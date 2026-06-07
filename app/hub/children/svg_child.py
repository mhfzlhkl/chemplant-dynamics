# app/hub/children/svg_child.py

"""Child that updates the P&ID SVG ``<text>`` elements.

Replaces the legacy ``BaseLiveFlusher._push_to_svg`` (see
``app/pid/_shared/base_live_flusher.py``). Differences:

- Reads its targets and formatting from the hub's
  :class:`ControllerRegistry` instead of three per-case maps.
- Receives ``delta_keys`` from the hub, so it only formats and
  pushes controllers whose value actually changed this tick.
- One batched ``ui.run_javascript`` per tick when the
  client-side live-state store is unavailable, **or zero** when
  it is — the client store's rAF loop drives DOM updates
  locally (see ``app.ui.bridge_store``).
- Local **control**: ``svg.control.flush_all()`` forces a full
  repaint (used by the page after a reset to repopulate the seed
  values). The control object holds no engine state — it only
  affects this child's own rendering.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from app.hub.controller_registry import ControllerRegistry
from app.hub.signal_hub import SignalHub, TickMeta


logger = logging.getLogger(__name__)


# Element-level flag: once set, the SvgChild registers its
# text-element bindings with the client store and stops
# per-tick ``run_javascript`` pushes for those elements.
_CLIENT_STORE_REGISTERED: set[int] = set()


class _SvgChildControl:
    """Local control surface for :class:`SvgChild`.

    Exposes child-local actions that don't need to round-trip through
    the hub: forcing a repaint, switching the target SVG class, etc.
    """

    def __init__(self, owner: 'SvgChild') -> None:
        self._owner = owner

    def flush_all(self) -> None:
        """Format and push every emitter (ignore the delta gate)."""
        self._owner._render(self._owner._all_emitter_keys(), self._owner._hub.snapshot())

    def set_wrapper_class(self, css_class: str) -> None:
        """Re-scope the JS document.getElementById lookup.

        Currently the SvgChild looks elements up by absolute id which
        doesn't need a wrapper scope, but the hook is here so a
        future child that batches via a scoped ``querySelector`` can
        rebind without re-creating the child.
        """
        self._owner._wrapper_class = str(css_class)


class SvgChild:
    """Subscriber that drives the P&ID SVG text elements.

    Each tick: filter ``delta_keys`` to those that have an
    ``svg_id``, format via the registry, batch into one JS call.

    When the client-side live-state store is available
    (``window.__chemPlantState`` exists), the SVG child registers
    its element bindings ONCE and the store's rAF loop does the
    DOM writes — the per-tick ``run_javascript`` push is skipped,
    removing a round trip per changed value. The store is updated
    by :meth:`app.hub.signal_hub.SignalHub._tick` itself, so this
    child becomes essentially zero-cost per tick.
    """

    def __init__(
        self,
        hub: SignalHub,
        *,
        wrapper_class: str | None = None,
    ) -> None:
        self._hub = hub
        self._registry: ControllerRegistry = hub.registry
        self._wrapper_class = str(wrapper_class or '')
        self._control = _SvgChildControl(self)
        self._unsubscribe: Any = None

        # Map modal_key → svg_id (cached so the per-tick loop is O(delta)).
        self._modal_key_to_svg_id: dict[str, str] = {
            spec.modal_key: spec.svg_id
            for spec in self._registry.svg_emitters()
            if spec.svg_id
        }
        # Set True after the first successful registration with the
        # client store. When True, ``_render`` becomes a no-op for
        # the standard text elements — only ``flush_all`` (used
        # after a reset) forces a server-side push.
        self._client_store_active: bool = False

    # ---------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------

    @property
    def control(self) -> _SvgChildControl:
        """Child-local control (forces repaint, scope changes)."""
        return self._control

    def attach(self) -> None:
        """Subscribe to the hub."""
        if self._unsubscribe is None:
            self._unsubscribe = self._hub.subscribe(self)
        # Best-effort: register with the client store on attach so
        # the first tick already uses the client-driven path. Safe
        # to call before the store is installed — the registration
        # JS is a no-op when ``window.__chemPlantState`` is absent.
        self._register_with_client_store()

    def detach(self) -> None:
        unsubscribe = self._unsubscribe
        self._unsubscribe = None
        if unsubscribe is not None:
            try:
                unsubscribe()
            except Exception:
                pass
        # Clear the registration flag so a subsequent ``attach`` (e.g.
        # after a page reload) re-registers cleanly.
        try:
            _CLIENT_STORE_REGISTERED.discard(id(self))
        except Exception:
            pass
        self._client_store_active = False

    def _register_with_client_store(self) -> None:
        """Push the modal_key → svg_id map to the client store.

        The store then drives DOM updates from its own
        ``requestAnimationFrame`` loop. Called once on
        ``attach``; idempotent via ``_CLIENT_STORE_REGISTERED``.
        """
        if not self._modal_key_to_svg_id:
            return
        if id(self) in _CLIENT_STORE_REGISTERED:
            return
        try:
            from app.ui.bridge_store import bind_text_elements
            bind_text_elements(bindings=self._modal_key_to_svg_id)
            _CLIENT_STORE_REGISTERED.add(id(self))
            self._client_store_active = True
        except Exception:
            # Fall through — per-tick JS push will continue to work.
            logger.debug(
                'SvgChild: client store registration failed',
                exc_info=True,
            )

    # ---------------------------------------------------------------
    # Subscriber protocol
    # ---------------------------------------------------------------

    def on_tick(
        self,
        delta_keys: frozenset[str],
        snapshot: Mapping[str, float],
        meta: TickMeta,
    ) -> None:
        if not delta_keys:
            return
        # Filter to keys that have an SVG element.
        targets = delta_keys & self._modal_key_to_svg_id.keys()
        if not targets:
            return
        # When the client store is active, the per-tick DOM writes
        # happen in the browser's rAF loop. Skip the server push
        # entirely to keep the wire chatty-free.
        if self._client_store_active:
            return
        self._render(targets, snapshot)

    # ---------------------------------------------------------------
    # Internal — formatting + JS push (identical contract to legacy
    # ``BaseLiveFlusher._push_to_svg``)
    # ---------------------------------------------------------------

    def _all_emitter_keys(self) -> frozenset[str]:
        return frozenset(self._modal_key_to_svg_id.keys())

    def _render(self, keys, snapshot: Mapping[str, float]) -> None:
        updates: dict[str, str] = {}
        for modal_key in keys:
            svg_id = self._modal_key_to_svg_id.get(modal_key)
            if svg_id is None:
                continue
            value = snapshot.get(modal_key)
            updates[f'{svg_id}-value'] = self._registry.format(modal_key, value)

        if not updates:
            return

        payload = json.dumps(updates, ensure_ascii=False)
        try:
            from nicegui import ui
            ui.run_javascript(f'''
                (function() {{
                    const updates = {payload};
                    for (const [id, text] of Object.entries(updates)) {{
                        const el = document.getElementById(id);
                        if (el) {{
                            el.textContent = text;
                        }}
                    }}
                }})();
            ''')
        except Exception:
            logger.exception('SvgChild: ui.run_javascript failed')


__all__ = ['SvgChild']
