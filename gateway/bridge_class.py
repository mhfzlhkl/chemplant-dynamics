# engine_root/gateway/bridge_class.py

"""Generic, case-agnostic bridge between the engine and the NiceGUI UI.

Historically this module lived at ``gateway/sthr_bridge.py`` and
shipped a class named :class:`STHRBridge`. The class is fully
case-agnostic — it accepts a ``case_name`` argument and dispatches
to the matching ``cases.<name>.config`` module via
:func:`gateway.config_registry.get_case_config`. The historical
``sthr_bridge`` name was a relic of the original STHR-only origin.

This file now exports the renamed, generic :class:`Bridge` class.
For backward compatibility the old import paths are still re-exported
from :mod:`gateway.bridge` and :mod:`gateway.biodiesel_bridge`.
"""

from __future__ import annotations

import logging
import math
import sys
from collections import deque
from collections.abc import Sequence
from datetime import datetime
import time
from queue import Empty, Queue
from threading import Event as ThreadEvent
from threading import Lock, Thread
from typing import Any

from core.appdb import appdb as default_appdb
from gateway.config_registry import get_case_config
from engine.runtime.interfaces import SimulationSessionProtocol
from engine.runtime.runtime_config import RuntimeConfig
from engine.runtime.simulation_clock import SimulationClock, make_clock
from engine.runtime.simulation_engine import SimulationEngine
from gateway.bridge_support import BridgeRecord, BridgeState, safe_float


logger = logging.getLogger(__name__)


def _set_worker_priority_low() -> None:
    """Lower the current thread priority so the UI/main thread stays responsive.

    On Windows this calls SetThreadPriority(BELOW_NORMAL).  On other
    platforms it is a no-op.
    """
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]
        kernel32.SetThreadPriority.restype = wintypes.BOOL
        handle = kernel32.GetCurrentThread()
        # THREAD_PRIORITY_BELOW_NORMAL = -1
        kernel32.SetThreadPriority(handle, -1)
    except Exception:
        pass


class Bridge:
    """
    Bridge antara engine simulasi dan NiceGUI.

    Tanggung jawab:
        - menyimpan state UI
        - menyimpan profile user/browser
        - menjalankan worker thread
        - mengatur stop/restart/config changed
        - mengirim BridgeRecord ke UI melalui queue

    Pacing simulasi dipisahkan ke SimulationClock.

    Aturan waktu:
        real_time=True:
            simulasi real-time, acceleration diabaikan.

        real_time=False:
            simulasi mengikuti acceleration.

        acceleration=1:
            setara real-time.

        acceleration>1:
            lebih cepat.

        acceleration<1:
            lebih lambat.

        time_end finite:
            waktu akhir absolute sesuai session.time_unit.

        time_end inf:
            tanpa batas akhir simulasi.
    """

    profile_storage_prefix = 'case_bridge'

    def __init__(self, appdb=default_appdb, case_name: str = 'sthr') -> None:
        self.appdb = appdb
        self.case_name = str(case_name or 'sthr').strip().lower()
        self.cfg = get_case_config(self.case_name)
        self.state = BridgeState()

        self._records: Queue[BridgeRecord] = Queue()

        # Persistent step history for replay when a new browser session connects
        # mid-simulation. Mirrors the old engine's chart_data store.
        self._step_log: deque[dict] = deque(maxlen=6000)

        self._lock = Lock()
        self._stop_event = ThreadEvent()
        self._pause_event = ThreadEvent()
        self._restart_event = ThreadEvent()
        self._config_changed_event = ThreadEvent()

        self._worker: Thread | None = None

        # If True, the next start() should create a fresh worker and reset time.
        self._need_fresh_start = False

        self._browser_profile_key: str | None = None
        self._browser_profile: dict[str, Any] | None = None

        self._global_sim_time = 0.0

        self._session: SimulationSessionProtocol | None = None
        self._engine: SimulationEngine | None = None

    # -------------------------------------------------------------------------
    # Profile
    # -------------------------------------------------------------------------

    def bind_profile(
        self,
        browser_id: str,
        profile_storage: dict[str, Any],
    ) -> None:
        self._browser_profile_key = (
            f'{self.profile_storage_prefix}:{self.case_name}:{browser_id}'
        )
        self._browser_profile = profile_storage

        self._load_profile()

        runtime_config = self._read_runtime_config()
        self._apply_runtime_config_to_legacy_cfg(runtime_config)

        # Tell core which case is now active so its timeseries backend
        # picks up the right ``SIMULATION_PARAMS``. ``core.appdb`` no
        # longer imports the case config — it relies on this hook.
        try:
            from core.appdb import set_active_case_config
            set_active_case_config(self.cfg.SIMULATION_PARAMS)
        except Exception:
            logger.exception(
                'bind_profile: failed to register case config with core.appdb',
            )

        engine = self._build_engine()
        session = engine.session_factory()

        self._store_available_log_fields(session)
        self._seed_input_overrides()
        # ensure the next start() creates a fresh worker/session so the
        # first Run click after UI load reliably starts the simulation
        # (avoids cases where a partially-initialized state requires
        # a second click).
        self._need_fresh_start = True

    def _load_profile(self) -> None:
        profile = self._browser_profile or {}

        case_time_unit = self._case_time_unit()

        self.state.controller_mode = str(
            profile.get(
                'controller_mode',
                self.cfg.CONTROLLER_MODE.get('Mode', 'Automatic'),
            )
            or 'Automatic'
        )

        self.state.Ts = safe_float(
            profile.get(
                'Ts',
                self.cfg.to_minutes(
                    self.cfg.SIMULATION_PARAMS.get('Ts', 0.01),
                    case_time_unit,
                ),
            ),
            0.01,
            minimum=1e-12,
        )

        self.state.acceleration = safe_float(
            profile.get(
                'acceleration',
                self.cfg.SIMULATION_PARAMS.get('acceleration', 1.0),
            ),
            1.0,
            minimum=1e-12,
        )

        self.state.real_time = bool(
            profile.get(
                'real_time',
                self.cfg.SIMULATION_PARAMS.get('real_time', True),
            )
        )

        self.state.time_end = self.parse_time_end_value(
            profile.get(
                'time_end',
                self.cfg.SIMULATION_PARAMS.get('time_end', float('inf')),
            )
        )

        # Always start with no fields selected — user picks explicitly each session.
        self.state.selected_log_fields = []

        # Always start from config defaults — _seed_input_overrides fills these
        # after the session is built, so no need to restore from profile.
        self.state.input_overrides = {}

        raw_loop_modes = profile.get('loop_modes', {})
        self.state.loop_modes = {
            k: str(v)
            for k, v in raw_loop_modes.items()
            if isinstance(k, str) and isinstance(v, str)
        }

        self.state.scenario = str(profile.get('scenario', 'operational'))

    def export_profile(self) -> dict[str, Any]:
        parsed_time_end = self.parse_time_end_value(self.state.time_end)

        return {
            'controller_mode': str(self.state.controller_mode or 'Automatic'),
            'Ts': safe_float(
                self.state.Ts,
                0.01,
                minimum=1e-12,
            ),
            'acceleration': safe_float(
                self.state.acceleration,
                1.0,
                minimum=1e-12,
            ),
            'real_time': bool(self.state.real_time),
            'time_end': None if math.isinf(parsed_time_end) else parsed_time_end,
            'loop_modes': dict(self.state.loop_modes),
            'scenario': str(self.state.scenario or 'operational'),
        }

    def _case_time_unit(self) -> str:
        runtime = getattr(self.cfg, 'CASE_RUNTIME', None)
        configured_unit = getattr(runtime, 'time_unit', None)
        if configured_unit is None:
            configured_unit = self.cfg.SIMULATION_PARAMS.get('time_unit', 'minutes')
        return self.cfg.normalize_time_unit(configured_unit)

    def persist_profile(self) -> None:
        if self._browser_profile is None:
            return

        self._browser_profile.update(self.export_profile())

    # -------------------------------------------------------------------------
    # Engine/session
    # -------------------------------------------------------------------------

    def _build_engine(self) -> SimulationEngine:
        return SimulationEngine(
            appdb=self.appdb,
            case=self.case_name,
            config_module=self.cfg,
        )

    def _seed_input_overrides(self) -> None:
        mode = str(
            self.state.controller_mode
            or self.cfg.CONTROLLER_MODE.get('Mode', 'Automatic')
            or 'Automatic'
        )

        # Build defaults from mode-specific provider (not generic defaults)
        defaults: dict[str, float] = {}

        scenario_mode_defaults_provider = getattr(
            self.cfg,
            'default_inputs_for_scenario_mode',
            None,
        )

        mode_defaults_provider = getattr(
            self.cfg,
            'default_inputs_for_mode',
            None,
        )

        if callable(scenario_mode_defaults_provider):
            try:
                raw = scenario_mode_defaults_provider(
                    self.state.scenario,
                    mode,
                )
                if isinstance(raw, dict):
                    defaults.update({name: float(v) for name, v in raw.items()})
            except Exception:
                logger.exception(
                    'Failed to load scenario/mode-specific default inputs.',
                )

        elif callable(mode_defaults_provider):
            try:
                raw = mode_defaults_provider(mode)
                if isinstance(raw, dict):
                    defaults.update({name: float(v) for name, v in raw.items()})
            except Exception:
                logger.exception('Failed to load mode-specific default inputs.')
        
        # Only fallback to generic defaults for names not covered by mode-specific
        # This prevents mode-independent controller params (e.g., Kc) from leaking
        # into incompatible modes (Manual, Off)
        if mode.lower() == 'automatic':
            try:
                for name, value in dict(self.cfg.default_input_values() or {}).items():
                    defaults.setdefault(name, float(value))
            except Exception:
                logger.exception('Failed to load base default inputs.')

        # Preserve any user-entered overrides; only remove keys that are no
        # longer valid inputs for the current mode (e.g., Kc/tauI after
        # switching to Manual), and add defaults only for missing keys.
        for name in list(self.state.input_overrides.keys()):
            if name not in defaults:
                del self.state.input_overrides[name]
        for name, value in defaults.items():
            self.state.input_overrides.setdefault(name, float(value))

        # Ensure all session input tags have at least a value (0 for fields not in mode defaults)
        if self._session is not None:
            for name in getattr(self._session, 'input_tags', {}).keys():
                self.state.input_overrides.setdefault(name, 0.0)

    def supported_modes(self) -> list[str]:
        runtime = getattr(self.cfg, 'CASE_RUNTIME', None)
        configured_modes = getattr(runtime, 'supported_modes', None)
        if configured_modes:
            return [
                mode if any(ch.isupper() for ch in mode) else mode.capitalize()
                for mode in configured_modes
            ]
        return ['Automatic', 'Manual', 'Off']

    # -------------------------------------------------------------------------
    # time_end helpers
    # -------------------------------------------------------------------------

    def parse_time_end_value(
        self,
        value: Any,
    ) -> float:
        """
        Parse time_end dari UI/profile/config.

        Aturan:
            angka:
                waktu akhir absolute sesuai session.time_unit.

            None / kosong / Inf / infinity / ∞:
                tidak ada time end.
        """

        return safe_float(
            value,
            float('inf'),
            minimum=0.0,
            allow_inf=True,
        )

    def time_end_to_text(self) -> str:
        """
        Format time_end untuk UI input.

        Jika infinite, tampilkan string kosong agar user melihat field kosong.
        """

        value = self.parse_time_end_value(self.state.time_end)

        if math.isinf(value):
            return ''

        return f'{value:g}'

    def set_time_end_from_ui(
        self,
        value: Any,
    ) -> None:
        """
        Set time_end dari ui.input.

        Empty / Inf / infinity / ∞ akan menjadi float('inf').
        """

        with self._lock:
            self.state.time_end = self.parse_time_end_value(value)
            self.persist_profile()
            self._config_changed_event.set()

    # -------------------------------------------------------------------------
    # Runtime config
    # -------------------------------------------------------------------------

    def _read_runtime_config(self) -> RuntimeConfig:
        return RuntimeConfig(
            controller_mode=str(self.state.controller_mode or 'Automatic'),
            Ts=safe_float(
                self.state.Ts,
                0.01,
                minimum=1e-12,
            ),
            acceleration=safe_float(
                self.state.acceleration,
                1.0,
                minimum=1e-12,
            ),
            real_time=bool(self.state.real_time),
            time_end=self.parse_time_end_value(self.state.time_end),
            loop_modes=dict(self.state.loop_modes),
        )

    def _runtime_config_from_legacy_cfg(self) -> RuntimeConfig:
        case_time_unit = self._case_time_unit()
        _legacy_loop_modes = self.cfg.CONTROLLER_MODE.get('LoopModes', {})
        return RuntimeConfig(
            controller_mode=str(
                self.cfg.CONTROLLER_MODE.get(
                    'Mode',
                    self.state.controller_mode or 'Automatic',
                )
                or 'Automatic'
            ),
            Ts=safe_float(
                self.cfg.to_minutes(
                    self.cfg.SIMULATION_PARAMS.get(
                        'Ts',
                        self.cfg.from_minutes(self.state.Ts, case_time_unit),
                    ),
                    case_time_unit,
                ),
                0.01,
                minimum=1e-12,
            ),
            acceleration=safe_float(
                self.cfg.SIMULATION_PARAMS.get(
                    'acceleration',
                    self.state.acceleration,
                ),
                1.0,
                minimum=1e-12,
            ),
            real_time=bool(
                self.cfg.SIMULATION_PARAMS.get(
                    'real_time',
                    self.state.real_time,
                )
            ),
            time_end=self.parse_time_end_value(
                (
                    float('inf')
                    if math.isinf(
                        safe_float(
                            self.cfg.SIMULATION_PARAMS.get(
                                'time_end',
                                self.cfg.from_minutes(self.state.time_end, case_time_unit),
                            ),
                            float('inf'),
                            minimum=0.0,
                            allow_inf=True,
                        )
                    )
                    else self.cfg.to_minutes(
                        self.cfg.SIMULATION_PARAMS.get(
                            'time_end',
                            self.cfg.from_minutes(self.state.time_end, case_time_unit),
                        ),
                        case_time_unit,
                    )
                )
            ),
            loop_modes=dict(_legacy_loop_modes) if isinstance(_legacy_loop_modes, dict) else {},
        )

    def _apply_runtime_config_to_legacy_cfg(
        self,
        runtime_config: RuntimeConfig,
    ) -> None:
        case_time_unit = self._case_time_unit()
        self.cfg.CONTROLLER_MODE['Mode'] = runtime_config.controller_mode
        self.cfg.CONTROLLER_MODE['LoopModes'] = dict(runtime_config.loop_modes)
        self.cfg.SIMULATION_PARAMS['Ts'] = self.cfg.from_minutes(
            runtime_config.Ts,
            case_time_unit,
        )
        self.cfg.SIMULATION_PARAMS['acceleration'] = runtime_config.acceleration
        self.cfg.SIMULATION_PARAMS['real_time'] = runtime_config.real_time
        if math.isinf(runtime_config.time_end):
            self.cfg.SIMULATION_PARAMS['time_end'] = float('inf')
        else:
            self.cfg.SIMULATION_PARAMS['time_end'] = self.cfg.from_minutes(
                runtime_config.time_end,
                case_time_unit,
            )

    def _pacing_signature(
        self,
        runtime_config: RuntimeConfig,
    ) -> tuple[str, float]:
        """
        Signature untuk menentukan apakah clock perlu dibuat ulang.

        real_time=True:
            acceleration diabaikan.

        real_time=False:
            acceleration memengaruhi pacing.
        """

        if runtime_config.real_time:
            return ('real_time', 1.0)

        return (
            'accelerated',
            safe_float(runtime_config.acceleration, 1.0, minimum=1e-12),
        )

    def apply_runtime_configuration(
        self,
        *,
        restart_if_needed: bool = True,
    ) -> None:
        with self._lock:
            old_config = self._runtime_config_from_legacy_cfg()
            new_config = self._read_runtime_config()
            old_scenario = getattr(self, '_last_applied_scenario', None)
            new_scenario = str(self.state.scenario or 'operational')

            old_pacing = self._pacing_signature(old_config)
            new_pacing = self._pacing_signature(new_config)

            needs_restart = (
                self._session is not None
                and abs(float(new_config.Ts) - float(old_config.Ts)) > 1e-12
            )

            self._apply_runtime_config_to_legacy_cfg(new_config)
            
            # Reset input_overrides when scenario changes so that scenario-specific
            # defaults (e.g., STARTUP_ACTUATOR_INPUT) are applied correctly.
            if old_scenario != new_scenario:
                self.state.input_overrides = {}
            
            self._seed_input_overrides()
            self._last_applied_scenario = new_scenario
            self.persist_profile()

            if old_pacing != new_pacing:
                self._config_changed_event.set()

            if (
                old_config.time_end != new_config.time_end
                or old_config.controller_mode != new_config.controller_mode
                or old_config.loop_modes != new_config.loop_modes
                or old_scenario != new_scenario
            ):
                self._config_changed_event.set()

            if old_config.loop_modes != new_config.loop_modes:
                needs_restart = True

            if (
                old_config.loop_modes != new_config.loop_modes
                or old_config.controller_mode != new_config.controller_mode
            ):
                # Refresh available_log_fields immediately when the worker is not
                # running, so the input panel reflects the new mode without needing
                # to start the simulation first.
                if not (self._worker and self._worker.is_alive()):
                    try:
                        temp_engine = self._build_engine()
                        temp_session = temp_engine.session_factory()
                        self._session = temp_session
                        self._store_available_log_fields(temp_session)
                        self._seed_input_overrides()
                    except Exception:
                        logger.exception(
                            'Failed to refresh available_log_fields for controller or loop mode change.'
                        )
                else:
                    # If worker is alive and controller_mode changed, we need to restart
                    # the worker so it picks up the new session with the new mode/controller
                    if old_config.controller_mode != new_config.controller_mode:
                        needs_restart = True

            if needs_restart and restart_if_needed:
                self._restart_event.set()
                self._config_changed_event.set()

    # -------------------------------------------------------------------------
    # Log fields
    # -------------------------------------------------------------------------

    def _build_available_log_fields(
        self,
        session: SimulationSessionProtocol,
    ) -> list[str]:
        fields = [
            'meta:mode',
            'meta:step',
            'meta:time',
        ]

        fields.extend(
            f'input:{name}'
            for name in session.input_tags.keys()
        )

        fields.extend(
            f'state:{tag.name}'
            for tag in session.state_tags.values()
        )

        fields.extend(
            f'output:{name}'
            for name in session.output_tags.keys()
        )

        return fields

    def _store_available_log_fields(
        self,
        session: SimulationSessionProtocol,
    ) -> None:
        available = self._build_available_log_fields(session)

        # Detect whether the *set* of available fields actually changed.
        # A time_end-only change, or any other config change that does not
        # alter the engine session's input/state/output tags, must not
        # re-emit a 'header' record. The Data Logger and Performance Plot
        # treat a header re-emit as "available fields changed" and force a
        # re-render of every scope's header grid and replay. Suppressing
        # the no-op re-emit keeps the chart and log continuous across
        # worker restarts that are part of a "continue" flow.
        previous = list(self.state.available_log_fields or [])
        fields_changed = (
            len(previous) != len(available)
            or any(prev != new for prev, new in zip(previous, available))
        )

        self.state.available_log_fields = available

        if not self.state.selected_log_fields:
            self.state.selected_log_fields = []
        else:
            self.state.selected_log_fields = [
                name
                for name in self.state.selected_log_fields
                if name in available
            ]

        self.persist_profile()

        if fields_changed:
            self.queue_log_header()

    def set_selected_log_fields(
        self,
        fields: Sequence[str],
    ) -> None:
        with self._lock:
            self.state.selected_log_fields = [
                field
                for field in fields
                if field
            ]

            self.persist_profile()
            self.queue_log_header()

    # -------------------------------------------------------------------------
    # Runtime inputs
    # -------------------------------------------------------------------------

    def set_input_value(
        self,
        name: str,
        value: float,
    ) -> None:
        with self._lock:
            self.state.input_overrides[name] = float(value)
            self.persist_profile()

    # -------------------------------------------------------------------------
    # Formatting
    # -------------------------------------------------------------------------

    @staticmethod
    def _format_value(
        value: float | int | None,
    ) -> str:
        if value is None:
            return ''

        return f'{float(value):.6g}'

    @staticmethod
    def _format_value_dcs(
        value: float | int | None,
        *,
        width: int = 10,
        precision: int = 4,
    ) -> str:
        """Render a numeric value DCS-style: right-aligned fixed width.

        Used by the data-logger UI so columns line up visually like a
        real Distributed Control System log strip. The default
        ``width=10``, ``precision=4`` accommodates values from
        ``-9999.9999`` to ``9999.9999`` without truncation while
        keeping enough digits for typical process variables.

        ``None`` (missing reading) is rendered as a centered em-dash
        within the same column width so the alignment never breaks.
        """
        if value is None:
            return f'{"—":^{width}}'
        return f'{float(value):>{width}.{precision}f}'

    @staticmethod
    def _format_mode_value(
        mode: str | None,
    ) -> int:
        mapping = {
            'off': 0,
            'manual': 1,
            'automatic': 2,
        }

        return mapping.get(
            str(mode or '').strip().lower(),
            -1,
        )

    def _selected_fields_for_record(
        self,
        record: BridgeRecord,
    ) -> list[str]:
        return list(
            record.selected_fields
            or self.state.selected_log_fields
        )

    def _format_log_header(
        self,
        fields: Sequence[str],
        *,
        units: Sequence[str] | None = None,
        dcs_style: bool = False,
    ) -> str:
        """Header line shown above the streamed log rows.

        Two output variants:

        * Default (``dcs_style=False``) — legacy ``'realtime | step |
          sim_min | <fields>'`` shape. Kept for any non-UI consumer
          that already parses the string.
        * DCS style (``dcs_style=True``) — fixed-width prefix that
          matches :meth:`_format_log_row` when called with the same
          flag, so the column-tag header lines up exactly with the
          value cells below. When ``units`` is supplied, each field
          tag is decorated with ``[unit]`` so a glance at the
          header is enough to read the column unit.
        """
        if dcs_style:
            # Each value cell renders as ``TAG=<value:>10.4f> <unit:<4>``
            # (see ``_format_log_row``); width = len(tag) + 1 + 10
            # + 1 + 4 = len(tag) + 16. The header centers the
            # ``TAG [unit]`` label in that same width so the
            # decorated header tag sits visually above its column.
            unit_iter = list(units or [])
            decorated: list[str] = []
            for index, field in enumerate(fields):
                _, _, tag = field.partition(':')
                unit = unit_iter[index] if index < len(unit_iter) else ''
                label = f'{tag} [{unit}]' if unit else tag
                cell_width = len(tag) + 16  # mirror _format_log_row
                decorated.append(f'{label:^{cell_width}}')

            # Prefix designed to align character-for-character with
            # the row prefix written by ``_format_log_row``:
            #
            #   row:    "[2026-06-07 14:23:11.123] STEP 00001 | t=   10.2500 min  "
            #   header: "[    wall-clock time   ] STEP #step# | t=   sim_min  min "
            #
            # Each segment width is chosen to equal the corresponding
            # row-segment width.
            prefix = (
                f'[{ "wall-clock time":^23}] '   # matches "[<23-char ts>] "
                f'STEP {"#step":>5} '            # matches "STEP NNNNN "
                f'| t={"sim_min":>10} min  '     # matches "| t=mm.mmmm min  "
            )
            if decorated:
                return prefix + '| ' + ' | '.join(decorated)
            return prefix

        columns = [
            'realtime',
            'step',
            'sim_min',
        ]

        columns.extend(fields)

        return ' | '.join(columns)

    def _format_log_row(
        self,
        record: BridgeRecord,
        fields: Sequence[str],
        *,
        units: Sequence[str] | None = None,
        dcs_style: bool = False,
    ) -> str:
        """One streamed log row.

        Two output variants (same flag as
        :meth:`_format_log_header`):

        * Default — legacy ``'realtime | step | sim_min | <vals>'``
          shape, values formatted by :meth:`_format_value` (``.6g``).
        * DCS style — fixed-width:
          ``'[<wall-clock>] STEP <NNNNN> | t=<      mm.mmmm> min | TAG=<     vv.vvvv> <unit> | …'``.
          The wall-clock stamp always uses :func:`datetime.now` (not
          ``record.real_time``) so a step row produced under
          ``real_time=False`` still carries the live wall-clock time
          — that is exactly what the user asked for ("real time
          waktunya tetap muncul disana").

        ``units``, when supplied, must be the same length as
        ``fields`` and is the resolved unit string for each column
        (see :func:`app.hub.data_logger._unit_for_field`).
        """
        if dcs_style:
            from datetime import datetime
            wall = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            step_index = (
                int(record.step_index)
                if record.step_index is not None
                else 0
            )
            sim_min = (
                float(record.time_min) if record.time_min is not None else 0.0
            )
            prefix = (
                f'[{wall:^23}] '
                f'STEP {step_index:05d} | t={sim_min:>10.4f} min  '
            )

            unit_iter = list(units or [])
            cells: list[str] = []
            for index, field_name in enumerate(fields):
                scope, _, tag = field_name.partition(':')

                value: float | int | None = None
                if scope == 'input':
                    value = record.inputs.get(tag)
                elif scope == 'state':
                    value = record.states.get(tag)
                elif scope == 'output':
                    value = record.outputs.get(tag)
                elif scope == 'meta':
                    if tag == 'mode':
                        value = self._format_mode_value(
                            record.mode or self.state.controller_mode,
                        )
                    elif tag == 'time':
                        value = record.time_min
                    elif tag == 'step':
                        value = record.step_index

                unit = unit_iter[index] if index < len(unit_iter) else ''
                cell_value = self._format_value_dcs(value)
                cells.append(f'{tag}={cell_value} {unit:<4}')

            if cells:
                return prefix + '| ' + ' | '.join(cells)
            return prefix

        values = [
            record.real_time or '',
            self._format_value(record.step_index),
            self._format_value(record.time_min),
        ]

        for field_name in fields:
            scope, _, tag = field_name.partition(':')

            value: float | int | None = None

            if scope == 'input':
                value = record.inputs.get(tag)

            elif scope == 'state':
                value = record.states.get(tag)

            elif scope == 'output':
                value = record.outputs.get(tag)

            elif scope == 'meta':
                if tag == 'mode':
                    value = self._format_mode_value(
                        record.mode or self.state.controller_mode,
                    )
                elif tag == 'time':
                    value = record.time_min
                elif tag == 'step':
                    value = record.step_index

            values.append(
                self._format_value(value),
            )

        return ' | '.join(values)

    def format_record(
        self,
        record: BridgeRecord,
    ) -> str:
        if record.kind == 'status':
            stamp = f'[{record.mode}]' if record.mode else '[status]'
            return f'{stamp} {record.message}'

        if record.kind == 'header':
            return self._format_log_header(
                self._selected_fields_for_record(record),
            )

        return self._format_log_row(
            record,
            self._selected_fields_for_record(record),
        )

    # -------------------------------------------------------------------------
    # Queue
    # -------------------------------------------------------------------------

    def queue_log_header(self) -> None:
        self._records.put(
            BridgeRecord(
                kind='header',
                message='',
                real_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                mode=self.state.controller_mode,
                selected_fields=list(self.state.selected_log_fields),
            ),
        )

    def clear_logs(self) -> None:
        """Clear historical log records both in the backend appdb mirror and the bridge queue.

        This is a forceful clear used by the UI when the user wants to reset the log viewer.
        """
        with self._lock:
            try:
                # clear backend/in-memory timeseries mirror
                try:
                    self.appdb.timeseries.clear()
                except Exception:
                    self.appdb.timeseries = []
            except Exception:
                logger.exception('Failed to clear appdb.timeseries')

            # drain internal record queue
            try:
                while True:
                    self._records.get_nowait()
            except Empty:
                pass

            # push a fresh header so the UI shows current selected fields
            self.queue_log_header()

    def queue_status(
        self,
        message: str,
        *,
        mode: str | None = None,
    ) -> None:
        self._records.put(
            BridgeRecord(
                kind='status',
                message=message,
                mode=mode or self.state.controller_mode,
            ),
        )

    def drain_records(self, max_records: int = 300) -> list[BridgeRecord]:
        records: list[BridgeRecord] = []

        while len(records) < max_records:
            try:
                records.append(
                    self._records.get_nowait(),
                )
            except Empty:
                break

        return records

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self) -> None:
        # Backward-compatible start: resume by default, do not reset time.
        self._start_internal(reset=False)

    def _start_internal(self, *, reset: bool = False) -> None:
        with self._lock:
            # honor a pending fresh-start request from reset()
            if self._need_fresh_start:
                reset = True
                self._need_fresh_start = False

            if self._worker is not None and self._worker.is_alive():
                # If worker exists and is paused, resume by clearing pause event
                if self._pause_event.is_set():
                    self._pause_event.clear()
                    self.state.running = True
                    self.state.status = 'running'
                return

            self._stop_event.clear()
            self._restart_event.clear()
            self._config_changed_event.clear()

            if reset:
                self._global_sim_time = 0.0
                self.state.global_sim_time = 0.0
                self.state.last_step = -1
                self.state.last_sim_time = 0.0
                self.state.natural_stop = False

            # ensure any leftover pause flag is cleared when starting a fresh worker
            self._pause_event.clear()

            runtime_config = self._read_runtime_config()
            self._apply_runtime_config_to_legacy_cfg(runtime_config)
            self.persist_profile()

            self.state.running = True
            self.state.status = 'starting'

            self._worker = Thread(
                target=self._worker_loop,
                name='bridge-worker',
                daemon=True,
            )

            self._worker.start()

            # Wait briefly for the worker to transition to running to avoid
            # race conditions where the UI sees the worker as started but
            # it only executes a single step due to startup races.
            try:
                wait_deadline = time.time() + 1.0
                while time.time() < wait_deadline:
                    if self._worker is not None and self._worker.is_alive():
                        if self.state.status == 'running':
                            break
                    time.sleep(0.02)
            except Exception:
                pass

    def stop(self) -> None:
        self._stop_event.set()
        self._restart_event.clear()
        self._config_changed_event.set()

        worker = self._worker

        if worker is not None and worker.is_alive():
            worker.join(timeout=2.0)

        self.state.running = False
        self.state.status = 'stopped'
        self._worker = None

    def pause(self) -> None:
        """Pause the running simulation without terminating the worker thread.

        The worker will remain alive and can be resumed by calling `start()`.
        """
        # mark paused; do not join/kill thread
        self._pause_event.set()
        self._config_changed_event.set()
        self.state.running = False
        self.state.status = 'paused'

    def restart(self) -> None:
        self._restart_event.set()
        self._config_changed_event.set()

        if not self.state.running:
            self.start()

    def reset(self) -> None:
        """Stop the worker and reset simulation state to initial conditions without starting.

        This sets logical time to zero and rebuilds a fresh session so the next call to
        `start()` will run from the initial state.
        """
        with self._lock:
            # stop worker if running
            self._stop_event.set()
            # clear pause so a subsequent start doesn't immediately block
            self._pause_event.clear()
            # indicate that the next start() should create a fresh worker and reset time
            self._need_fresh_start = True

            worker = self._worker
            if worker is not None and worker.is_alive():
                worker.join(timeout=2.0)

            self._worker = None

            # clear server-side step log on reset
            self._step_log.clear()

            # reset global sim time and state markers
            self._global_sim_time = 0.0
            self.state.global_sim_time = 0.0
            self.state.last_step = -1
            self.state.last_sim_time = 0.0
            self.state.natural_stop = False

            # Reset only time-related state; preserve user-configured runtime parameters
            # (Ts, acceleration, real_time, controller_mode) so they survive a reset.
            try:
                # clear time_end so simulation won't stop immediately after restart
                self.state.time_end = float('inf')

                # persist cleared profile
                self.persist_profile()
            except Exception:
                logger.exception('Failed to reset runtime state to defaults')

            # rebuild engine/session to initial state (but do not start worker)
            try:
                engine = self._build_engine()
                session = engine.session_factory()
                self._session = session
                self._engine = engine

                # Apply scenario-specific initial states if the config supports it
                self._apply_scenario_x0(session)

                # refresh available fields and input overrides
                self._store_available_log_fields(session)
                self._seed_input_overrides()

                self.state.controller_mode = str(session.mode or self.state.controller_mode)

                # do NOT clear logs here — log clearing is controlled by the
                # dedicated UI 'Reset' in the Log filter panel. Reset should
                # only reset simulation state (time, session, inputs, etc.).
                self.state.running = False
                self.state.status = 'ready'

                self.queue_status(
                    f'Simulation reset [{self.state.scenario}]',
                    mode=str(self.state.controller_mode),
                )

            except Exception:
                logger.exception('Failed to reset simulation session.')

    # -------------------------------------------------------------------------
    # Scenario initial-state injection
    # -------------------------------------------------------------------------

    def _apply_scenario_x0(self, session: SimulationSessionProtocol) -> None:
        """Overwrite the runner's initial state vector with scenario-specific values.

        Only acts when the case config exposes ``initial_states_for_scenario``.
        Harmless for cases that don't support scenarios.
        """
        try:
            provider = getattr(self.cfg, 'initial_states_for_scenario', None)
            if not callable(provider):
                return

            scenario = str(self.state.scenario or 'operational')
            raw_states = provider(scenario)
            if not isinstance(raw_states, dict):
                return
            scenario_states: dict[str, float] = {
                str(k): float(v) for k, v in raw_states.items()
            }
            if not scenario_states:
                return

            runner = getattr(session, 'runner', None)
            if runner is None:
                return

            state_labels = list(getattr(runner.sys, 'state_labels', []))
            if not state_labels:
                return

            # Build new x0 from scenario, keeping default for any unlisted states
            new_x = list(runner.state())
            for i, label in enumerate(state_labels):
                # Normalise label the same way session._state_tag_name does
                state_tag_name_fn = getattr(session, '_state_tag_name', None)
                raw_tag = state_tag_name_fn(label) if callable(state_tag_name_fn) else label
                tag_name = str(raw_tag)
                if tag_name in scenario_states:
                    new_x[i] = float(scenario_states[tag_name])

            # Use reset instead of direct assignment to ensure internal cache is updated
            runner.reset(x0=new_x, t0=float(getattr(session, 't', 0.0)))
            session.X0 = list(new_x)

        except Exception:
            logger.exception('Failed to apply scenario x0 to session runner.')

    # -------------------------------------------------------------------------
    # Session transfer/reconfiguration
    # -------------------------------------------------------------------------

    def _transfer_session_state(
        self,
        engine: SimulationEngine,
        previous_session: SimulationSessionProtocol,
        next_session: SimulationSessionProtocol,
    ) -> None:
        try:
            flush = getattr(
                previous_session,
                'flush_timeseries_buffer',
                None,
            )

            if callable(flush):
                flush()

        except Exception:
            logger.exception(
                'Failed to flush the previous session before reconfiguration.',
            )

        try:
            if previous_session.runner is not None and next_session.runner is not None:
                engine._transfer_runner_state(  # noqa: SLF001
                    previous_session.runner,
                    next_session.runner,
                    next_session.X0,
                    float(getattr(previous_session, 't', 0.0)),
                )

        except Exception:
            logger.exception(
                'Failed to transfer runner state during bridge reconfiguration.',
            )

        try:
            engine._sync_session_time(  # noqa: SLF001
                next_session,
                float(getattr(previous_session, 't', 0.0)),
            )

        except Exception:
            logger.exception(
                'Failed to sync session time during bridge reconfiguration.',
            )

    def _rebuild_session(
        self,
        *,
        engine: SimulationEngine,
        previous_session: SimulationSessionProtocol,
    ) -> SimulationSessionProtocol:
        next_session = engine.session_factory()

        self._transfer_session_state(
            engine,
            previous_session,
            next_session,
        )

        self._session = next_session

        self._store_available_log_fields(next_session)
        self._seed_input_overrides()

        self.state.controller_mode = str(
            next_session.mode or self.state.controller_mode,
        )

        return next_session

    # -------------------------------------------------------------------------
    # Simulation helpers
    # -------------------------------------------------------------------------

    def _time_end_to_minutes(
        self,
        *,
        engine: SimulationEngine,
        raw_time_end: float,
        session: SimulationSessionProtocol,
    ) -> float:
        if not math.isfinite(raw_time_end):
            return float('inf')

        return engine._time_to_minutes(  # noqa: SLF001
            raw_time_end,
            session.time_unit,
        )

    def _is_finished(
        self,
        *,
        sim_time: float,
        time_end_minutes: float,
    ) -> bool:
        return sim_time > time_end_minutes + 1e-12

    def _would_overshoot(
        self,
        *,
        sim_time: float,
        step: float,
        time_end_minutes: float,
    ) -> bool:
        """Return True when taking the next ``step`` would advance past ``time_end_minutes``.

        Used as the pre-step gate in the worker loop so the worker
        never advances ``sample_time`` beyond the user's End Time
        even by a sub-tick. Without this, a horizon that is not an
        exact multiple of ``Ts`` (e.g. End=10 min, Ts=0.07 min) would
        let the final step land at 10.01 — visually "the sim ran
        past the End Time" — and the user would only see the block
        via the next ``_is_finished`` check, one tick too late.

        ``time_end_minutes = inf`` short-circuits to False so an
        unbounded simulation runs forever as before.
        """
        if not math.isfinite(time_end_minutes):
            return False
        # Add a tiny epsilon so a perfectly-aligned final step
        # (e.g. sample_time + step == time_end exactly) is still
        # accepted; only a real overshoot is rejected.
        return (sim_time + float(step)) > (time_end_minutes + 1e-12)

    def _refresh_session_runtime_parameters(
        self,
        session: SimulationSessionProtocol,
    ) -> None:
        refresh_runtime_parameters = getattr(
            session,
            'refresh_runtime_parameters',
            None,
        )

        if callable(refresh_runtime_parameters):
            refresh_runtime_parameters()

    def _sync_state_from_session_and_config(
        self,
        session: SimulationSessionProtocol,
        runtime_config: RuntimeConfig,
    ) -> None:
        self.state.Ts = safe_float(
            session.Ts,
            runtime_config.Ts,
            minimum=1e-12,
        )
        self.state.acceleration = runtime_config.acceleration
        self.state.real_time = runtime_config.real_time
        self.state.time_end = runtime_config.time_end
        self.state.controller_mode = runtime_config.controller_mode

    def _make_clock(
        self,
        runtime_config: RuntimeConfig,
    ) -> SimulationClock:
        accel = max(float(runtime_config.acceleration or 1.0), 1e-12)

        clock = make_clock(
            real_time=runtime_config.real_time,
            acceleration=accel,
        )

        clock.reset()

        return clock

    def _run_one_step(
        self,
        *,
        engine: SimulationEngine,
        session: SimulationSessionProtocol,
        step_index: int,
        sample_time: float,
    ) -> None:
        engine._sync_session_time(  # noqa: SLF001
            session,
            sample_time,
        )

        real_time_stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        overrides = dict(self.state.input_overrides or {})

        session.step(
            external_inputs=overrides if overrides else None,
        )

        self.state.last_step = step_index
        self.state.last_sim_time = sample_time
        self.state.status = 'running'

        _step_entry = {
            'step_index': step_index,
            'time_min': sample_time,
            'inputs': dict(getattr(session, 'last_inputs', {}) or {}),
            'states': dict(getattr(session, 'last_states', {}) or {}),
            'outputs': dict(getattr(session, 'last_outputs', {}) or {}),
        }
        # Persist in server-side step log (for replay on new/refreshed connections)
        self._step_log.append(_step_entry)

        self._records.put(
            BridgeRecord(
                kind='step',
                message='',
                step_index=step_index,
                time_min=sample_time,
                real_time=real_time_stamp,
                mode=str(session.mode or self.state.controller_mode),
                inputs=_step_entry['inputs'],
                states=_step_entry['states'],
                outputs=_step_entry['outputs'],
                selected_fields=list(self.state.selected_log_fields or []),
            ),
        )

    def _flush_session(
        self,
        session: SimulationSessionProtocol,
    ) -> None:
        try:
            flush = getattr(
                session,
                'flush_timeseries_buffer',
                None,
            )

            if callable(flush):
                flush()

        except Exception:
            logger.exception(
                'Failed to flush session timeseries buffer.',
            )

    # -------------------------------------------------------------------------
    # Worker loop
    # -------------------------------------------------------------------------

    def _worker_loop(self) -> None:
        engine = self._build_engine()
        self._engine = engine

        runtime_config = self._read_runtime_config()
        self._apply_runtime_config_to_legacy_cfg(runtime_config)

        session = engine.session_factory()
        _set_worker_priority_low()

        # (startup runtime params logging removed)

        if session.runner is None:
            self.queue_status(
                'Controller mode is unrecognized; nothing to simulate.',
                mode=session.mode,
            )

            self.state.running = False
            self.state.status = 'idle'
            self._worker = None
            return

        self._session = session

        self._store_available_log_fields(session)
        self._seed_input_overrides()

        # Apply scenario initial conditions if starting from the beginning (t=0).
        if abs(self._global_sim_time) < 1e-12:
            self._apply_scenario_x0(session)

        self.state.controller_mode = str(
            session.mode or self.state.controller_mode,
        )

        clock = self._make_clock(runtime_config)
        pacing_signature = self._pacing_signature(runtime_config)

        # The step counter is a bridge-level, monotonically increasing value.
        # On a fresh worker (e.g. after a previous run hit time_end) we must
        # continue from the previous run's last step, otherwise the data
        # logger and performance plot will silently drop every new step
        # because their watermark checks assume a global counter.
        step_index = max(int(getattr(self.state, 'last_step', -1)) + 1, 0)
        sample_time = float(self._global_sim_time)

        # If time_end is accidentally set to a very small finite value (<= Ts)
        # at initial startup, ignore it to avoid the worker exiting after a
        # single step. This avoids stale/saved profile values causing a one-step
        # run. Only do this when starting from global time zero.
        try:
            parsed_time_end = self.parse_time_end_value(runtime_config.time_end)
            if (
                math.isfinite(parsed_time_end)
                and float(parsed_time_end) <= float(session.Ts) + 1e-12
                and abs(self._global_sim_time) < 1e-12
            ):
                runtime_config = RuntimeConfig(
                    controller_mode=runtime_config.controller_mode,
                    Ts=runtime_config.Ts,
                    acceleration=runtime_config.acceleration,
                    real_time=runtime_config.real_time,
                    time_end=float('inf'),
                )
                self._apply_runtime_config_to_legacy_cfg(runtime_config)
                self.persist_profile()
                self.queue_status('Ignored tiny time_end on startup (treated as no end).', mode=session.mode)
                time_end_minutes = float('inf')
            else:
                time_end_minutes = self._time_end_to_minutes(
                    engine=engine,
                    raw_time_end=runtime_config.time_end,
                    session=session,
                )
        except Exception:
            time_end_minutes = self._time_end_to_minutes(
                engine=engine,
                raw_time_end=runtime_config.time_end,
                session=session,
            )

        self.queue_status(
            (
                f'Starting simulation: '
                f'mode={session.mode}, '
                f'real_time={runtime_config.real_time}, '
                f'acceleration={runtime_config.acceleration}, '
                f'time_end={runtime_config.time_end}'
            ),
            mode=session.mode,
        )

        self.state.status = 'running'

        try:
            while not self._stop_event.is_set():
                # handle pause: block here while paused
                if self._pause_event.is_set():
                    self.state.status = 'paused'
                    self.state.running = False
                    while self._pause_event.is_set() and not self._stop_event.is_set():
                        time.sleep(0.1)

                    if self._stop_event.is_set():
                        break

                    # resumed
                    self.state.running = True
                    self.state.status = 'running'
                runtime_config = self._read_runtime_config()
                self._apply_runtime_config_to_legacy_cfg(runtime_config)

                new_pacing_signature = self._pacing_signature(runtime_config)

                if self._config_changed_event.is_set():
                    self._config_changed_event.clear()

                    if new_pacing_signature != pacing_signature:
                        clock = self._make_clock(runtime_config)
                        pacing_signature = new_pacing_signature

                        # pacing update applied (no debug message)
                        continue

                self._refresh_session_runtime_parameters(session)

                self._sync_state_from_session_and_config(
                    session,
                    runtime_config,
                )

                raw_time_end = runtime_config.time_end

                time_end_minutes = self._time_end_to_minutes(
                    engine=engine,
                    raw_time_end=raw_time_end,
                    session=session,
                )

                # Two-stage finish gate:
                #
                #  1. ``_is_finished`` — we are ALREADY past the end
                #     (e.g. user reduced time_end below the current
                #     sim time mid-run). Break immediately.
                #  2. ``_would_overshoot`` — the NEXT step would
                #     advance past the end. Break before stepping,
                #     never let ``sample_time`` exceed the user's
                #     End Time even by a sub-tick.
                #
                # This is the fix for the "simulasi tidak boleh
                # berjalan melebihi waktu yang yang diset di time
                # end" requirement.
                if self._is_finished(
                    sim_time=sample_time,
                    time_end_minutes=time_end_minutes,
                ) or self._would_overshoot(
                    sim_time=sample_time,
                    step=session.Ts,
                    time_end_minutes=time_end_minutes,
                ):
                    break

                if self._restart_event.is_set():
                    self._restart_event.clear()
                    self._config_changed_event.clear()

                    previous_session = session

                    session = self._rebuild_session(
                        engine=engine,
                        previous_session=previous_session,
                    )

                    runtime_config = self._read_runtime_config()
                    self._apply_runtime_config_to_legacy_cfg(runtime_config)

                    clock = self._make_clock(runtime_config)
                    pacing_signature = self._pacing_signature(runtime_config)

                    # reconfiguration applied (no debug message)
                    continue

                current_global_mode = str(
                    self.cfg.CONTROLLER_MODE.get('Mode', ''),
                ).strip()

                session_mode = str(
                    getattr(session, 'mode', ''),
                ).strip()

                if (
                    current_global_mode
                    and current_global_mode.lower() != session_mode.lower()
                ):
                    previous_session = session

                    session = self._rebuild_session(
                        engine=engine,
                        previous_session=previous_session,
                    )

                    runtime_config = self._read_runtime_config()
                    self._apply_runtime_config_to_legacy_cfg(runtime_config)

                    clock = self._make_clock(runtime_config)
                    pacing_signature = self._pacing_signature(runtime_config)

                    self.queue_status(
                        (
                            f'Switching simulation session mode: '
                            f'from={session_mode} '
                            f'to={current_global_mode}'
                        ),
                        mode=current_global_mode,
                    )

                    self.state.controller_mode = current_global_mode

                    continue

                step_due = clock.wait_next_step(
                    float(session.Ts),
                    should_interrupt=lambda: (
                        self._stop_event.is_set()
                        or self._restart_event.is_set()
                        or self._config_changed_event.is_set()
                    ),
                )

                if not step_due:
                    continue

                self._run_one_step(
                    engine=engine,
                    session=session,
                    step_index=step_index,
                    sample_time=sample_time,
                )
                # Yield the GIL so the UI/main thread gets a chance to run
                # even when the engine is running at high acceleration.
                time.sleep(0)
                sample_time += float(session.Ts)

                self._global_sim_time = sample_time
                self.state.global_sim_time = self._global_sim_time

                step_index += 1

                if self._is_finished(
                    sim_time=sample_time,
                    time_end_minutes=time_end_minutes,
                ):
                    break

            self.queue_status(
                f'Simulation finished: records={len(self.appdb.timeseries)}',
                mode=str(session.mode or self.state.controller_mode),
            )

            self.state.status = 'complete'

        except KeyboardInterrupt:
            self.queue_status(
                'Simulation stopped by user.',
                mode=str(session.mode or self.state.controller_mode),
            )

            self.state.status = 'stopped'

        except Exception as exc:
            logger.exception('Bridge worker failed.')

            self.queue_status(
                f'Bridge worker failed: {exc}',
                mode=str(session.mode or self.state.controller_mode),
            )

            self.state.status = 'error'

        finally:
            # Record whether the worker exited naturally (reached time_end)
            # or was interrupted/errored. Data Logger and Performance Plot
            # read this flag in their reset-detection branch so a "continue"
            # does not wipe the chart/log.
            self.state.natural_stop = (
                self.state.status == 'complete'
            )

            self._flush_session(session)

            self.state.running = False
            self._worker = None
            self._session = None
            self._engine = None
