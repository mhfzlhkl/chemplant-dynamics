# app/hub/signal_hub.py

"""Parent hub: single-producer / multi-subscriber fan-out.

Architecture (see ``README.md`` section "SignalHub (parent–child
broadcast, v2)" for the high-level picture):

::

        ENGINE → bridge._records (Queue)        ──── 1× per-page producer
                       │
                       ▼   (drain once per tick)
            ┌──────────────────────────────┐
            │   SignalHub  (PARENT)        │
            │  - snapshot, lock            │
            │  - subscribers: [Child, ...] │
            │  - 1× ui.timer @ tick_s      │
            └──────────────────────────────┘
              │      │      │      │
              ▼      ▼      ▼      ▼
            SvgChild Faceplate Modal Logger ...

Properties this delivers:

- **No queue race.** Only ``SignalHub._tick`` calls
  ``bridge.drain_records()``. Children NEVER touch the queue.
- **Same value, same tick.** A single ``_tick`` builds one
  ``snapshot`` and one ``delta_keys`` set, then dispatches them
  *sequentially in the same Python turn* to every child — so
  "one number from the engine appears at every child in the same
  tick" is structural, not just best-effort.
- **Bidirectional channel.** ``request_write(modal_key, value)``
  resolves to the engine tag and either:
    * sets ``bridge.state.input_overrides[engine_tag]`` (writable
      input), or
    * routes a status key change through
      ``bridge.apply_runtime_configuration(restart_if_needed=True)``.
  The engine's echo lands in the next ``_run_one_step`` record
  and is fanned out to *all* children — so a SP edit in the modal
  is reflected in the SVG, faceplate, data logger, and chart in
  the same downstream tick.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable, Iterable, List, Mapping, Optional, Protocol

from app.hub.controller_registry import ControllerRegistry
from app.hub.engine_control import EngineControl


logger = logging.getLogger(__name__)


def _offload(func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Run ``func(*args, **kwargs)`` in the default thread pool so the
    UI/main thread is not blocked by I/O or CPU work that does not
    touch NiceGUI elements directly.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    try:
        loop.run_in_executor(None, lambda: func(*args, **kwargs))
    except Exception:
        pass


# ── Mode name <-> code helpers (mirrored from base_bridge_store) ──
# Modals encode controller mode as 0=Off, 1=Manual, 2=Auto; the bridge
# uses the words 'Off' | 'Manual' | 'Automatic'. The hub exposes them
# in the snapshot as floats (same convention as the legacy stack) so
# children and the legacy modals interoperate cleanly.

def mode_name_to_code(name: str) -> int:
    return {'off': 0, 'manual': 1, 'automatic': 2, 'auto': 2}.get(
        str(name or '').strip().lower(), 2,
    )


def mode_code_to_name(code: int) -> str:
    return {0: 'Off', 1: 'Manual', 2: 'Automatic'}.get(int(code), 'Automatic')


@dataclass(slots=True, frozen=True)
class TickMeta:
    """Per-tick metadata that accompanies every ``on_tick`` dispatch.

    Children that care about *which step* a value came from
    (data logger, perf chart) read these. The :attr:`reset_counter`
    advances when the bridge is reset — children compare against
    their own copy to detect a wipe.
    """

    sim_time: float
    step_index: int
    status: str
    mode: str
    reset_counter: int


class Subscriber(Protocol):
    """Anything the hub can fan out to."""

    def on_tick(
        self,
        delta_keys: frozenset[str],
        snapshot: Mapping[str, float],
        meta: TickMeta,
    ) -> None: ...


class SignalHub:
    """Parent broadcast hub.

    One per page, per case. Wraps the per-browser bridge and the
    case's :class:`ControllerRegistry`. Spins a SINGLE ``ui.timer``
    at ``tick_s`` (default 50 ms = 20 Hz) — this is the only timer
    that ever calls ``bridge.drain_records()``.

    See :func:`build_sthr_hub` and :func:`build_biodiesel_hub` for
    construction helpers.
    """

    def __init__(
        self,
        bridge: Any,
        registry: ControllerRegistry,
        *,
        initial: Optional[Mapping[str, float]] = None,
        tick_s: float = 0.05,
    ) -> None:
        self._bridge = bridge
        self._registry = registry
        self._tick_s = float(tick_s)
        self._engine_control = EngineControl(bridge)

        self._lock = threading.Lock()
        self._snapshot: dict[str, float] = dict(initial or {})
        # Initial seed snapshot used by ``reset()`` to repopulate the
        # cache so a child reading immediately after reset still sees
        # the case-config baseline (matches legacy
        # ``BaseBridgeStore._initial_seed``).
        self._initial_seed: dict[str, float] = dict(initial or {})

        # Subscribers — stored as a tuple snapshot so iteration during
        # ``_tick`` can drop the lock as soon as the snapshot is taken.
        self._subscribers: List[Subscriber] = []

        # Per-tick state — populated by drain, consumed by notify.
        self._sim_time: float = 0.0
        self._step_index: int = -1
        self._status: str = str(getattr(bridge.state, 'status', 'idle') or 'idle')
        self._mode: str = str(
            getattr(bridge.state, 'controller_mode', '') or 'Automatic',
        )
        self._reset_counter: int = 0

        # Monotonic tick counter — exposed to the client store so
        # out-of-order batches under on_air jitter can be ignored.
        self._tick_counter: int = 0

        # NiceGUI timer handle so ``stop()`` can cancel it.
        self._timer: Any = None

    # ---------------------------------------------------------------
    # Public surface
    # ---------------------------------------------------------------

    @property
    def engine_control(self) -> EngineControl:
        """Direct control surface for the engine (run/stop/reset/...)."""
        return self._engine_control

    @property
    def registry(self) -> ControllerRegistry:
        return self._registry

    @property
    def bridge(self) -> Any:
        """Escape hatch — exposes the bridge for legacy code paths.

        New children should NOT use this; they subscribe and react
        to ``on_tick`` instead.
        """
        return self._bridge

    @property
    def tick_s(self) -> float:
        return self._tick_s

    def snapshot(self) -> Mapping[str, float]:
        """Return a copy of the latest snapshot (lock-safe)."""
        with self._lock:
            return dict(self._snapshot)

    def get(self, modal_key: str, default: float = 0.0) -> float:
        """Single-value snapshot read (LocalStore-compatible)."""
        with self._lock:
            if modal_key in self._snapshot:
                return float(self._snapshot[modal_key])
        return float(default)

    def subscribe(self, child: Subscriber) -> Callable[[], None]:
        """Register a child. Returns an unsubscribe callable."""
        with self._lock:
            self._subscribers.append(child)

        def _unsubscribe() -> None:
            with self._lock:
                try:
                    self._subscribers.remove(child)
                except ValueError:
                    pass

        return _unsubscribe

    # ---------------------------------------------------------------
    # Bidirectional path — child → engine
    # ---------------------------------------------------------------

    def request_write(self, modal_key: str, value: float) -> None:
        """Push a value upstream from a child to the engine.

        Three routes, decided by the registry spec:

        1. **Status key** (``role='status'``): writes the bridge's
           ``controller_mode`` and triggers
           ``apply_runtime_configuration(restart_if_needed=True)``.
           The next step record will echo the new mode and the hub
           fans it out to every child.
        2. **Writable input** (``writable=True`` with an
           ``engine_tag``): calls ``bridge.set_input_value(tag, v)``
           which updates ``bridge.state.input_overrides``. The next
           ``_run_one_step`` will use it as an external input and
           the echo flows back via the normal tick.
        3. **Local / read-only**: just writes the snapshot cache
           (so a child that requests a write to a PV key still
           sees its value until the engine overrides it).

        The snapshot cache is updated immediately in cases (2) and
        (3) so a read on the SAME tick sees the new value (the
        engine echo on the NEXT tick will confirm).
        """
        try:
            v = float(value)
        except (TypeError, ValueError):
            return

        spec = self._registry.get_by_modal_key(modal_key)

        # Status key → bridge controller_mode + apply
        if spec is not None and spec.role == 'status':
            mode_name = mode_code_to_name(round(v))
            try:
                self._bridge.state.controller_mode = mode_name
                apply = getattr(
                    self._bridge, 'apply_runtime_configuration', None,
                )
                if callable(apply):
                    apply(restart_if_needed=True)
            except Exception:
                logger.exception(
                    'SignalHub: status write failed for %s', modal_key,
                )
            self._write_snapshot({modal_key: v})
            return

        # Writable input → bridge.set_input_value
        engine_tag = spec.engine_tag if (spec and spec.writable) else None
        if engine_tag is not None:
            try:
                self._bridge.set_input_value(engine_tag, v)
            except Exception:
                logger.exception(
                    'SignalHub: bridge.set_input_value failed for %s → %s',
                    modal_key, engine_tag,
                )
            self._write_snapshot({modal_key: v})
            return

        # Local / read-only — just cache
        self._write_snapshot({modal_key: v})

    # ---------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------

    def start(self) -> None:
        """Start the master tick. Idempotent."""
        if self._timer is not None:
            return
        # Seed-from-storage: if the bridge's persistent state has
        # no records yet (typical right after a page reload) but
        # we have a stashed last snapshot for this browser, merge
        # it into the in-memory snapshot so the UI doesn't flash
        # zeros while the first engine tick arrives. The bridge's
        # own tick on the next loop will overwrite any key whose
        # authoritative value differs — we just want a "no flash"
        # paint.
        try:
            self._seed_from_storage()
        except Exception:
            logger.debug('SignalHub: _seed_from_storage failed', exc_info=True)
        try:
            # Lazy import so the hub stays importable in tests that
            # don't have NiceGUI's UI loop available.
            from nicegui import ui
            self._timer = ui.timer(self._tick_s, self._tick)
        except Exception:
            # In headless / test mode the caller can drive _tick manually.
            logger.debug('SignalHub.start: no NiceGUI ui.timer available')

    def _seed_from_storage(self) -> None:
        """Merge a previously-persisted snapshot (if any) into the
        in-memory snapshot. Keys already present in the bridge's
        authoritative state are NOT overwritten — the bridge wins.

        Storage shape: ``app.storage.user['hub_snapshot:<case>']`` is
        a dict of ``{modal_key: float}``. We only read; writes happen
        in :meth:`_maybe_persist_snapshot` below.
        """
        try:
            from nicegui import app
        except Exception:
            return
        case = self._case_slug()
        if not case:
            return
        key = f'hub_snapshot:{case}'
        try:
            stored = app.storage.user.get(key) or {}
        except Exception:
            return
        if not isinstance(stored, dict) or not stored:
            return
        with self._lock:
            for modal_key, value in stored.items():
                if modal_key in self._snapshot:
                    continue
                try:
                    self._snapshot[str(modal_key)] = float(value)
                except (TypeError, ValueError):
                    continue

    def _maybe_persist_snapshot(self) -> None:
        """Every Nth tick, mirror the snapshot to ``app.storage.user``.

        Throttled to every 5th tick (~250 ms at 20 Hz) so the JSON
        serialization cost is bounded. The write is best-effort:
        a failure (storage full, private mode) is logged at debug
        and never raised.

        The actual file write is off-loaded to the default thread pool
        so the UI timer tick never stalls on disk I/O.
        """
        if not hasattr(self, '_persist_counter'):
            self._persist_counter = 0
        self._persist_counter += 1
        if self._persist_counter % 5 != 0:
            return
        try:
            from nicegui import app
        except Exception:
            return
        case = self._case_slug()
        if not case:
            return
        key = f'hub_snapshot:{case}'
        with self._lock:
            payload = dict(self._snapshot)

        def _write() -> None:
            try:
                app.storage.user[key] = payload
            except Exception:
                logger.debug(
                    'SignalHub: failed to persist snapshot to storage',
                    exc_info=True,
                )

        _offload(_write)

    def _case_slug(self) -> str:
        """Best-effort case name for the storage key.

        Falls back to the bridge's ``case_name`` (which every
        bridge has) and finally to the empty string (which skips
        persistence).
        """
        try:
            name = str(getattr(self._bridge, 'case_name', '') or '')
            if name:
                return name
        except Exception:
            pass
        return ''

    def stop(self) -> None:
        timer = self._timer
        self._timer = None
        if timer is None:
            return
        try:
            cancel = getattr(timer, 'cancel', None)
            if callable(cancel):
                cancel()
            deactivate = getattr(timer, 'deactivate', None)
            if callable(deactivate):
                deactivate()
        except Exception:
            pass

    def tick_once(self) -> None:
        """Drive one tick manually (used by tests and post-reset rebuilds)."""
        self._tick()

    # ---------------------------------------------------------------
    # Reset support — clears the snapshot to its initial seed and
    # bumps the reset counter so children can detect the boundary.
    # ---------------------------------------------------------------

    def reset_snapshot_to_seed(self) -> None:
        """Re-seed the snapshot from the registry's initial seed.

        Mirrors the legacy ``BaseBridgeStore._reseed_cache_from_bridge``
        — called by the v2 page's Reset handler AFTER the bridge has
        been reset, so children that snapshot-read during the same
        tick see the post-reset baseline.
        """
        with self._lock:
            self._snapshot = dict(self._initial_seed)
            # Replenish input echoes from bridge.input_overrides (which
            # the bridge re-seeded from its case config).
            try:
                overrides = (
                    getattr(self._bridge.state, 'input_overrides', None) or {}
                )
                input_map = self._registry.input_field_to_override()
                for modal_key, engine_tag in input_map.items():
                    if engine_tag in overrides:
                        try:
                            self._snapshot[modal_key] = float(
                                overrides[engine_tag],
                            )
                        except (TypeError, ValueError):
                            pass
            except Exception:
                pass
            self._sim_time = 0.0
            self._step_index = -1
            self._reset_counter += 1

    # ---------------------------------------------------------------
    # Internal — tick loop
    # ---------------------------------------------------------------

    def _tick(self) -> None:
        # ── 1. Drain (single producer-consumer point) ──
        # Cap at 20 records per tick.  At 20 Hz that is enough headroom
        # for one real-time step; larger bursts are deferred to the next
        # tick so the UI timer never stalls on heavy formatting.
        try:
            records: list[Any] = self._bridge.drain_records(20)
        except Exception:
            logger.exception('SignalHub: drain_records failed')
            return

        # ── 2. Apply records → snapshot + delta ──
        delta_keys, meta = self._apply_records(records)

        # Always refresh status / clock so children's clocks tick even
        # when no step record arrived this turn.
        try:
            bridge_state = self._bridge.state
            self._status = str(
                getattr(bridge_state, 'status', self._status) or self._status,
            )
            self._mode = str(
                getattr(bridge_state, 'controller_mode', self._mode)
                or self._mode,
            )
            self._sim_time = float(
                getattr(bridge_state, 'global_sim_time', self._sim_time)
                or self._sim_time,
            )
            self._step_index = int(
                getattr(bridge_state, 'last_step', self._step_index)
                or self._step_index,
            )
        except Exception:
            pass

        # Even without a data delta we still publish a tick so children
        # that care about time/status (clock, glow, faceplate refresh)
        # repaint. Children that only care about delta keys check
        # ``if not delta_keys: return`` themselves.
        meta = TickMeta(
            sim_time=self._sim_time,
            step_index=self._step_index,
            status=self._status,
            mode=self._mode,
            reset_counter=self._reset_counter,
        )

        # ── 3. Atomic fan-out ──
        # Take a snapshot of the subscriber list under the lock so a
        # ``subscribe()`` during dispatch can't mutate it mid-iteration.
        # All children are then called sequentially with the SAME
        # ``delta_keys`` frozenset and the SAME snapshot mapping —
        # that's what makes "satu angka di tick yang sama" structural.
        with self._lock:
            subscribers_snapshot = tuple(self._subscribers)
            snapshot_view = dict(self._snapshot)

        for child in subscribers_snapshot:
            try:
                child.on_tick(delta_keys, snapshot_view, meta)
            except Exception:
                logger.exception(
                    'SignalHub: subscriber %r raised in on_tick',
                    type(child).__name__,
                )

        # ── 3b. Single batched client-state push ──
        # Sends the same delta_keys + snapshot to the client-side
        # ``window.__chemPlantState`` store. Subscribers that opt
        # in (currently ``SvgChild``) read from that store instead
        # of round-tripping per key. Best-effort: never raises.
        # See ``app.ui.bridge_store`` for the rationale.
        try:
            from app.ui.bridge_store import dispatch, payload as _payload
            self._tick_counter += 1
            meta_for_payload = TickMeta(
                sim_time=self._sim_time,
                step_index=self._step_index,
                status=self._status,
                mode=self._mode,
                reset_counter=self._reset_counter,
            )
            # Only push to the client store when there is real data
            # changed.  When the engine is idle/paused the wire stays
            # completely silent so the browser's rAF loop doesn't
            # wake up for no-op batches.
            if delta_keys:
                pl = _payload(
                    delta_keys=delta_keys,
                    snapshot=snapshot_view,
                    registry=self._registry,
                    meta=meta_for_payload,
                    tick=self._tick_counter,
                )
                dispatch(pl)
        except Exception:
            logger.debug(
                'SignalHub: client-state dispatch failed',
                exc_info=True,
            )

        # Give the engine / other threads a chance to run even when
        # the UI timer fires in a tight loop (high-acceleration mode).
        try:
            import time as _time
            _time.sleep(0)
        except Exception:
            pass

        # Throttled mirror of the snapshot to ``app.storage.user``
        # so a page reload repaints the last-known values within
        # ~200 ms before the first engine tick lands. The write
        # is throttled to every 5th tick (250 ms at 20 Hz) so the
        # JSON serialization cost is bounded.
        try:
            self._maybe_persist_snapshot()
        except Exception:
            logger.debug(
                'SignalHub: _maybe_persist_snapshot failed',
                exc_info=True,
            )

    def _apply_records(
        self,
        records: Iterable[Any],
    ) -> tuple[frozenset[str], TickMeta]:
        """Fold drained records into ``self._snapshot``, return delta keys."""
        delta: dict[str, float] = {}

        output_to_pv = self._registry.output_to_pv()
        input_map = self._registry.input_field_to_override()
        status_keys = self._registry.status_keys()

        for record in records:
            kind = getattr(record, 'kind', None)
            if kind == 'step':
                self._fold_step(
                    record, output_to_pv, input_map, status_keys, delta,
                )
            elif kind == 'status':
                self._fold_status(record, status_keys, delta)

        if delta:
            self._write_snapshot(delta)

        # Apply derived mirrors (e.g. STHR fi102_pv = fi101_pv).
        derived = self._registry.derived_pairs()
        if derived and (delta or not self._snapshot):
            with self._lock:
                for source_key, target_key in derived:
                    if source_key in self._snapshot:
                        v = float(self._snapshot[source_key])
                        if self._snapshot.get(target_key) != v:
                            self._snapshot[target_key] = v
                            delta[target_key] = v

        meta = TickMeta(
            sim_time=self._sim_time,
            step_index=self._step_index,
            status=self._status,
            mode=self._mode,
            reset_counter=self._reset_counter,
        )
        return frozenset(delta.keys()), meta

    def _fold_step(
        self,
        record: Any,
        output_to_pv: Mapping[str, str],
        input_map: Mapping[str, str],
        status_keys: tuple[str, ...],
        delta: dict[str, float],
    ) -> None:
        inputs = getattr(record, 'inputs', None) or {}
        states = getattr(record, 'states', None) or {}
        outputs = getattr(record, 'outputs', None) or {}

        # outputs > states > inputs (mirrors BaseBridgeStore._update_from_step).
        for engine_tag, modal_key in output_to_pv.items():
            source: Optional[float] = None
            if engine_tag in outputs:
                source = self._safe_float(outputs[engine_tag])
            elif engine_tag in states:
                source = self._safe_float(states[engine_tag])
            elif engine_tag in inputs:
                source = self._safe_float(inputs[engine_tag])
            if source is not None:
                delta[modal_key] = source

        # Input echo — only fills modal keys not already in delta.
        for modal_key, engine_tag in input_map.items():
            if modal_key in delta:
                continue
            if engine_tag in inputs:
                v = self._safe_float(inputs[engine_tag])
                if v is not None:
                    delta[modal_key] = v

        # Status keys
        mode_text = getattr(record, 'mode', None) or ''
        if mode_text:
            code = float(mode_name_to_code(mode_text))
            for sk in status_keys:
                delta[sk] = code

        # Step / time bookkeeping
        if getattr(record, 'time_min', None) is not None:
            try:
                self._sim_time = float(record.time_min)
            except (TypeError, ValueError):
                pass
        if getattr(record, 'step_index', None) is not None:
            try:
                self._step_index = int(record.step_index)
            except (TypeError, ValueError):
                pass

    def _fold_status(
        self,
        record: Any,
        status_keys: tuple[str, ...],
        delta: dict[str, float],
    ) -> None:
        mode_text = getattr(record, 'mode', None) or ''
        if mode_text:
            code = float(mode_name_to_code(mode_text))
            for sk in status_keys:
                delta[sk] = code

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _write_snapshot(self, new_values: Mapping[str, float]) -> None:
        with self._lock:
            for key, value in new_values.items():
                self._snapshot[key] = float(value)


__all__ = [
    'SignalHub',
    'Subscriber',
    'TickMeta',
    'mode_name_to_code',
    'mode_code_to_name',
]
