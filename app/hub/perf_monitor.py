# app/hub/perf_monitor.py

"""Reusable real-time stripchart for the Performance Monitoring section.

Moved from ``app/components/performance_monitor.py`` during the v1
purge — identical behaviour, new location. Consumes the same
``store.bridge`` ``_step_log`` deque; pages now obtain the store via
``hub.engine_control.bridge`` (any wrapper that exposes ``.bridge``
works).

This module mirrors the plot pattern in ``tests/main.py`` and the
selection pattern from the Data Logger:

- A NiceGUI ``ui.echart`` line chart, one trace per selected field,
  retuned to the DCS HMI palette (amber / cyan / green / red, amber
  axes, deep-black background).
- Smart y-axis: padded around the visible data range, rounded to a
  human-friendly step (1×/2×/5× decade).
- Scrolling x-axis: a fixed ``window_min`` window of simulation
  minutes.
- Flow-rate fields (FSP*, F_*, *.F) auto-scaled from per-second to
  per-hour for display.
- Periodic ``ui.timer`` flush that drains the bridge's step records
  into a bounded history deque and re-renders the chart.

Selection — single source of truth
----------------------------------
The Performance Monitoring page reads its plot selection from the
**same** state as the Data Logger:

- :pyattr:`bridge.state.selected_log_fields` — list of ``field``
  strings (``input:...`` / ``state:...`` / ``output:...``).
- :py:meth:`bridge.set_selected_log_fields` — setter that the
  Data Logger uses too.

The picker UI mirrors the Data Logger's *clickable header cell*
pattern: one cell per available field, in a horizontal-scrolling
row. Clicking a cell toggles the field in/out of the bridge's
selected set. Active cells get the green accent used by the Data
Logger; inactive cells are muted. Because both pages write to the
same bridge state, toggling a cell here is reflected instantly in
the Data Logger's log widget, and vice-versa.

Layout
------
Three stacked plot panels (input / state / output), in the visual
language of the right drawer. Each panel exposes the same header
cell row as the Data Logger (filtered to its own scope), followed
by a status strip ("Selected: …") and the echart stripchart.

Usage
-----

In a per-case page render function::

    from app.components.performance_monitor import render_performance_monitor

    def render_sthr_monitoring(store=None) -> None:
        render_performance_monitor(store, case_slug='sthr')

When ``store`` is ``None`` (engine not importable) the panel renders
a small placeholder explaining the situation, instead of crashing.
"""

from __future__ import annotations

import math
import time
from collections import deque
from typing import Any, Optional

from nicegui import ui


__all__ = ['render_performance_monitor']


# ────────────────────────────────────────────────────────────────────────────
# Constants — mirror the test app
# ────────────────────────────────────────────────────────────────────────────

# Bounded history (steps) — 6000 steps ≈ 60 min at Ts=0.01 min.
# This must stay high enough so the 60-minute window is always full.
_HISTORY_MAXLEN = 6000

# How often the flush timer runs (s) — 500 ms gives the UI plenty of
# breathing room while the chart still feels live.
_FLUSH_INTERVAL_S = 0.5

# Minimum interval between echart re-renders.  500 ms = 2 fps is more
# than enough for a process-control stripchart and keeps the wire
# light even when the engine is running at high acceleration.
_CHART_THROTTLE_S = 0.5

# Default visible x-axis window (simulation minutes).
_DEFAULT_WINDOW_MIN = 60.0

# Section keys for the three stacked panels.
_PANEL_SECTIONS: tuple[tuple[str, str], ...] = (
    ('input', 'Input Section'),
    ('state', 'State Section'),
    ('output', 'Output Section'),
)

# Scope → display label (mirrors data_logger._SCOPE_TITLES).
_SCOPE_TITLES: dict[str, str] = {
    'input': 'INPUTS',
    'state': 'STATES',
    'output': 'OUTPUTS',
}

# Scope → hint (mirrors data_logger._SCOPE_HINTS).
_SCOPE_HINTS: dict[str, str] = {
    'input': 'Click a cell to plot / unplot the input signal',
    'state': 'Click a cell to plot / unplot the state signal',
    'output': 'Click a cell to plot / unplot the output signal',
}

# Trace palette for the chart — DCS HMI colors cycled through the
# selected fields, with amber first (brand accent).
_DCS_TRACE_PALETTE: list[str] = [
    '#ffd54f',  # amber
    '#4fd1c5',  # cyan
    '#4caf50',  # green
    '#ff5252',  # red
    '#90cdf4',  # sky
    '#f687b3',  # pink
    '#f6ad55',  # orange
    '#a0aec0',  # slate
]


def _color_for_index(index: int) -> str:
    """Return the palette color for the ``index``-th selected field.

    The picker cells and the chart both use this resolver so the
    cell's accent border matches the trace it produces.
    """
    return _DCS_TRACE_PALETTE[index % len(_DCS_TRACE_PALETTE)]


def _repaint_cell_dot(cell: Any, color: str) -> None:
    """Update (or clear) the color-dot child of a picker cell.

    The cell is a NiceGUI ``ui.element('div')``. Its first child is
    a ``span.pm-cell-color-dot`` we inject when building the grid.
    The dot's color is set via inline ``style`` so it can be
    re-tinted as the active-field order changes without rebuilding
    the cell from scratch.
    """
    try:
        dot = next(
            (
                child
                for child in cell.default_slot.children
                if 'pm-cell-color-dot' in getattr(child, '_classes', [])
            ),
            None,
        )
    except Exception:
        return

    if dot is None:
        return

    if color:
        dot.props(
            f'style="background-color: {color}; '
            f'box-shadow: 0 0 4px {color}; "',
        )
        # Make sure the dot is visible (display restored).
        dot.style('display: inline-block;')
    else:
        # Hide on inactive cells so the inactive look matches the
        # original muted state.
        dot.style('display: none;')


# ────────────────────────────────────────────────────────────────────────────
# Helpers — copied from tests/main.py with minor cleanup
# ────────────────────────────────────────────────────────────────────────────

def _is_flow_field(field_name: str) -> bool:
    """Detect if ``field_name`` is a flow-rate field needing per-hour scaling.

    Flow fields cover:
    - FSP setpoints (``input:FSP-100.SP``)
    - ``f_*`` plant flow state variables
    - Actuator flow outputs ending in ``.F``
    """
    _, _, tag = field_name.partition(':')
    tag_upper = tag.upper()

    return (
        tag_upper.startswith('FSP')
        or tag_upper.startswith('F_')
        or 'F_' in tag_upper
        or tag_upper.endswith('.F')
    )


def _scale_value(value: float | None, field_name: str) -> float | None:
    """Scale per-second flow values to per-hour for display."""
    if value is None:
        return None
    try:
        scaled = float(value)
    except (TypeError, ValueError):
        return value
    if _is_flow_field(field_name):
        scaled *= 3600.0
    return scaled


def _extract_plot_value(step_entry: dict, field_name: str) -> float | None:
    """Pull the value for ``field_name`` out of one history entry."""
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


def _split_fields_by_scope(fields: list[str]) -> dict[str, list[str]]:
    """Bucket ``input:…/state:…/output:…/meta:…`` fields by scope.

    ``meta:`` fields are folded into ``state`` so the three scope
    cards cover every available signal without a fourth card.
    Mirrors ``data_logger._split_fields_by_scope``.
    """
    buckets: dict[str, list[str]] = {
        scope: [] for scope, _ in _PANEL_SECTIONS
    }
    for field in fields:
        scope, _, _ = field.partition(':')
        if scope in buckets:
            buckets[scope].append(field)
        elif scope == 'meta':
            buckets['state'].append(field)
    return buckets


def _smart_yaxis_config(series: list[dict]) -> dict:
    """Y-axis config with padding around the visible data range.

    The min/max are pulled in to ``floor(low/step)*step`` /
    ``ceil(high/step)*step`` so the gridlines land on round numbers.
    """
    yaxis_config: dict[str, Any] = {
        'type': 'value',
        'scale': True,
        'axisLine': {'lineStyle': {'color': '#ffd54f'}},
        'axisLabel': {
            'color': '#ffd54f',
            'fontFamily': 'Courier Prime, Courier, monospace',
            'fontSize': 10,
            ':formatter': (
                'v => (v !== 0 && Math.abs(v) < 0.01) '
                '? v.toExponential(2) '
                ': v.toFixed(2)'
            ),
        },
        'splitLine': {
            'lineStyle': {'color': 'rgba(255, 213, 79, 0.10)'},
        },
    }

    all_y: list[float] = []
    for item in series:
        for point in item.get('data', []):
            if point and len(point) >= 2:
                try:
                    all_y.append(float(point[1]))
                except (TypeError, ValueError):
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


# ────────────────────────────────────────────────────────────────────────────
# Main entry point
# ────────────────────────────────────────────────────────────────────────────

def render_performance_monitor(
    store: Optional[Any],
    *,
    case_slug: str,
    window_min: float = _DEFAULT_WINDOW_MIN,
) -> None:
    """Render the Performance Monitoring page.

    The page contains three stacked plot panels (input / state /
    output), each in a card styled like the right drawer. The plot
    selection is the same source of truth as the Data Logger:
    ``bridge.state.selected_log_fields`` — toggling a cell here
    toggles the column in the Data Logger's log widget too.

    Parameters
    ----------
    store:
        A ``BaseBridgeStore`` (or subclass) bound to a running
        :class:`GenericBridge``. ``None`` triggers the placeholder.
    case_slug:
        Reserved for future per-case hookups (loop grouping, etc.).
        The current implementation does not consume it, but it is
        kept for API compatibility with the original component.
    window_min:
        Width of the scrolling x-axis window in simulation minutes.
    """
    _ = case_slug  # kept for API compatibility

    with ui.column().classes('pm-page w-full gap-3'):
        # ── Page header — matches the right-drawer title language ──
        with ui.row().classes('pm-page-header w-full items-center'):
            ui.label('Performance Monitoring').classes('pm-page-title')
            ui.label(
                f'Live signals · {window_min:g} min window · '
                f'click cells to toggle',
            ).classes('pm-page-subtitle')

        if store is None:
            ui.label(
                'Performance monitoring is not available without an engine '
                'connection. Start the engine and reload this page.',
            ).classes('text-white/70 text-sm')
            return

        bridge = getattr(store, 'bridge', None)
        if bridge is None:
            ui.label(
                'No bridge attached to the store — cannot render real-time '
                'plot.',
            ).classes('text-white/70 text-sm')
            return

        _mount_stripchart(
            bridge=bridge,
            window_min=window_min,
        )


def _mount_stripchart(
    *,
    bridge: Any,
    window_min: float,
) -> None:
    """Build the three stacked panels, each with header cells + chart.

    Each panel renders a right-drawer-style card with:
    - a section title + scope-tag header bar (mirrors the Data
      Logger scope card);
    - a horizontal-scrolling row of clickable cells (one per
      available field in the section) — the picker UI;
    - a status strip showing the currently plotted fields;
    - the echart stripchart bound to the bridge's
      ``selected_log_fields`` (filtered to the panel's scope).
    """
    # ── History deque, seeded from the bridge's existing _step_log ──
    initial_log = list(getattr(bridge, '_step_log', []) or [])
    step_history: deque[dict] = deque(initial_log, maxlen=_HISTORY_MAXLEN)
    watermark: list[int] = [
        max(
            (
                entry['step_index']
                for entry in step_history
                if isinstance(entry, dict)
                and entry.get('step_index') is not None
            ),
            default=-1,
        ),
    ]

    # ── Reset detection ──
    # The engine bridge clears its persistent ``_step_log`` on
    # ``bridge.reset()`` and re-seeds ``state.last_step`` to ``-1``.
    # The stripchart's local ``step_history`` and ``watermark`` need
    # to mirror that, otherwise the chart's pre-reset lines would
    # stay on screen indefinitely (or, when the engine starts a new
    # session, the watermark check would silently drop every new
    # step until the watermark caught up). Treat any *backwards*
    # jump in ``state.last_step`` as a reset signal and wipe the
    # chart's local state on the next flush tick.
    _last_seen_last_step: list[int] = [
        int(
            getattr(getattr(bridge, 'state', None), 'last_step', -1) or -1,
        ),
    ]

    # Initial field set (read once; flush timer will refresh).
    available_fields: list[str] = list(
        getattr(bridge.state, 'available_log_fields', []) or [],
    )
    fields_by_scope: dict[str, list[str]] = _split_fields_by_scope(
        available_fields,
    )

    # ── Stacked column of three plot panels ──
    panel_containers: dict[str, Any] = {}
    for section, title in _PANEL_SECTIONS:
        with ui.card().classes('pm-panel w-full') as panel:
            pass
        panel_containers[section] = panel

    # Per-panel mutable refs (populated as each panel renders).
    charts: dict[str, Any] = {}
    status_els: dict[str, Any] = {}
    cell_refs: dict[str, dict[str, Any]] = {
        scope: {} for scope, _ in _PANEL_SECTIONS
    }

    # ── Bridge state helpers (mirror Data Logger's setter) ──
    def _commit_selection(new_fields: list[str]) -> None:
        """Push the new selection back to the bridge.

        Preserves the original ordering relative to
        ``available_log_fields`` so the picker cells stay in a
        stable order. Same convention as the Data Logger.
        """
        available = list(
            getattr(bridge.state, 'available_log_fields', []) or [],
        )
        ordered = [field for field in available if field in set(new_fields)]
        try:
            bridge.set_selected_log_fields(ordered)
        except Exception:
            pass

    def _selected_for_scope(scope: str) -> list[str]:
        """Return the fields the bridge has selected whose scope matches.

        Mirrors ``data_logger._selected_for_scope``: ``meta:`` is
        folded into ``state`` so the three scope panels cover every
        available signal.
        """
        try:
            current = list(bridge.state.selected_log_fields) or []
        except Exception:
            current = []
        return [
            field
            for field in current
            if field.partition(':')[0] == scope
            or (scope == 'state' and field.startswith('meta:'))
        ]

    def _toggle_field(scope: str, field_name: str) -> None:
        """Flip ``field_name`` in/out of the bridge's selection."""
        try:
            current = list(bridge.state.selected_log_fields) or []
        except Exception:
            current = []
        if field_name in current:
            current = [f for f in current if f != field_name]
        else:
            current.append(field_name)
        _commit_selection(current)
        _refresh_cells(scope)
        _refresh_status(scope)
        _update_panel_chart(scope)

    def _refresh_cells(scope: str) -> None:
        """Repaint active/inactive class **and** trace color on every cell.

        Because the picker row IS the chart's legend (the chart's own
        legend is disabled), every active cell must carry the same
        color the chart trace uses. The trace color comes from
        :func:`_color_for_index` over the *scope-filtered* selection
        order, so toggling any field can shift later cells' colors
        — we re-apply the inline ``style`` here on every refresh so
        the cell ↔ line mapping stays correct after any toggle.
        """
        active_in_order = _selected_for_scope(scope)
        color_by_field: dict[str, str] = {
            field_name: _color_for_index(index)
            for index, field_name in enumerate(active_in_order)
        }
        active = set(active_in_order)

        for field_name, cell in cell_refs.get(scope, {}).items():
            if cell is None:
                continue
            try:
                if field_name in active:
                    cell.classes(
                        add='pm-cell-active',
                        remove='pm-cell-inactive',
                    )
                    cell_color = color_by_field.get(field_name, '')
                    if cell_color:
                        # Full chrome in the trace color — border,
                        # tinted fill, inner+outer glow. The
                        # ``!important`` is required because the
                        # ``.pm-cell-active`` CSS rule otherwise
                        # wins the cascade.
                        cell.props(
                            'style="border: 1px solid '
                            f'{cell_color} !important; '
                            f'background-color: {cell_color}26 !important; '
                            f'box-shadow: inset 0 0 0 1px {cell_color}55, '
                            f'0 0 6px -2px {cell_color}aa; "',
                        )
                    # Repaint the inner dot (if it exists) so its
                    # color tracks the active trace too. The dot is
                    # a child element with class ``pm-cell-color-dot``
                    # — we update it via the cell's own slot so the
                    # next chart render sees the fresh color.
                    _repaint_cell_dot(cell, cell_color)
                else:
                    cell.classes(
                        add='pm-cell-inactive',
                        remove='pm-cell-active',
                    )
                    # Strip any prior inline style so the inactive
                    # cell falls back to the muted base look.
                    cell.props('style=""')
                    _repaint_cell_dot(cell, '')
            except Exception:
                pass

    def _refresh_status(scope: str) -> None:
        el = status_els.get(scope)
        if el is None:
            return
        fields = _selected_for_scope(scope)
        try:
            if fields:
                # Use the same uppercase legend format as the chart
                # so the statusbar reads identically to the legend.
                el.text = '   ·   '.join(
                    _format_legend_label(f) for f in fields
                )
                el.classes(remove='pm-panel-statusbar-value-empty')
            else:
                el.text = '(no signal selected)'
                el.classes('pm-panel-statusbar-value-empty')
        except Exception:
            pass

    def _update_panel_chart(scope: str) -> None:
        chart = charts.get(scope)
        if chart is None:
            return
        _update_chart(
            chart=chart,
            selected_fields=_selected_for_scope(scope),
            step_history=step_history,
            window_min=window_min,
        )

    # ── Panel rendering ──
    def _build_panel(scope: str, title: str) -> None:
        scope_fields = fields_by_scope.get(scope, [])

        # ── Scope card header (title + hint, like Data Logger) ──
        with ui.row().classes('pm-panel-header w-full items-center'):
            with ui.column().classes('pm-panel-title-group'):
                ui.label(title).classes('pm-panel-title')
                ui.label(_SCOPE_HINTS[scope]).classes('pm-panel-hint')
            with ui.row().classes('pm-panel-tag items-center gap-1'):
                ui.element('span').classes('pm-panel-tag-dot')
                ui.label(scope.upper()).classes('pm-panel-tag-text')

        # ── Body ──
        with ui.column().classes('pm-panel-body w-full'):

            # ── Header cell row (Data Logger style) ──
            cell_container = ui.element('div').classes(
                'pm-panel-cell-container',
            )
            with cell_container:
                _build_header_grid(scope, scope_fields)

            # ── Status strip ──
            with ui.row().classes('pm-panel-statusbar w-full items-center'):
                ui.label('Selected').classes('pm-panel-statusbar-label')
                initial = _selected_for_scope(scope)
                initial_text = (
                    '   ·   '.join(_format_legend_label(f) for f in initial)
                    if initial
                    else '(no signal selected)'
                )
                value_classes = (
                    'pm-panel-statusbar-value'
                    if initial
                    else (
                        'pm-panel-statusbar-value '
                        'pm-panel-statusbar-value-empty'
                    )
                )
                value_el = ui.label(initial_text).classes(value_classes)
                status_els[scope] = value_el

            # ── Chart ──
            chart = _build_chart()
            charts[scope] = chart
            _update_panel_chart(scope)

    def _build_header_grid(scope: str, scope_fields: list[str]) -> None:
        """Render the picker row as one clickable cell per signal.

        Mirrors ``data_logger._build_header_grid`` (minus the
        read-only prefix columns, which are log-specific and not
        relevant to the stripchart). Each cell shows the tag
        (top, bold, uppercase) and the scope prefix (bottom,
        muted). When the field is active, a small color dot
        appears that matches the trace color used in the chart
        — the cell ↔ line correspondence is therefore visible
        at a glance.

        Because the chart's own legend is disabled, **this row IS
        the legend**: each active cell carries the trace color
        end-to-end (border, tinted background, glow, color dot),
        and ``_refresh_cells`` re-applies that styling whenever
        the selection shifts.
        """
        if not scope_fields:
            ui.label(
                '(no fields available for this scope)',
            ).classes('pm-panel-cell-empty')
            return

        with ui.row().classes('pm-panel-cell-grid'):
            active_in_order = _selected_for_scope(scope)
            color_by_field: dict[str, str] = {
                field_name: _color_for_index(index)
                for index, field_name in enumerate(active_in_order)
            }
            active = set(active_in_order)

            for field_name in scope_fields:
                scope_prefix, _, tag = field_name.partition(':')
                is_active = field_name in active
                cell_color = color_by_field.get(field_name, '')

                cell = ui.element('div').classes(
                    'pm-cell '
                    + (
                        'pm-cell-active'
                        if is_active
                        else 'pm-cell-inactive'
                    ),
                )
                # When active, the cell adopts the trace color end to
                # end: full border in the trace color, tinted
                # background in the same hue, and an inner glow. The
                # user therefore sees the cell ↔ chart line mapping
                # without having to read a separate legend.
                if is_active and cell_color:
                    cell.props(
                        f'style="border: 1px solid {cell_color} !important; '
                        f'background-color: {cell_color}26 !important; '
                        f'box-shadow: inset 0 0 0 1px {cell_color}55, '
                        f'0 0 6px -2px {cell_color}aa; "',
                    )
                with cell:
                    # Always render the color dot — ``_repaint_cell_dot``
                    # toggles its visibility based on active state so
                    # we don't have to rebuild the cell to change its
                    # color when the selection order shifts.
                    dot = ui.element('span').classes('pm-cell-color-dot')
                    if is_active and cell_color:
                        dot.props(
                            f'style="background-color: {cell_color}; '
                            f'box-shadow: 0 0 4px {cell_color}; "',
                        )
                        dot.style('display: inline-block;')
                    else:
                        dot.style('display: none;')
                    with ui.column().classes('pm-cell-text'):
                        ui.label(tag.upper()).classes('pm-cell-tag')
                        ui.label(scope_prefix.upper()).classes('pm-cell-meta')

                cell.on(
                    'click',
                    lambda _event, s=scope, f=field_name: _toggle_field(
                        s, f,
                    ),
                )
                cell_refs[scope][field_name] = cell

    for scope, title in _PANEL_SECTIONS:
        with panel_containers[scope]:
            _build_panel(scope, title)
        _refresh_cells(scope)

    # ── Periodic flush ──
    last_available_fields: list[str] = list(available_fields)
    last_render_time: list[float] = [0.0]

    def _flush() -> None:
        nonlocal last_available_fields

        # ── Reset detection ──
        # If the engine bridge was reset (its ``state.last_step``
        # went backwards), wipe the local history deque + watermark
        # and rebuild the chart's series so the first post-reset
        # step records aren't dropped by the watermark check below.
        # We update ``_last_seen_last_step`` *before* the drain so
        # the follow-up append can pick up the new step_index.
        #
        # Exception: if the previous run finished naturally (reached
        # ``time_end``), the worker restart on a "continue"
        # legitimately re-uses ``last_step + 1`` as the next
        # step_index. In that case the bridge flips
        # ``state.natural_stop = True`` and we must NOT wipe — a
        # "continue" must preserve the chart's prior history.
        try:
            current_last_step = int(
                getattr(
                    getattr(bridge, 'state', None), 'last_step', -1,
                ) or -1,
            )
        except Exception:
            current_last_step = -1
        try:
            natural_stop = bool(
                getattr(
                    getattr(bridge, 'state', None),
                    'natural_stop',
                    False,
                ),
            )
        except Exception:
            natural_stop = False
        if (
            current_last_step < _last_seen_last_step[0]
            and not natural_stop
        ):
            step_history.clear()
            watermark[0] = -1
            # Force a chart re-render so the old lines disappear
            # immediately rather than waiting for new data.
            for scope_key in charts:
                _update_panel_chart(scope_key)
        _last_seen_last_step[0] = current_last_step

        current_available = list(
            getattr(bridge.state, 'available_log_fields', []) or [],
        )

        if current_available != last_available_fields:
            last_available_fields = current_available
            fields_by_scope.clear()
            fields_by_scope.update(_split_fields_by_scope(current_available))
            for scope, title in _PANEL_SECTIONS:
                cell_refs[scope].clear()
                panel = panel_containers[scope]
                panel.clear()
                with panel:
                    _build_panel(scope, title)
                _refresh_cells(scope)
                _update_panel_chart(scope)

        # Drain new step records into history.
        chart_has_new_data = False
        try:
            step_log = list(getattr(bridge, '_step_log', []) or [])
        except Exception:
            step_log = []

        for entry in step_log:
            if not isinstance(entry, dict):
                continue
            step_index = entry.get('step_index')
            if step_index is None or step_index <= watermark[0]:
                continue
            watermark[0] = int(step_index)
            step_history.append(dict(entry))
            chart_has_new_data = True

        if chart_has_new_data:
            now = time.perf_counter()
            if now - last_render_time[0] >= _CHART_THROTTLE_S:
                for scope_key in charts:
                    _update_panel_chart(scope_key)
                last_render_time[0] = now

    ui.timer(_FLUSH_INTERVAL_S, _flush)


def _build_chart() -> Any:
    """Build a blank echart with the DCS HMI palette."""
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

    return ui.echart(
        {
            'animation': False,
            'backgroundColor': '#000000',
            'color': _DCS_TRACE_PALETTE,
            'tooltip': {
                'trigger': 'axis',
                'backgroundColor': 'rgba(17, 17, 17, 0.95)',
                'borderColor': '#ffd54f',
                'borderWidth': 1,
                'textStyle': {
                    'color': '#ffffff',
                    'fontFamily': 'Courier Prime, Courier, monospace',
                    'fontSize': 11,
                },
                'axisPointer': {
                    'type': 'line',
                    'lineStyle': {
                        'color': '#ffd54f',
                        'width': 1,
                        'type': 'dashed',
                        'opacity': 0.7,
                    },
                },
                ':formatter': tooltip_formatter,
            },
            # Legend intentionally disabled — the picker cell row above
            # the chart IS the legend. Each active cell carries the
            # trace color end-to-end (border, tinted background, color
            # dot) so the operator can read the cell ↔ line mapping
            # directly without a separate legend strip eating into the
            # chart well.
            'legend': {'show': False},
            'grid': {
                'left': '4%',
                'right': '3%',
                # Legend removed → top margin can be tightened so the
                # chart well fills the freed vertical space.
                'top': '6%',
                'bottom': '8%',
                'containLabel': True,
                'borderColor': 'rgba(255, 213, 79, 0.25)',
                'show': True,
            },
            'xAxis': {
                'type': 'value',
                # No axis title — the picker row above the chart is
                # the "label" for each trace. The X axis still shows
                # tick numbers (sim_min) without a heading.
                'name': '',
                'nameTextStyle': {'show': False},
                'axisLine': {'lineStyle': {'color': '#ffd54f'}},
                'axisTick': {'lineStyle': {'color': '#ffd54f'}},
                'axisLabel': {
                    'color': '#ffd54f',
                    'fontFamily': 'Courier Prime, Courier, monospace',
                    'fontSize': 10,
                    ':formatter': axis_formatter,
                },
                'splitLine': {
                    'lineStyle': {
                        'color': 'rgba(255, 213, 79, 0.08)',
                        'type': 'dashed',
                    },
                },
            },
            'yAxis': {
                'type': 'value',
                'name': '',
                'nameTextStyle': {'show': False},
                'scale': True,
                'min': 'dataMin',
                'max': 'dataMax',
                'axisLine': {'lineStyle': {'color': '#ffd54f'}},
                'axisTick': {'lineStyle': {'color': '#ffd54f'}},
                'axisLabel': {
                    'color': '#ffd54f',
                    'fontFamily': 'Courier Prime, Courier, monospace',
                    'fontSize': 10,
                    ':formatter': axis_formatter,
                },
                'splitLine': {
                    'lineStyle': {
                        'color': 'rgba(255, 213, 79, 0.10)',
                        'type': 'dashed',
                    },
                },
            },
            'series': [],
        },
    ).classes('pm-panel-chart')


def _format_legend_label(field_name: str) -> str:
    """Render ``field_name`` as an uppercase HMI legend tag.

    ``input:FSP-100.SP`` → ``FSP-100.SP  ·  INPUT``. The tag (top
    half) is the part the operator recognises; the scope (bottom
    half) is the section it lives in, matching the cell picker
    layout.
    """
    scope, _, tag = field_name.partition(':')
    return f'{tag.upper()}  ·  {scope.upper()}'


def _update_chart(
    *,
    chart: Any,
    selected_fields: list[str],
    step_history: deque,
    window_min: float,
) -> None:
    """Push the latest series into ``chart`` from the history deque.

    ``selected_fields`` is the scope-filtered slice of the bridge's
    ``selected_log_fields`` (one entry per field the user wants
    plotted). Each field becomes one trace on the chart; the trace
    color is the same :func:`_color_for_index` index the picker
    cell uses, so the cell border and the line on the chart are
    guaranteed to match.
    """
    series: list[dict[str, Any]] = []
    legend_names: list[str] = []

    for index, field_name in enumerate(selected_fields):
        points: list[list[float]] = []
        for step_entry in step_history:
            x_value = step_entry.get('time_min')
            y_value = _extract_plot_value(step_entry, field_name)
            if x_value is None or y_value is None:
                continue
            try:
                points.append([float(x_value), float(y_value)])
            except (TypeError, ValueError):
                continue

        color = _color_for_index(index)
        series.append(
            {
                'name': _format_legend_label(field_name),
                'type': 'line',
                'showSymbol': False,
                'connectNulls': True,
                'smooth': False,
                'lineStyle': {'width': 2, 'color': color},
                'itemStyle': {'color': color},
                'data': points,
            },
        )
        legend_names.append(_format_legend_label(field_name))

    chart.options['series'] = series
    chart.options['yAxis'] = _smart_yaxis_config(series)
    chart.options.setdefault('xAxis', {})

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
            data_max = max(all_x)
            # Oscilloscope-style scrolling:
            #   - data < window: axis = [0, data_max] so the trace
            #     always fills the full chart left-to-right.
            #   - data >= window: axis = [data_max - window, data_max]
            #     so the last window minutes scroll rightward.
            if data_max <= window_min:
                x_min = 0.0
                x_max = data_max
            else:
                x_min = data_max - window_min
                x_max = data_max
            chart.options['xAxis']['min'] = x_min
            chart.options['xAxis']['max'] = x_max
        else:
            chart.options['xAxis']['min'] = 0.0
            chart.options['xAxis']['max'] = window_min
    except Exception:
        chart.options['xAxis']['min'] = 0.0
        chart.options['xAxis']['max'] = window_min

    # Legend stays disabled — the picker cells above are the legend.
    # See ``_build_chart`` for the rationale. We still keep the
    # ``legend`` key in the options dict so echart doesn't fall back
    # to its built-in default when the series list is rebuilt.
    chart.options['legend'] = {'show': False}
    # ``legend_names`` is kept above so any future hover/tooltip
    # reader can still resolve a series index → label without us
    # having to recompute it.
    _ = legend_names

    chart.update()
