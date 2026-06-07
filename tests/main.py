# engine_root/main.py

from __future__ import annotations

import math
import os
import time
from collections import deque
from datetime import datetime
from typing import Any

from nicegui import app, ui

from gateway.bridge import Bridge as GenericBridge
from gateway.config_registry import get_case_config, list_case_configs
from gateway.bridge_support import BridgeRecord


BRIDGE_REGISTRY: dict[str, GenericBridge] = {}


def get_bridge(profile_key: str, case_name: str) -> GenericBridge:
    """Return an existing bridge for the profile, or create a new one."""
    bridge = BRIDGE_REGISTRY.get(profile_key)

    if bridge is None:
        bridge = GenericBridge(case_name=case_name)
        BRIDGE_REGISTRY[profile_key] = bridge

    return bridge


def shutdown_bridges() -> None:
    """Stop all active bridges on application shutdown."""
    for bridge in BRIDGE_REGISTRY.values():
        bridge.stop()


app.on_shutdown(shutdown_bridges)


@ui.page('/')
def index() -> None:
    browser_id = str(app.storage.browser.get('id', 'default-browser'))

    available_cases = list_case_configs() or []
    default_case = available_cases[0] if available_cases else 'sthr'

    selected_case = str(
        app.storage.user.get('active_case', default_case),
    ).strip().lower()

    if selected_case not in available_cases:
        selected_case = default_case

    case_cfg = get_case_config(selected_case)
    case_runtime = getattr(case_cfg, 'CASE_RUNTIME', None)

    case_default_mode = str(getattr(case_runtime, 'default_mode', 'off'))
    case_default_mode_display = (
        case_default_mode
        if any(ch.isupper() for ch in case_default_mode)
        else case_default_mode.capitalize()
    )

    case_default_unit = case_cfg.normalize_time_unit(
        getattr(
            case_runtime,
            'time_unit',
            case_cfg.SIMULATION_PARAMS.get('time_unit', 'minutes'),
        ),
    )

    profile_key = f'{GenericBridge.profile_storage_prefix}:{selected_case}:{browser_id}'
    profile = app.storage.user.setdefault(profile_key, {})

    bridge = get_bridge(profile_key, selected_case)
    bridge.bind_profile(browser_id, profile)

    if not str(bridge.state.controller_mode or '').strip():
        bridge.state.controller_mode = case_default_mode_display

    # Ensure initial runtime configuration is applied so the first Run works immediately.
    bridge.apply_runtime_configuration(restart_if_needed=False)

    ui.page_title(f'{selected_case.upper()} Simulation')

    def record_info(message: str, *, mode: str | None = None) -> None:
        try:
            bridge.queue_status(message, mode=mode or bridge.state.controller_mode)
        except Exception:
            pass

    def event_value(event: Any, fallback: Any = None) -> Any:
        """Extract value from a NiceGUI event object."""
        value = getattr(event, 'value', None)
        if value is not None:
            return value

        args = getattr(event, 'args', None)

        if isinstance(args, dict):
            for key in ('value', 'newValue', 'modelValue'):
                if args.get(key) is not None:
                    return args[key]

            if len(args) == 1:
                return next(iter(args.values()))

        elif args is not None:
            return args

        return fallback

    record_info('Login')

    with ui.column().classes('w-full max-w-6xl mx-auto gap-4 p-4'):
        ui.label(f'{selected_case.upper()} Simulation').classes('text-h4 font-bold')

        with ui.row().classes('items-end gap-3 w-full'):

            def on_case_change(event: Any) -> None:
                chosen_value = event_value(event, case_selector.value)
                chosen = str(chosen_value or selected_case).strip().lower()

                if chosen not in available_cases:
                    chosen = default_case

                app.storage.user['active_case'] = chosen

                ui.timer(
                    0.05,
                    lambda: ui.run_javascript("location.href='/';"),
                    once=True,
                )

            case_selector = ui.select(
                available_cases,
                label='Case',
                value=selected_case,
                on_change=on_case_change,
            ).classes('w-48')

        ui.label().bind_text_from(
            bridge.state,
            'status',
            backward=lambda value: f'Status: {value}',
        )

        # Forward-declared references used by reset/chart helpers.
        plot_ref: dict[str, Any] = {'step_history': None}
        ui_refs: dict[str, Any] = {
            'end_input': None,
            'strip_chart_fn': None,
        }
        log_ref: dict[str, Any] = {'log': None}

        # Updated after step_history is initialized.
        _watermark: list[int] = [-1]

        def _do_reset_simulation() -> None:
            try:
                bridge.reset()

                end_input_ref = ui_refs.get('end_input')
                if end_input_ref is not None:
                    end_input_ref.value = ''

                history = plot_ref.get('step_history')
                if history is not None:
                    history.clear()
                    _watermark[0] = -1

                strip_chart_fn = ui_refs.get('strip_chart_fn')
                if strip_chart_fn is not None:
                    strip_chart_fn()

                record_info('Simulation reset (UI)')
                ui.notify('Simulation reset — End Time cleared', color='positive')

            except Exception as exc:
                ui.notify(f'Failed to reset simulation: {exc}', color='negative')

        with ui.card().classes('w-full'):
            ui.label('Runtime Manager').classes('text-h6')

            def on_controller_mode_change(event: Any) -> None:
                supported_modes = bridge.supported_modes()
                fallback_mode = supported_modes[0] if supported_modes else case_default_mode_display

                bridge.state.controller_mode = str(
                    event_value(event, fallback_mode) or fallback_mode,
                )

                bridge.apply_runtime_configuration(restart_if_needed=False)
                record_info(f'Controller mode set to: {bridge.state.controller_mode}')

            def on_acceleration_change(event: Any) -> None:
                current_value = event_value(event, None)

                bridge.state.acceleration = (
                    1.0
                    if current_value is None
                    else max(float(current_value), 1e-12)
                )

                bridge.apply_runtime_configuration(restart_if_needed=False)
                record_info(f'Acceleration set to: {bridge.state.acceleration}')

            def on_real_time_change(event: Any) -> None:
                bridge.state.real_time = bool(event_value(event, bridge.state.real_time))
                bridge.apply_runtime_configuration(restart_if_needed=False)
                record_info(f'Real Time set to: {bridge.state.real_time}')

            def on_units_change(event: Any) -> None:
                selected_unit = str(event_value(event, units_select.value) or units_select.value)

                try:
                    step_input.value = case_cfg.from_minutes(
                        float(bridge.state.Ts),
                        selected_unit,
                    )
                except Exception:
                    step_input.value = case_cfg.from_minutes(
                        float(bridge.state.Ts),
                        units_select.value,
                    )

                raw_end = bridge.time_end_to_text()
                if raw_end is None or raw_end == '':
                    end_input.value = ''
                else:
                    try:
                        end_input.value = f'{case_cfg.from_minutes(float(raw_end), selected_unit):g}'
                    except Exception:
                        end_input.value = raw_end

                try:
                    bridge.state.global_sim_time = bridge.state.global_sim_time
                except Exception:
                    pass

                record_info(f'Units changed to: {selected_unit}')

            # Row 1: time settings
            with ui.row().classes('items-end gap-4 w-full flex-wrap'):
                units_select = ui.select(
                    ['seconds', 'minutes', 'hours'],
                    label='Units',
                    value=case_default_unit,
                    on_change=on_units_change,
                ).classes('w-32')

                step_display_value = case_cfg.from_minutes(
                    float(bridge.state.Ts),
                    case_default_unit,
                )

                step_input = ui.number(
                    'Step Size',
                    value=step_display_value,
                    format='%.4f',
                    min=0.0001,
                    step=0.001,
                ).classes('w-36')

                def _commit_step_input(_event: Any = None, element: Any = step_input) -> None:
                    value = element.value

                    if value is not None and not (
                        isinstance(value, str) and not value.strip()
                    ):
                        try:
                            minutes = case_cfg.to_minutes(float(value), units_select.value)
                            bridge.state.Ts = max(float(minutes), 1e-12)
                        except Exception:
                            pass

                    bridge.apply_runtime_configuration(restart_if_needed=True)

                step_input.on('blur', _commit_step_input)
                step_input.on('keydown.enter', _commit_step_input)

                raw_end = bridge.time_end_to_text()
                if raw_end is None or raw_end == '':
                    end_value_display = ''
                else:
                    try:
                        end_value_display = f'{case_cfg.from_minutes(float(raw_end), case_default_unit):g}'
                    except Exception:
                        end_value_display = raw_end

                end_input = ui.input(
                    'End Time',
                    value=end_value_display,
                    placeholder='empty / Inf = no end',
                ).classes('w-40')

                ui_refs['end_input'] = end_input

                def _commit_end_input(_event: Any = None, element: Any = end_input) -> None:
                    value = element.value

                    if value is None or (
                        isinstance(value, str) and not str(value).strip()
                    ):
                        bridge.set_time_end_from_ui(value)
                    else:
                        try:
                            minutes = case_cfg.to_minutes(float(value), units_select.value)
                            bridge.set_time_end_from_ui(minutes)
                        except Exception:
                            bridge.set_time_end_from_ui(value)

                    bridge.apply_runtime_configuration(restart_if_needed=False)

                end_input.on('blur', _commit_end_input)
                end_input.on('keydown.enter', _commit_end_input)

                with ui.column().classes('gap-0'):
                    ui.label('Current Time').classes('text-xs text-gray-500')

                    ui.label().classes('text-sm font-mono').bind_text_from(
                        bridge.state,
                        'global_sim_time',
                        backward=lambda value: (
                            f'{case_cfg.from_minutes(float(value) if value is not None else 0.0, units_select.value):.4f}'
                            f' {units_select.value}'
                        ),
                    )

            # Row 2: pacing
            with ui.row().classes('items-center gap-6 w-full flex-wrap'):
                ui.number(
                    'Acceleration',
                    value=bridge.state.acceleration,
                    format='%.2f',
                    min=0.000001,
                    max=1000.0,
                    step=0.1,
                    on_change=on_acceleration_change,
                ).bind_value(
                    bridge.state,
                    'acceleration',
                ).classes('w-36')

                ui.checkbox(
                    'Real Time',
                    value=bridge.state.real_time,
                    on_change=on_real_time_change,
                ).bind_value(
                    bridge.state,
                    'real_time',
                )

                ui.label(
                    '1 = real-time  ·  >1 faster (max 1000×)  ·  <1 slower  ·  Real Time ignores acceleration',
                ).classes('text-xs text-gray-500')

            # Row 3: controller loop modes
            loop_order = getattr(case_cfg, 'LOOP_ORDER', None)

            # References to UI select elements.
            # These are needed so scenario changes update the visible dropdowns
            # immediately, not only the backend state.
            loop_mode_select_refs: dict[str, Any] = {}
            controller_mode_select_ref: dict[str, Any] = {'select': None}

            def _normalize_mode_for_ui(mode: str) -> str:
                """
                Normalize mode text so it matches one of bridge.supported_modes().

                Examples:
                - 'off'       -> 'Off'
                - 'automatic' -> 'Automatic'
                - 'manual'    -> 'Manual'

                NiceGUI select values should match the available option values.
                """
                raw_mode = str(mode or '').strip()
                supported_modes = bridge.supported_modes()

                for supported_mode in supported_modes:
                    if str(supported_mode).strip().lower() == raw_mode.lower():
                        return str(supported_mode)

                return str(supported_modes[0]) if supported_modes else raw_mode

            def _default_loop_mode_for_scenario(scenario_key: str) -> str:
                """
                Define default controller/loop mode for each scenario.

                Required behavior:
                - Start-up         -> Off
                - Normal Operation -> Automatic
                - Shutdown         -> Automatic
                """
                scenario_key = str(scenario_key or '').strip().lower()

                default_modes = {
                    'startup': 'Off',
                    'operational': 'Automatic',
                    'shutdown': 'Automatic',
                }

                return _normalize_mode_for_ui(
                    default_modes.get(scenario_key, 'Automatic'),
                )

            def _apply_mode_to_controller_and_loops(mode: str) -> None:
                """
                Apply mode to:
                - global controller mode
                - all loop modes
                - visible multi-loop dropdowns
                - visible single controller dropdown, if present
                """
                normalized_mode = _normalize_mode_for_ui(mode)

                bridge.state.controller_mode = normalized_mode

                current_loop_order = getattr(case_cfg, 'LOOP_ORDER', []) or []

                if current_loop_order:
                    for loop_id in current_loop_order:
                        bridge.state.loop_modes[loop_id] = normalized_mode

                        loop_select = loop_mode_select_refs.get(loop_id)
                        if loop_select is not None:
                            try:
                                loop_select.value = normalized_mode
                            except Exception:
                                pass

                controller_select = controller_mode_select_ref.get('select')
                if controller_select is not None:
                    try:
                        controller_select.value = normalized_mode
                    except Exception:
                        pass

            if loop_order and len(loop_order) > 1:
                with ui.row().classes('items-end gap-3 w-full flex-wrap'):
                    ui.label('Loop Modes').classes('text-sm font-semibold self-center')

                    def _make_loop_handler(loop_name: str):
                        def _on_change(event: Any) -> None:
                            new_mode = _normalize_mode_for_ui(
                                str(event_value(event, 'Automatic') or 'Automatic'),
                            )

                            bridge.state.loop_modes[loop_name] = new_mode
                            bridge.apply_runtime_configuration(restart_if_needed=True)
                            bridge.persist_profile()

                            record_info(f'{loop_name} mode: {new_mode}')

                        return _on_change

                    for loop in loop_order:
                        loop_select = ui.select(
                            bridge.supported_modes(),
                            label=f'{loop}',
                            value=_normalize_mode_for_ui(
                                bridge.state.loop_modes.get(
                                    loop,
                                    bridge.state.controller_mode or 'Automatic',
                                ),
                            ),
                            on_change=_make_loop_handler(loop),
                        ).classes('w-36')

                        loop_mode_select_refs[loop] = loop_select

            else:
                with ui.row().classes('items-end gap-3 w-full'):
                    controller_select = ui.select(
                        bridge.supported_modes(),
                        label='Controller mode',
                        value=_normalize_mode_for_ui(
                            bridge.state.controller_mode or 'Automatic',
                        ),
                        on_change=on_controller_mode_change,
                    ).bind_value(
                        bridge.state,
                        'controller_mode',
                    ).classes('w-44')

                    controller_mode_select_ref['select'] = controller_select

            @ui.refreshable
            def mode_settings_panel() -> None:
                """Placeholder for optional mode-specific settings.

                This keeps calls to mode_settings_panel.refresh() safe.
                Extend this function if a case needs additional mode controls.
                """
                pass

            mode_settings_panel()

            # Row 4: scenario
            scenario_order = getattr(case_cfg, 'SCENARIO_ORDER', None)

            if scenario_order:
                scenario_labels = {
                    'startup': 'Start-up',
                    'operational': 'Normal Operation',
                    'shutdown': 'Shutdown',
                }

                scenario_options = [
                    scenario_labels.get(scenario, scenario.capitalize())
                    for scenario in scenario_order
                ]

                # Robust UI label -> internal scenario key mapping.
                # This supports both known and custom scenarios.
                scenario_value_to_key = {
                    scenario_labels.get(key, key.capitalize()): key
                    for key in scenario_order
                }

                def _on_scenario_change(event: Any) -> None:
                    selected_label = str(
                        event_value(event, 'Normal Operation') or 'Normal Operation',
                    )

                    scenario_key = scenario_value_to_key.get(
                        selected_label,
                        'operational',
                    )

                    scenario_loop_mode = _default_loop_mode_for_scenario(
                        scenario_key,
                    )

                    # Store selected scenario.
                    bridge.state.scenario = scenario_key

                    bridge.state.input_overrides = {}

                    # Apply scenario-based mode immediately.
                    #
                    # Behavior:
                    # - startup      -> Off
                    # - operational  -> Automatic
                    # - shutdown     -> Automatic
                    _apply_mode_to_controller_and_loops(scenario_loop_mode)

                    # Apply runtime configuration before reset so the rebuilt
                    # session reads the latest controller mode and loop modes.
                    bridge.apply_runtime_configuration(restart_if_needed=False)

                    # Refresh optional mode-specific panel.
                    mode_settings_panel.refresh()

                    # Reset simulation so scenario-specific initial state x0 is applied.
                    _do_reset_simulation()

                    # Persist scenario and mode changes.
                    bridge.persist_profile()

                    record_info(
                        f'Scenario set to: {selected_label} '
                        f'(all modes set to {scenario_loop_mode})',
                    )

                current_scenario = str(
                    bridge.state.scenario or 'operational',
                ).strip().lower()

                current_scenario_label = scenario_labels.get(
                    current_scenario,
                    current_scenario.capitalize(),
                )

                if current_scenario_label not in scenario_options:
                    current_scenario_label = (
                        scenario_labels.get('operational', 'Normal Operation')
                        if 'operational' in scenario_order
                        else scenario_options[0]
                    )

                with ui.row().classes('items-center gap-4 w-full flex-wrap'):
                    ui.label('Scenario').classes('text-sm font-semibold self-center')

                    ui.select(
                        scenario_options,
                        label='Initial condition',
                        value=current_scenario_label,
                        on_change=_on_scenario_change,
                    ).classes('w-56')

                    ui.label(
                        'Applied on Reset — sets x₀ for the next simulation run.',
                    ).classes('text-xs text-gray-500')            

            # Row 5: action buttons
            with ui.row().classes('gap-2 mt-2'):
                ui.button(
                    'Run',
                    on_click=lambda: (
                        bridge.start(),
                        record_info('Run requested'),
                    ),
                ).props('color=primary icon=play_arrow')

                ui.button(
                    'Stop',
                    on_click=lambda: (
                        bridge.pause(),
                        record_info('Simulation paused'),
                    ),
                ).props('outline icon=stop')

                ui.button(
                    'Reset',
                    on_click=_do_reset_simulation,
                ).props('outline icon=restart_alt')

        last_available_fields = list(bridge.state.available_log_fields)
        printed_header: str | None = None

        def clear_ui_log_and_reset_selection() -> None:
            bridge.set_selected_log_fields(
                [
                    field
                    for field in bridge.state.available_log_fields
                    if field.startswith('output:')
                ],
            )

            bridge.clear_logs()

            try:
                log_widget = log_ref.get('log')
                if log_widget is not None:
                    log_widget.clear()
            except Exception:
                pass

            ui.notify('Logs cleared', color='positive')

        def _is_flow_field(field_name: str) -> bool:
            """
            Detect if field is a flow-rate field that needs per-hour scaling.

            Flow rate fields:
            - FSP setpoint values
            - f_ plant flow state variables
            - actuator flow outputs ending with .F
            """
            _, _, tag = field_name.partition(':')
            tag_upper = tag.upper()

            return (
                tag_upper.startswith('FSP')
                or tag_upper.startswith('F_')
                or 'F_' in tag_upper
                or tag_upper.endswith('.F')
            )

        def _build_field_groups(
            fields: list[str],
            loop_order_value: list[str] | None,
            loop_signal_map: dict | None,
        ) -> dict[str, list[str]]:
            """Partition fields into groups by controller loop."""
            if (
                not loop_order_value
                or not loop_signal_map
                or len(loop_order_value) <= 1
            ):
                return {'All': list(fields)}

            loop_prefixes: dict[str, list[str]] = {}
            loop_plant_mvs: dict[str, str] = {}

            for loop_id, meta in loop_signal_map.items():
                prefixes = [
                    meta[key]
                    for key in ('controller', 'setpoint', 'actuator')
                    if meta.get(key)
                ]

                loop_letter = loop_id[0]
                loop_num = loop_id.split('-', 1)[1]
                prefixes.append(f'{loop_letter}T-{loop_num}')

                loop_prefixes[loop_id] = prefixes
                loop_plant_mvs[loop_id] = meta.get('plant_mv', '')

            groups: dict[str, list[str]] = {
                loop: []
                for loop in loop_order_value
            }
            groups['Plant'] = []
            groups['Meta'] = []

            for field in fields:
                scope, _, tag = field.partition(':')

                if scope == 'meta':
                    groups['Meta'].append(field)
                    continue

                for loop_id in loop_order_value:
                    if tag == loop_plant_mvs.get(loop_id, ''):
                        groups[loop_id].append(field)
                        break
                else:
                    for loop_id in loop_order_value:
                        if any(
                            tag.startswith(f'{prefix}.') or tag == prefix
                            for prefix in loop_prefixes[loop_id]
                        ):
                            groups[loop_id].append(field)
                            break
                    else:
                        groups['Plant'].append(field)

            return groups

        def _replay_log_from_history(fields: list[str]) -> None:
            """Clear log widget and re-populate it from step_history."""
            try:
                log_widget = log_ref.get('log')
                if log_widget is None:
                    return

                log_widget.clear()

                if not fields:
                    return

                header = bridge._format_log_header(fields)
                if header:
                    log_widget.push(header)

                history = plot_ref.get('step_history')
                if not history:
                    return

                for entry in history:
                    if not isinstance(entry, dict):
                        continue

                    record = BridgeRecord(
                        kind='step',
                        message='',
                        step_index=entry.get('step_index'),  # type: ignore[arg-type]
                        time_min=entry.get('time_min'),      # type: ignore[arg-type]
                        inputs=entry.get('inputs', {}),
                        states=entry.get('states', {}),
                        outputs=entry.get('outputs', {}),
                    )

                    row = bridge._format_log_row(record, fields)
                    if row:
                        log_widget.push(row)

            except Exception:
                pass

        def _toggle_log_field(field_name: str, enabled: bool) -> None:
            current = list(bridge.state.selected_log_fields)

            if enabled:
                if field_name not in current:
                    current.append(field_name)
            else:
                current = [
                    field
                    for field in current
                    if field != field_name
                ]

            bridge.set_selected_log_fields(current)
            _replay_log_from_history(current)
            _render_columns_card.refresh()

        def _render_input_field(input_name: str) -> None:
            """Render one runtime input field."""
            backend_value = float(bridge.state.input_overrides.get(input_name, 0.0))
            is_flow = _is_flow_field(f'input:{input_name}')

            display_value = backend_value * 3600.0 if is_flow else backend_value
            unit_label = ' (per-hour)' if is_flow else ''
            display_format = '%.2f' if is_flow else '%.4f'

            number_input = ui.number(
                f'{input_name}{unit_label}',
                value=display_value,
                format=display_format,
            ).classes('w-56')

            def _commit_input(
                _event: Any = None,
                name: str = input_name,
                element: Any = number_input,
                is_flow_field: bool = is_flow,
            ) -> None:
                try:
                    display_val = float(element.value) if element.value is not None else 0.0
                    backend_val = display_val / 3600.0 if is_flow_field else display_val
                except Exception:
                    display_val = 0.0
                    backend_val = 0.0

                bridge.set_input_value(name, backend_val)

                suffix = ' per-hour' if is_flow_field else ''
                record_info(f'Input {name} set to {display_val}{suffix}')

            number_input.on('blur', _commit_input)
            number_input.on('keydown.enter', _commit_input)

        @ui.refreshable
        def dynamic_runtime_panels() -> None:
            ui.label('Runtime inputs').classes('text-h6')

            ui.label(
                'These values are merged into the next simulation step as external inputs. '
                'Flow values are shown in per-hour units for clarity.',
            ).classes('text-sm text-gray-600')

            runtime_loop_order = getattr(case_cfg, 'LOOP_ORDER', None)
            runtime_signal_map = getattr(case_cfg, 'LOOP_SIGNAL_MAP', None)

            input_fields = sorted(
                field
                for field in bridge.state.available_log_fields
                if field.startswith('input:')
            )

            groups = _build_field_groups(
                input_fields,
                runtime_loop_order,
                runtime_signal_map,
            )

            for group_name, group_fields in groups.items():
                if not group_fields:
                    continue

                if group_name == 'All':
                    with ui.row().classes('w-full flex-wrap gap-4'):
                        for field in group_fields:
                            _render_input_field(field.removeprefix('input:'))
                else:
                    if runtime_signal_map and group_name in runtime_signal_map:
                        current_mode = bridge.state.loop_modes.get(group_name, 'automatic')
                        header = f'{group_name}  •  {current_mode}'
                    else:
                        header = group_name

                    with ui.expansion(header, value=True).classes('w-full border rounded'):
                        with ui.row().classes('flex-wrap gap-4 p-2'):
                            for field in group_fields:
                                _render_input_field(field.removeprefix('input:'))

        dynamic_runtime_panels()

        step_history: deque[dict] = deque(bridge._step_log, maxlen=6000)
        plot_ref['step_history'] = step_history

        _watermark[0] = max(
            (
                entry['step_index']
                for entry in step_history
                if entry.get('step_index') is not None
            ),
            default=-1,
        )

        selected_plot_fields: list[str] = []

        def _scale_value(value: float | None, field_name: str) -> float | None:
            """Scale flow values from per-second to per-hour."""
            if value is None:
                return None

            try:
                scaled = float(value)
            except Exception:
                return value

            if _is_flow_field(field_name):
                scaled *= 3600.0

            return scaled

        def _extract_plot_value(step_entry: dict, field_name: str) -> float | None:
            scope, _, tag = field_name.partition(':')

            if scope == 'input':
                value = step_entry.get('inputs', {}).get(tag)
            elif scope == 'state':
                value = step_entry.get('states', {}).get(tag)
            elif scope == 'output':
                value = step_entry.get('outputs', {}).get(tag)
            elif scope == 'meta' and tag == 'time':
                value = step_entry.get('time_min')
            elif scope == 'meta' and tag == 'step':
                value = step_entry.get('step_index')
            else:
                value = None

            return _scale_value(value, field_name)

        plot_field_controls: dict[str, Any] = {}

        def _sync_plot_field_controls() -> None:
            for field_name, control in plot_field_controls.items():
                try:
                    control.value = field_name in selected_plot_fields
                except Exception:
                    pass

        def _set_selected_plot_fields(chosen: list[str]) -> None:
            nonlocal selected_plot_fields

            if len(chosen) > 4:
                chosen = chosen[:4]
                ui.notify('Maximum 4 plot fields allowed', color='warning')

            selected_plot_fields = chosen
            _sync_plot_field_controls()

            try:
                selected_plot_label.text = ', '.join(selected_plot_fields or ['(none)'])
            except Exception:
                pass

            record_info(
                'Plot fields changed: '
                + ', '.join(selected_plot_fields or ['(none)']),
            )

            ui.timer(0.01, _render_strip_chart, once=True)

        def _toggle_plot_field(
            field_name: str,
            enabled: bool,
            control: Any,
        ) -> None:
            current = list(selected_plot_fields)

            if enabled:
                if field_name in current:
                    return

                if len(current) >= 4:
                    ui.notify('Maximum 4 plot fields allowed', color='warning')

                    try:
                        control.value = False
                    except Exception:
                        pass

                    return

                current.append(field_name)

            else:
                current = [
                    field
                    for field in current
                    if field != field_name
                ]

            _set_selected_plot_fields(current)

        with ui.card().classes('w-full'):
            ui.label('Stripchart (Real-time)').classes('text-h6')

            ui.label(
                'Choose up to 4 signals. The chart updates as new simulation records arrive.',
            ).classes('text-sm text-gray-600')

            ui.label('Quick pick signals (max 4)').classes('text-sm font-medium')

            def _add_plot_checkbox(field_name: str) -> None:
                control = ui.checkbox(
                    field_name,
                    value=field_name in selected_plot_fields,
                    on_change=lambda event, name=field_name: _toggle_plot_field(
                        name,
                        bool(event_value(event, False)),
                        plot_field_controls.get(name),
                    ),
                ).classes('min-w-[220px]')

                plot_field_controls[field_name] = control

            @ui.refreshable
            def _render_plot_field_selector() -> None:
                plot_field_controls.clear()

                plot_loop_order = getattr(case_cfg, 'LOOP_ORDER', None)
                plot_signal_map = getattr(case_cfg, 'LOOP_SIGNAL_MAP', None)

                plot_groups = _build_field_groups(
                    list(bridge.state.available_log_fields),
                    plot_loop_order,
                    plot_signal_map,
                )

                for group_name, group_fields in plot_groups.items():
                    if not group_fields:
                        continue

                    if group_name == 'All':
                        with ui.row().classes('w-full flex-wrap gap-3'):
                            for field_name in group_fields:
                                _add_plot_checkbox(field_name)
                    else:
                        with ui.expansion(group_name, value=False).classes(
                            'w-full border rounded',
                        ):
                            with ui.row().classes('flex-wrap gap-3 p-2'):
                                for field_name in group_fields:
                                    _add_plot_checkbox(field_name)

            _render_plot_field_selector()

            with ui.row().classes('items-center gap-2'):
                ui.label('Selected:').classes('text-sm text-gray-600')

                selected_plot_label = ui.label(
                    ', '.join(selected_plot_fields or ['(none)']),
                ).classes('text-sm font-mono')

            with ui.row().classes('gap-2'):
                ui.button(
                    'Use output fields',
                    on_click=lambda: _set_selected_plot_fields(
                        [
                            field
                            for field in bridge.state.available_log_fields
                            if field.startswith('output:')
                        ][:4],
                    ),
                ).props('outline')

                ui.button(
                    'Clear selection',
                    on_click=lambda: _set_selected_plot_fields([]),
                ).props('outline')

            axis_formatter = (
                'v => (v !== 0 && Math.abs(v) < 0.01) '
                '? v.toExponential(2) '
                ': v.toFixed(2)'
            )

            tooltip_formatter = (
                'params => { '
                'const fmt = v => (v !== 0 && Math.abs(v) < 0.01) '
                '? v.toExponential(2) '
                ': v.toFixed(2); '
                'let s = "t: " + fmt(params[0].axisValue) + "<br/>"; '
                'params.forEach(p => { '
                's += p.marker + p.seriesName + ": " + fmt(p.value[1]) + "<br/>"; '
                '}); '
                'return s; '
                '}'
            )

            strip_chart = ui.echart(
                {
                    'animation': False,
                    'backgroundColor': 'transparent',
                    'color': [
                        '#4FD1C5',
                        '#90CDF4',
                        '#F6AD55',
                        '#F687B3',
                        '#A0AEC0',
                        '#F56565',
                        '#68D391',
                        '#B794F4',
                    ],
                    'tooltip': {
                        'trigger': 'axis',
                        ':formatter': tooltip_formatter,
                    },
                    'legend': {
                        'type': 'scroll',
                        'textStyle': {'color': '#d0d7de'},
                    },
                    'grid': {
                        'left': '6%',
                        'right': '4%',
                        'bottom': '8%',
                        'containLabel': True,
                    },
                    'xAxis': {
                        'type': 'value',
                        'name': 'sim_min',
                        'axisLine': {'lineStyle': {'color': '#bfc7d6'}},
                        'axisLabel': {
                            'color': '#d0d7de',
                            ':formatter': axis_formatter,
                        },
                        'nameTextStyle': {'color': '#d0d7de'},
                    },
                    'yAxis': {
                        'type': 'value',
                        'scale': True,
                        'min': 'dataMin',
                        'max': 'dataMax',
                        'axisLine': {'lineStyle': {'color': '#bfc7d6'}},
                        'axisLabel': {
                            'color': '#d0d7de',
                            ':formatter': axis_formatter,
                        },
                    },
                    'series': [],
                },
            ).classes('w-full h-80')

        strip_chart_window_min = 60

        def _get_smart_yaxis_config(series: list[dict]) -> dict:
            """Compute smart Y-axis config with padding around data range."""
            yaxis_config: dict[str, Any] = {
                'type': 'value',
                'scale': True,
                'axisLine': {'lineStyle': {'color': '#bfc7d6'}},
                'axisLabel': {
                    'color': '#d0d7de',
                    ':formatter': (
                        'v => (v !== 0 && Math.abs(v) < 0.01) '
                        '? v.toExponential(2) '
                        ': v.toFixed(2)'
                    ),
                },
            }

            all_y: list[float] = []

            for item in series:
                for point in item.get('data', []):
                    if point and len(point) >= 2:
                        try:
                            all_y.append(float(point[1]))
                        except Exception:
                            pass

            if not all_y:
                return yaxis_config

            y_min = min(all_y)
            y_max = max(all_y)
            y_range = y_max - y_min

            if y_range > 0:
                padding = y_range * 0.3
                low = y_min - padding
                high = y_max + padding
            else:
                padding = 0.005
                low = y_min - padding
                high = y_max + padding

            span = high - low if high != low else abs(high) if high != 0 else 1.0
            magnitude = 10 ** math.floor(math.log10(span))
            step = magnitude / 2

            yaxis_config['min'] = math.floor(low / step) * step
            yaxis_config['max'] = math.ceil(high / step) * step

            return yaxis_config

        def _render_strip_chart() -> None:
            series: list[dict[str, Any]] = []

            for field_name in selected_plot_fields:
                points: list[list[float]] = []

                for step_entry in step_history:
                    x_value = step_entry.get('time_min')
                    y_value = _extract_plot_value(step_entry, field_name)

                    if x_value is None or y_value is None:
                        continue

                    try:
                        points.append([float(x_value), float(y_value)])
                    except Exception:
                        continue

                series.append(
                    {
                        'name': field_name,
                        'type': 'line',
                        'showSymbol': False,
                        'connectNulls': True,
                        'smooth': False,
                        'lineStyle': {'width': 2},
                        'data': points,
                    },
                )

            strip_chart.options['series'] = series
            strip_chart.options['yAxis'] = _get_smart_yaxis_config(series)

            strip_chart.options.setdefault('xAxis', {})

            try:
                all_x = [
                    point[0]
                    for item in series
                    for point in item.get('data', [])
                    if point and len(point) >= 1
                ]

                if not all_x:
                    all_x = [
                        float(entry['time_min'])
                        for entry in step_history
                        if entry.get('time_min') is not None
                    ]

                if all_x:
                    x_max = max(all_x)
                    x_min = max(0.0, x_max - strip_chart_window_min)

                    strip_chart.options['xAxis']['min'] = x_min
                    strip_chart.options['xAxis']['max'] = x_max
                else:
                    strip_chart.options['xAxis'].pop('min', None)
                    strip_chart.options['xAxis'].pop('max', None)

            except Exception:
                strip_chart.options['xAxis'].pop('min', None)
                strip_chart.options['xAxis'].pop('max', None)

            strip_chart.options['legend'] = {
                'type': 'scroll',
                'data': list(selected_plot_fields),
                'textStyle': {'color': '#d0d7de'},
            }

            strip_chart.update()

        ui_refs['strip_chart_fn'] = _render_strip_chart
        _render_strip_chart()

        header_card = ui.card().classes('w-full')
        header_card.props('flat')

        @ui.refreshable
        def _render_columns_card() -> None:
            column_loop_order = getattr(case_cfg, 'LOOP_ORDER', None)
            column_signal_map = getattr(case_cfg, 'LOOP_SIGNAL_MAP', None)

            column_groups = _build_field_groups(
                list(bridge.state.available_log_fields),
                column_loop_order,
                column_signal_map,
            )

            scope_short = {
                'input': 'Inputs',
                'state': 'States',
                'output': 'Outputs',
                'meta': 'Meta',
            }

            ui.label('Columns').classes('text-h6')

            for group_name, group_fields in column_groups.items():
                if not group_fields:
                    continue

                if group_name == 'All':
                    by_scope: dict[str, list[str]] = {}

                    for field in group_fields:
                        by_scope.setdefault(field.partition(':')[0], []).append(field)

                    for scope_key in ('input', 'state', 'output', 'meta'):
                        scope_fields = by_scope.get(scope_key, [])
                        if not scope_fields:
                            continue

                        ui.label(
                            scope_short.get(scope_key, scope_key),
                        ).classes('text-xs font-semibold text-gray-500 mt-2')

                        with ui.row().classes('w-full flex-wrap gap-x-4 gap-y-1'):
                            for field_name in scope_fields:
                                ui.checkbox(
                                    field_name.partition(':')[2],
                                    value=field_name in bridge.state.selected_log_fields,
                                    on_change=lambda event, name=field_name: _toggle_log_field(
                                        name,
                                        bool(event_value(event, False)),
                                    ),
                                ).classes('min-w-[180px]')

                else:
                    with ui.expansion(group_name, value=True).classes(
                        'w-full border rounded mb-1',
                    ):
                        by_scope_group: dict[str, list[str]] = {}

                        for field in group_fields:
                            by_scope_group.setdefault(
                                field.partition(':')[0],
                                [],
                            ).append(field)

                        for scope_key in ('input', 'state', 'output', 'meta'):
                            scope_fields = by_scope_group.get(scope_key, [])
                            if not scope_fields:
                                continue

                            ui.label(
                                scope_short.get(scope_key, scope_key),
                            ).classes('text-xs font-semibold text-gray-400 mt-1 px-2')

                            with ui.row().classes('w-full flex-wrap gap-x-4 gap-y-1 px-2'):
                                for field_name in scope_fields:
                                    ui.checkbox(
                                        field_name.partition(':')[2],
                                        value=field_name in bridge.state.selected_log_fields,
                                        on_change=lambda event, name=field_name: _toggle_log_field(
                                            name,
                                            bool(event_value(event, False)),
                                        ),
                                    ).classes('min-w-[180px]')

            with ui.row().classes('gap-2 mt-3'):
                ui.button(
                    'All outputs',
                    on_click=lambda: (
                        bridge.set_selected_log_fields(
                            [
                                field
                                for field in bridge.state.available_log_fields
                                if field.startswith('output:')
                            ],
                        ),
                        _replay_log_from_history(
                            list(bridge.state.selected_log_fields),
                        ),
                        _render_columns_card.refresh(),
                    ),
                ).props('outline')

                ui.button(
                    'All fields',
                    on_click=lambda: (
                        bridge.set_selected_log_fields(
                            list(bridge.state.available_log_fields),
                        ),
                        _replay_log_from_history(
                            list(bridge.state.selected_log_fields),
                        ),
                        _render_columns_card.refresh(),
                    ),
                ).props('outline')

                ui.button(
                    'Clear log',
                    on_click=lambda: (
                        clear_ui_log_and_reset_selection(),
                        _render_columns_card.refresh(),
                        record_info('Datalog cleared and reset to output fields'),
                    ),
                ).props('outline')

            current_fields = list(bridge.state.selected_log_fields)
            if current_fields:
                header_string = bridge._format_log_header(current_fields)
                ui.label(header_string).classes('text-sm font-mono mt-3 text-gray-400')

        with header_card:
            _render_columns_card()

        log = ui.log(max_lines=400).classes('w-full h-96')
        log_ref['log'] = log

        info_card = ui.card().classes('w-full')

        with info_card:
            ui.label('Info').classes('text-h6')
            info_log = ui.log(max_lines=200).classes('w-full h-32')

        last_chart_render_time: list[float] = [0.0]

        def flush_log() -> None:
            nonlocal last_available_fields, printed_header

            if bridge.state.available_log_fields != last_available_fields:
                last_available_fields = list(bridge.state.available_log_fields)

                dynamic_runtime_panels.refresh()
                mode_settings_panel.refresh()
                _render_columns_card.refresh()
                _render_plot_field_selector.refresh()

                selected_plot_fields[:] = [
                    field
                    for field in selected_plot_fields
                    if field in bridge.state.available_log_fields
                ]

                _sync_plot_field_controls()
                _render_strip_chart()
                last_chart_render_time[0] = time.perf_counter()

            chart_has_new_data = False
            step_count_this_flush = 0

            for record in bridge.drain_records():
                if record.kind == 'status':
                    try:
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        mode = f'[{record.mode}]' if record.mode else ''
                        info_log.push(f'{timestamp} | INFO : {mode} {record.message}')
                    except Exception:
                        info_log.push(bridge.format_record(record))

                    continue

                if record.kind == 'header':
                    try:
                        current_fields = list(bridge.state.selected_log_fields)
                        header_string = bridge._format_log_header(current_fields)

                        if header_string != printed_header:
                            printed_header = header_string
                            _render_columns_card.refresh()
                    except Exception:
                        pass

                    continue

                if record.kind == 'step':
                    step_index = record.step_index

                    if step_index is not None and step_index <= _watermark[0]:
                        continue

                    if step_index is not None:
                        _watermark[0] = step_index

                    step_history.append(
                        {
                            'step_index': record.step_index,
                            'time_min': record.time_min,
                            'inputs': dict(record.inputs or {}),
                            'states': dict(record.states or {}),
                            'outputs': dict(record.outputs or {}),
                        },
                    )

                    chart_has_new_data = True
                    step_count_this_flush += 1

                    if step_count_this_flush <= 20:
                        current_fields = list(bridge.state.selected_log_fields)
                        log.push(bridge._format_log_row(record, current_fields))

                else:
                    log.push(bridge.format_record(record))

            if chart_has_new_data:
                now = time.perf_counter()

                if now - last_chart_render_time[0] >= 0.2:
                    _render_strip_chart()
                    last_chart_render_time[0] = now

        ui.timer(0.05, flush_log)

    ui.on_exception(
        lambda error: ui.notify(
            f'Bridge error: {error}',
            color='negative',
        ),
    )

    def _on_client_delete() -> None:
        record_info('App closed')
        bridge.stop()

    ui.context.client.on_delete(_on_client_delete)


if __name__ in {'__main__', '__mp_main__'}:
    ui.run(
        storage_secret=os.environ.get(
            'NICEGUI_STORAGE_SECRET',
            'dev-secret',
        ),
        dark=True,
    )