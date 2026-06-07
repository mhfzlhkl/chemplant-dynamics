# app/hub/data_logger.py

"""Data Logger menu-section renderer (case-agnostic).

Moved from ``app/pid/_shared/data_logger.py`` during the v1 purge —
identical behaviour, new location. Consumes the same ``bridge``
public API (``state``, ``drain_records``, ``set_selected_log_fields``,
``clear_logs``, ``_format_log_header``, ``_format_log_row``,
``format_record``, ``queue_status``, ``_step_log``,
``supported_modes``); pages obtain the bridge via
``hub.engine_control.bridge``.

Visual / UX style follows the **PID right drawer** (see
``app/components/right_drawer.py`` and
``app/static/css/control_panel/pid_right_drawer.css``):

- a top-level title row with an uppercase control-UI font and a
  thin separator (``.pid-right-drawer-title`` /
  ``.pid-right-drawer-separator``);
- each section gets a muted "section title" (``.pid-right-drawer-
  section-title``) immediately above its card;
- card backgrounds use ``--bg-panel`` with a hair border, the same
  treatment as the drawer items.

Layout
------

The data logger is split into **three scoped cards** (Inputs,
States, Outputs) plus one **Info** card at the bottom:

- Each scoped card exposes its log columns as a *table-header row*
  of multi-select dropdowns. The user toggles which signals show in
  that scope's log widget. The select rows are scrollable
  horizontally so wide column sets still fit.
- Below each header row sits a dedicated ``ui.log`` that streams
  rows for the selected fields in that scope only. The log line
  starts with ``realtime | step | sim_min`` and then the chosen
  signals — same row format the bridge already produces, just
  filtered per scope so each card is independently readable.
- The **Info** card at the very bottom shows status messages (Run,
  Stop, Reset, mode change, etc.) — kind ``'status'`` records
  drained from the bridge.

Bridge integration
------------------

The helper is **case-agnostic**. It only needs:

- a bridge object (anything exposing the relevant
  :class:`GenericBridge` API — ``state``, ``drain_records``,
  ``set_selected_log_fields``, ``clear_logs``, ``_format_log_header``,
  ``_format_log_row``, ``format_record``, ``queue_status``,
  ``_step_log``, ``supported_modes``);
- a case config object exposing ``LOOP_ORDER`` and ``LOOP_SIGNAL_MAP``
  (used as a hint for ordering columns inside each scope). The
  helper tries ``bridge.case_name`` →
  ``gateway.config_registry.get_case_config`` and silently falls
  back to plain alphabetical ordering if neither is available.

The helper is what each case's ``render_<case>_data_logger()`` calls
when a bridge is wired; otherwise the placeholder
"no engine / no log file" card stays in place.
"""

from __future__ import annotations

import csv
import io
import json
from collections import deque
from datetime import datetime
from typing import Any

from nicegui import ui


__all__ = [
    'render_data_logger_section',
    'data_logger_unavailable',
]


# How often the flush timer drains the bridge's record queue.
# 300 ms ≈ 3 Hz — fast enough to read the log, slow enough that
# the DOM never chokes even when the engine is running at very
# high acceleration.
_FLUSH_INTERVAL_S: float = 0.3

# Cap on the in-memory step history used for replay when the user
# toggles field selection.
_STEP_HISTORY_MAXLEN: int = 1000

# Cap on rows pushed to each per-scope ``ui.log`` per flush cycle.
# At 3 Hz this means ≤ 6 rows / sec per scope — readable without
# DOM jank.
_ROWS_PER_FLUSH_CAP: int = 2

# The three scopes that get their own card + log widget. The order
# here is the visual order top → bottom.
_SCOPE_ORDER: tuple[str, ...] = ('input', 'state', 'output')

# Display labels (uppercase to match right-drawer typography).
_SCOPE_TITLES: dict[str, str] = {
    'input': 'INPUTS',
    'state': 'STATES',
    'output': 'OUTPUTS',
}

# Short hint shown beside each scope title — same role the
# ``pid-right-drawer-section-title`` muted text plays in the drawer.
_SCOPE_HINTS: dict[str, str] = {
    'input': 'Manipulated values & setpoints fed into the plant',
    'state': 'Internal controller / plant states',
    'output': 'Plant outputs (PV) and measured signals',
}


# ──────────────────────────────────────────────────────────────
# Unit inference
# ──────────────────────────────────────────────────────────────

# Per-loop-letter unit for "process value" / "setpoint" /
# "controlled variable" signals. The letter is the first
# character of the loop id (TIC-100 → T → temperature, LIC-100
# → L → level, FIC-100 → F → flow).
_LOOP_LETTER_UNIT: dict[str, str] = {
    'T': '°C',
    'L': 'm',
    'F': 'kg/h',
    'P': 'bar',
}

# Suffix-based units that apply regardless of loop. The suffix
# is everything after the LAST dot in the bridge tag — these
# are the conventions every case in this project uses (see
# cases/sthr/config.py and cases/biodiesel/config.py).
_SUFFIX_UNIT: dict[str, str] = {
    # Controller / signal-conditioning percentages
    'C': '%',          # controller output / sensor-transmitter normalized
    'M': '%',          # manipulated variable command / actuator command
    'R': '%',          # reference (controller working SP, normalized)
    'vp': '%',         # valve position
    'I_state': '%',    # integral state of a PI / PID controller
    'D_state': '%',    # derivative state of a PI / PID controller
    # Tuning constants
    'Kc': '—',
    'tauI': 'min',
    'tauD': 'min',
}

# Whole-tag (no-dot) units. Used for plant-level signals like
# STHR.W (steam flow) and STHR.F (feed flow) where the meaning
# is tied to the symbol itself.
_PLANT_SYMBOL_UNIT: dict[str, str] = {
    'W': 'kg/h',
    'F': 'kg/h',
    'Ti': '°C',
    'T': '°C',
    'Ts': '°C',
    'L': 'm',
    'V': 'm³',
}


def _loop_letter_for_tag(
    tag: str,
    loop_signal_map: dict | None,
) -> str | None:
    """Return the loop-letter (T/L/F/P) the ``tag`` belongs to.

    Walks ``loop_signal_map`` looking for the controller / setpoint
    / actuator prefix that matches the tag's head. Falls back to
    the second letter of the tag itself (``TSP-100.SP`` → ``T``)
    because every loop id in this project follows the
    ``<X>IC-<num>`` convention.
    """
    if loop_signal_map:
        for loop_id, meta in loop_signal_map.items():
            for key in ('controller', 'setpoint', 'actuator'):
                prefix = meta.get(key) or ''
                if not prefix:
                    continue
                if tag == prefix or tag.startswith(f'{prefix}.'):
                    return loop_id[0]

    # Tag heads like TSP-100, TC-100, LV-100, FT-100 — the second
    # character is the loop type letter (P=setpoint, C=controller,
    # V=valve, T=transmitter). The first character is the loop's
    # physical variable letter.
    if tag and tag[0] in _LOOP_LETTER_UNIT:
        return tag[0]
    return None


def _unit_for_field(
    field_name: str,
    loop_signal_map: dict | None = None,
) -> str:
    """Infer a short unit string for a logger column.

    The bridge has no per-signal unit map today (see
    ``cases/*/config.py``), so we infer from the tag-naming
    convention every case in this project follows:

    - ``meta:time`` → time unit (minutes / seconds depending on
      case);
    - ``meta:step`` → ``#`` (dimensionless counter);
    - ``meta:mode`` → ``—``;
    - suffixes like ``.M``, ``.C``, ``.vp``, ``.I_state`` →
      ``%`` (HMI-normalized);
    - tuning constants ``.Kc / .tauI / .tauD`` → tuning units;
    - setpoints (``.SP``) and process values (``.PV``, ``.PVm``)
      → the loop's physical unit, looked up from
      ``loop_signal_map`` first then inferred from the tag head;
    - plant symbols (``STHR.W``, ``STHR.F``, ``STHR.Ti`` …) → a
      built-in lookup of common P&ID symbols.

    Returns ``''`` when no convention matches so the cell falls
    back to showing nothing rather than a misleading unit.
    """
    scope, _, tag = field_name.partition(':')

    if scope == 'meta':
        if tag == 'step':
            return '#'
        if tag == 'time':
            return 'min'
        if tag == 'mode':
            return '—'
        return ''

    if not tag:
        return ''

    head, _, suffix = tag.rpartition('.')

    # Suffix-based rules (most specific) ------------------------
    if suffix and suffix in _SUFFIX_UNIT:
        return _SUFFIX_UNIT[suffix]

    # Setpoint / process value follow the loop's physical unit.
    if suffix in {'SP', 'PV', 'PVm'}:
        letter = _loop_letter_for_tag(tag, loop_signal_map)
        if letter and letter in _LOOP_LETTER_UNIT:
            return _LOOP_LETTER_UNIT[letter]

    # Actuator / valve output flow (e.g. TV-100.F) is the loop's
    # process flow even though the loop isn't a flow loop.
    if suffix == 'F':
        return 'kg/h'

    # Plant symbol lookup — STHR.W, STHR.F, STHR.Ti, …
    if suffix and suffix in _PLANT_SYMBOL_UNIT:
        return _PLANT_SYMBOL_UNIT[suffix]

    # Whole-tag plant symbol (no dot, e.g. "W" or "Ti").
    if not head and tag in _PLANT_SYMBOL_UNIT:
        return _PLANT_SYMBOL_UNIT[tag]

    return ''


# ──────────────────────────────────────────────────────────────
# Case-config resolution
# ──────────────────────────────────────────────────────────────

def _resolve_case_config(bridge: Any) -> Any:
    """Return the case-config object for the bridge, or ``None``.

    Order of resolution:
    1. ``bridge.case_cfg`` (in case a subclass has cached it).
    2. ``gateway.config_registry.get_case_config(bridge.case_name)``.
    """
    cfg = getattr(bridge, 'case_cfg', None)
    if cfg is not None:
        return cfg

    case_name = getattr(bridge, 'case_name', None) or getattr(
        getattr(bridge, 'state', None), 'case_name', None,
    )
    if not case_name:
        return None

    try:
        from gateway.config_registry import get_case_config  # type: ignore
        return get_case_config(case_name)
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────
# Field grouping by scope
# ──────────────────────────────────────────────────────────────

def _split_fields_by_scope(
    fields: list[str],
) -> dict[str, list[str]]:
    """Bucket ``input:…/state:…/output:…/meta:…`` fields by scope.

    ``meta:`` fields are folded into ``state`` so the three scope
    cards cover every available signal without a fourth card. This
    matches the way the test app treats meta as state-adjacent
    metadata (mode, step counter, …).
    """
    buckets: dict[str, list[str]] = {scope: [] for scope in _SCOPE_ORDER}

    for field in fields:
        scope, _, _ = field.partition(':')
        if scope in buckets:
            buckets[scope].append(field)
        elif scope == 'meta':
            buckets['state'].append(field)

    return buckets


def _order_fields_for_scope(
    scope_fields: list[str],
    loop_order: list[str] | None,
    loop_signal_map: dict | None,
) -> list[str]:
    """Stable order for fields inside a scope card.

    Loop signals come first in the case's declared ``LOOP_ORDER``
    (each loop's controller/setpoint/actuator prefixes are checked
    against the tag); anything that doesn't match a loop falls
    after, in input order.
    """
    if not loop_order or not loop_signal_map or len(loop_order) <= 1:
        return list(scope_fields)

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

    buckets: dict[str, list[str]] = {loop_id: [] for loop_id in loop_order}
    leftovers: list[str] = []

    for field in scope_fields:
        _, _, tag = field.partition(':')

        for loop_id in loop_order:
            if tag == loop_plant_mvs.get(loop_id, ''):
                buckets[loop_id].append(field)
                break
        else:
            for loop_id in loop_order:
                if any(
                    tag.startswith(f'{prefix}.') or tag == prefix
                    for prefix in loop_prefixes[loop_id]
                ):
                    buckets[loop_id].append(field)
                    break
            else:
                leftovers.append(field)

    ordered: list[str] = []
    for loop_id in loop_order:
        ordered.extend(buckets[loop_id])
    ordered.extend(leftovers)
    return ordered


# ──────────────────────────────────────────────────────────────
# Row formatting (scope-filtered)
# ──────────────────────────────────────────────────────────────

def _format_scoped_row(
    bridge: Any,
    record_like: dict | Any,
    fields: list[str],
    *,
    units: list[str] | None = None,
) -> str:
    """Format one step row containing only ``fields`` for one scope.

    Accepts either a live :class:`BridgeRecord` or a ``dict`` entry
    pulled from the replay buffer. Delegates to
    ``bridge._format_log_row`` with ``dcs_style=True`` so the prefix
    is the bracketed wall-clock + ``STEP NNNNN | t=…`` shape and each
    field cell is ``TAG=<fixed-width value> <unit>``. ``units`` is
    aligned per-index with ``fields``; the caller computes them
    once via :func:`_unit_for_field` so the same list is reused for
    the header line emission too.
    """
    if not fields:
        return ''

    if isinstance(record_like, dict):
        try:
            from gateway.bridge_support import BridgeRecord  # type: ignore
            record = BridgeRecord(
                kind='step',
                message='',
                step_index=record_like.get('step_index'),
                time_min=record_like.get('time_min'),
                inputs=dict(record_like.get('inputs', {}) or {}),
                states=dict(record_like.get('states', {}) or {}),
                outputs=dict(record_like.get('outputs', {}) or {}),
            )
        except Exception:
            return ''
    else:
        record = record_like

    try:
        return bridge._format_log_row(
            record, fields, units=units, dcs_style=True,
        )
    except TypeError:
        # Older bridge build without the new kwargs — fall back to
        # the legacy single-row format. Keeps the UI working even if
        # the bridge module gets rolled back independently.
        try:
            return bridge._format_log_row(record, fields)
        except Exception:
            return ''
    except Exception:
        return ''


# ──────────────────────────────────────────────────────────────
# Export helpers — CSV / JSON
# ──────────────────────────────────────────────────────────────

def _export_columns_for_scope(
    scope: str | None,
    selected_fields: list[str],
) -> list[str]:
    """Return the field list that should appear in the export.

    ``scope=None`` exports every selected field. Otherwise we filter
    by scope prefix (``input``/``state``/``output``), folding
    ``meta:`` into ``state`` the same way the on-screen tabs do.
    """
    if scope is None:
        return list(selected_fields)

    return [
        field
        for field in selected_fields
        if field.partition(':')[0] == scope
        or (scope == 'state' and field.startswith('meta:'))
    ]


def _value_for_field(entry: dict, field_name: str) -> Any:
    """Pull a single field value out of a step-history entry.

    Mirrors the scope dispatch in :meth:`GenericBridge._format_log_row`
    so the export shows the same value the on-screen log shows.
    Returns ``None`` for unknown / missing values; the CSV writer
    converts that to an empty cell and the JSON writer keeps it
    as ``null``.
    """
    scope, _, tag = field_name.partition(':')

    if scope == 'input':
        return (entry.get('inputs') or {}).get(tag)
    if scope == 'state':
        return (entry.get('states') or {}).get(tag)
    if scope == 'output':
        return (entry.get('outputs') or {}).get(tag)
    if scope == 'meta':
        if tag == 'time':
            return entry.get('time_min')
        if tag == 'step':
            return entry.get('step_index')
        return None

    return None


def _build_csv_bytes(
    step_history: 'deque[dict]',
    fields: list[str],
) -> bytes:
    """Serialise ``step_history`` rows to a UTF-8 CSV payload.

    Columns are ``step | sim_min`` followed by every entry in
    ``fields`` (already scope-filtered by the caller). Values are
    written verbatim; floats keep their native repr — the user can
    re-parse with ``pandas.read_csv`` without column guessing.
    """
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer, lineterminator='\n')

    writer.writerow(['step', 'sim_min', *fields])

    for entry in step_history:
        if not isinstance(entry, dict):
            continue
        row = [
            entry.get('step_index'),
            entry.get('time_min'),
        ]
        for field in fields:
            row.append(_value_for_field(entry, field))
        writer.writerow(['' if v is None else v for v in row])

    return buffer.getvalue().encode('utf-8')


def _build_json_bytes(
    step_history: 'deque[dict]',
    fields: list[str],
    *,
    case_name: str | None = None,
    scope: str | None = None,
) -> bytes:
    """Serialise ``step_history`` rows to a UTF-8 JSON payload.

    Output shape:

    ::

        {
            "case": "sthr",
            "scope": "output" | "all",
            "exported_at": "2026-06-04T18:23:11",
            "fields": ["output:T_PV", ...],
            "rows": [
                {"step": 0, "sim_min": 0.0, "output:T_PV": 25.0, ...},
                ...
            ]
        }
    """
    rows: list[dict[str, Any]] = []
    for entry in step_history:
        if not isinstance(entry, dict):
            continue
        row: dict[str, Any] = {
            'step': entry.get('step_index'),
            'sim_min': entry.get('time_min'),
        }
        for field in fields:
            row[field] = _value_for_field(entry, field)
        rows.append(row)

    payload = {
        'case': case_name,
        'scope': scope or 'all',
        'exported_at': datetime.now().isoformat(timespec='seconds'),
        'fields': list(fields),
        'rows': rows,
    }
    return json.dumps(payload, indent=2, default=str).encode('utf-8')


def _build_export_filename(
    case_name: str | None,
    scope: str | None,
    ext: str,
) -> str:
    """Compose a stable, sortable export filename.

    Example: ``sthr_output_2026-06-04T182311.csv``
    """
    stamp = datetime.now().strftime('%Y-%m-%dT%H%M%S')
    parts = [case_name or 'data_logger', scope or 'all', stamp]
    parts = [p for p in parts if p]
    return f'{"_".join(parts)}.{ext}'


def _trigger_download(
    content: bytes,
    filename: str,
    media_type: str,
) -> None:
    """Push ``content`` to the browser as a file download.

    Wraps :func:`ui.download.content` with a fallback for older
    NiceGUI builds where the helper isn't available — in that case
    we surface an actionable ``ui.notify`` instead of silently
    failing.
    """
    try:
        ui.download.content(content, filename, media_type)
        ui.notify(f'Saved {filename}', color='positive')
    except AttributeError:
        # Pre-2.14 NiceGUI: fall back to the legacy ui.download(...).
        try:
            ui.download(content, filename)  # type: ignore[misc]
            ui.notify(f'Saved {filename}', color='positive')
        except Exception:
            ui.notify(
                'Download not supported by this NiceGUI version',
                color='warning',
            )
    except Exception as exc:  # noqa: BLE001
        ui.notify(f'Save failed: {exc}', color='negative')


# ──────────────────────────────────────────────────────────────
# Public API — placeholder for "no engine" case
# ──────────────────────────────────────────────────────────────

def data_logger_unavailable(message: str | None = None) -> None:
    """Render the original "no log file / no entries" placeholder."""
    fallback_message = (
        message
        or 'No log entries yet. Connect an engine to start logging data.'
    )

    with ui.column().classes('data-logger-root'):
        ui.label('Data Logger').classes('data-logger-page-title')
        ui.separator().classes('data-logger-separator')

        with ui.card().classes('data-logger-scope-card'):
            ui.label('Log File Location').classes('data-logger-scope-title')
            ui.label('(no log file — engine not connected)').classes(
                'data-logger-hint',
            )

        with ui.card().classes('data-logger-scope-card'):
            ui.label('Recent Entries').classes('data-logger-scope-title')
            ui.label(fallback_message).classes('data-logger-hint')


# ──────────────────────────────────────────────────────────────
# Public API — main renderer
# ──────────────────────────────────────────────────────────────

def render_data_logger_section(bridge: Any) -> None:
    """Render the Data Logger section wired to ``bridge``.

    The layout is three scope cards (Inputs / States / Outputs)
    each with a *header-row of multi-select dropdowns* that act as
    column pickers, followed by a ``ui.log`` showing rows filtered
    to that scope. A separate Info card at the bottom shows status
    messages drained off the bridge.

    Side effects:

    - registers a 50 ms ``ui.timer`` on the current page;
    - reads/writes ``bridge.state.selected_log_fields`` via
      :meth:`bridge.set_selected_log_fields`;
    - reads ``bridge._step_log`` once on first render to seed the
      replay buffer.
    """
    case_cfg = _resolve_case_config(bridge)
    loop_order = getattr(case_cfg, 'LOOP_ORDER', None) or []
    loop_signal_map = getattr(case_cfg, 'LOOP_SIGNAL_MAP', None) or {}

    # Ensure the initial field selection is sane. If the bridge has
    # never seen a user choice, default to all ``output:`` fields.
    if not list(getattr(bridge.state, 'selected_log_fields', []) or []):
        defaults = [
            field
            for field in getattr(bridge.state, 'available_log_fields', [])
            or []
            if field.startswith('output:')
        ]
        try:
            bridge.set_selected_log_fields(defaults)
        except Exception:
            pass

    # Replay buffer — bounded to keep memory in check during long sessions.
    step_history: deque[dict] = deque(
        getattr(bridge, '_step_log', []) or [],
        maxlen=_STEP_HISTORY_MAXLEN,
    )
    _watermark: list[int] = [-1]
    if step_history:
        _watermark[0] = max(
            (
                int(entry.get('step_index') or -1)
                for entry in step_history
                if entry.get('step_index') is not None
            ),
            default=-1,
        )

    last_available_fields: list[str] = list(
        getattr(bridge.state, 'available_log_fields', []) or [],
    )

    # ── Reset detection ──
    # The engine bridge clears its persistent ``_step_log`` on
    # ``bridge.reset()`` and re-seeds ``state.last_step`` to ``-1``.
    # The data logger's local ``step_history`` and ``_watermark``
    # need to mirror that, otherwise the first post-reset step
    # records (with ``step_index`` starting at 0) get dropped by
    # the watermark check at :func:`_flush_log` below.
    #
    # We track ``state.last_step`` and treat any *backwards* jump
    # past the previous value as a reset. ``last_step`` is the
    # engine-canonical "we have completed N steps" counter, so
    # a reset is the only legitimate way it goes from a high
    # number back to ``-1``.
    _last_seen_last_step: list[int] = [
        int(
            getattr(getattr(bridge, 'state', None), 'last_step', -1) or -1,
        ),
    ]

    def _reset_buffers() -> None:
        """Wipe the local replay buffer + every scope's log widget.

        Called when the engine bridge reports a reset (its
        ``state.last_step`` went backwards). Mirrors the bridge's
        own ``self._step_log.clear()`` so the data logger's view of
        history stays in lockstep with the engine's.

        Note: this intentionally does NOT call ``bridge.clear_logs()``.
        ``bridge.clear_logs()`` drains the record queue and wipes the
        backend ``appdb.timeseries`` mirror — which is destructive to
        *all* consumers (Data Logger, Performance Plot, any other
        widget). The standalone "Reset log" button on the Data Logger
        still calls ``bridge.clear_logs()`` directly via its own handler.
        """
        step_history.clear()
        _watermark[0] = -1
        for scope in _SCOPE_ORDER:
            widget = scope_log_refs[scope].get('log')
            if widget is not None:
                try:
                    widget.clear()
                except Exception:
                    pass
        info_widget = info_log_ref.get('log')
        if info_widget is not None:
            try:
                info_widget.clear()
            except Exception:
                pass

    # Per-scope refs so the flush timer and header pickers can reach
    # the right ``ui.log`` without threading them through closures.
    scope_log_refs: dict[str, dict[str, Any]] = {
        scope: {'log': None} for scope in _SCOPE_ORDER
    }
    info_log_ref: dict[str, Any] = {'log': None}
    # ``cells`` maps field_name → the cell's ``ui.element`` so the
    # active/inactive class toggling can run without rebuilding the
    # grid. ``grid_container`` is the row that hosts the cells so
    # the flush timer can rebuild the cell set if the available
    # fields change between sessions.
    scope_select_refs: dict[str, dict[str, Any]] = {
        scope: {
            'cells': {},
            'grid_container': None,
        }
        for scope in _SCOPE_ORDER
    }
    refresh_all_refs: dict[str, Any] = {'fn': None}

    # ──────────────────────────────────────────────────────────
    # Selection helpers
    # ──────────────────────────────────────────────────────────

    def _selected_for_scope(scope: str) -> list[str]:
        return [
            field
            for field in bridge.state.selected_log_fields
            if field.partition(':')[0] == scope
            or (scope == 'state' and field.startswith('meta:'))
        ]

    def _commit_selection(new_fields: list[str]) -> None:
        # Preserve original ordering relative to available_log_fields
        # so the header columns stay in a stable order.
        available = list(bridge.state.available_log_fields)
        ordered = [field for field in available if field in set(new_fields)]
        try:
            bridge.set_selected_log_fields(ordered)
        except Exception:
            pass

    def _on_scope_cell_click(scope: str, field_name: str) -> None:
        """Toggle a single signal in/out of the bridge's selection.

        Each header cell behaves like a column header in a table:
        clicking it flips that signal on/off for the scope's log.
        """
        current = list(bridge.state.selected_log_fields)
        if field_name in current:
            current = [f for f in current if f != field_name]
        else:
            current.append(field_name)
        _commit_selection(current)
        _refresh_scope_cells(scope)
        _replay_scope(scope)
        _refresh_header_label(scope)

    def _refresh_scope_cells(scope: str) -> None:
        """Repaint the active/inactive class on every cell in a scope."""
        active = set(_selected_for_scope(scope))
        cells = scope_select_refs[scope].get('cells') or {}
        for field_name, cell in cells.items():
            if cell is None:
                continue
            try:
                if field_name in active:
                    cell.classes(
                        add='data-logger-header-cell-active',
                        remove='data-logger-header-cell-inactive',
                    )
                else:
                    cell.classes(
                        add='data-logger-header-cell-inactive',
                        remove='data-logger-header-cell-active',
                    )
            except Exception:
                pass

    def _refresh_header_label(scope: str) -> None:
        """Legacy hook — the header-string preview row has been
        removed (each header cell now carries its own unit tag),
        so this is a no-op. Kept so existing call-sites (header
        record drained from the bridge, bulk actions) don't have
        to branch on whether the preview exists.
        """
        return

    # ──────────────────────────────────────────────────────────
    # Replay (per scope)
    # ──────────────────────────────────────────────────────────

    def _replay_scope(scope: str) -> None:
        widget = scope_log_refs[scope].get('log')
        if widget is None:
            return
        fields = _selected_for_scope(scope)

        try:
            widget.clear()
        except Exception:
            return

        if not fields:
            return

        # Resolve units once per replay — used for both the header
        # line and every replayed row so columns line up visually.
        units = [_unit_for_field(f, loop_signal_map) for f in fields]

        try:
            try:
                header = bridge._format_log_header(
                    fields, units=units, dcs_style=True,
                )
            except TypeError:
                header = bridge._format_log_header(fields)
            if header:
                widget.push(header)
        except Exception:
            pass

        # Replay only the tail so a huge history doesn't freeze the
        # UI when the user toggles a column.  200 rows is plenty
        # for the on-screen log view; the full history is still
        # available via CSV / JSON export.
        _REPLAY_TAIL = 200
        for entry in list(step_history)[-_REPLAY_TAIL:]:
            if not isinstance(entry, dict):
                continue
            row = _format_scoped_row(bridge, entry, fields, units=units)
            if row:
                widget.push(row)

    def _replay_all_scopes() -> None:
        for scope in _SCOPE_ORDER:
            _replay_scope(scope)
            _refresh_header_label(scope)

    # ──────────────────────────────────────────────────────────
    # Bulk actions
    # ──────────────────────────────────────────────────────────

    def _use_outputs() -> None:
        try:
            bridge.set_selected_log_fields(
                [
                    field
                    for field in bridge.state.available_log_fields
                    if field.startswith('output:')
                ],
            )
        except Exception:
            pass
        _refresh_pickers_from_state()
        _replay_all_scopes()

    def _use_all() -> None:
        try:
            bridge.set_selected_log_fields(
                list(bridge.state.available_log_fields),
            )
        except Exception:
            pass
        _refresh_pickers_from_state()
        _replay_all_scopes()

    def _clear_all_logs() -> None:
        try:
            bridge.set_selected_log_fields(
                [
                    field
                    for field in bridge.state.available_log_fields
                    if field.startswith('output:')
                ],
            )
        except Exception:
            pass
        try:
            bridge.clear_logs()
        except Exception:
            pass
        for scope in _SCOPE_ORDER:
            widget = scope_log_refs[scope].get('log')
            if widget is not None:
                try:
                    widget.clear()
                except Exception:
                    pass
        info_widget = info_log_ref.get('log')
        if info_widget is not None:
            try:
                info_widget.clear()
            except Exception:
                pass
        step_history.clear()
        _watermark[0] = -1
        _refresh_pickers_from_state()
        _replay_all_scopes()
        ui.notify('Logs cleared', color='positive')

    def _refresh_pickers_from_state() -> None:
        for scope in _SCOPE_ORDER:
            _refresh_scope_cells(scope)
            _refresh_header_label(scope)

    # ──────────────────────────────────────────────────────────
    # Export — CSV / JSON for one scope or every selected field
    # ──────────────────────────────────────────────────────────

    def _resolve_case_name() -> str | None:
        return (
            getattr(bridge, 'case_name', None)
            or getattr(getattr(bridge, 'state', None), 'case_name', None)
        )

    def _save_scope_as(scope: str | None, fmt: str) -> None:
        """Export the current step history to ``fmt`` (csv/json).

        ``scope=None`` saves every selected field across every scope
        (matches the on-screen "all" view). Otherwise the export is
        filtered to one scope's columns.
        """
        if not step_history:
            ui.notify(
                'No log entries to save yet.',
                color='warning',
            )
            return

        selected = list(bridge.state.selected_log_fields)
        fields = _export_columns_for_scope(scope, selected)

        if not fields and scope is not None:
            # If the user hasn't picked any column for this scope,
            # fall back to every available signal in that scope so
            # the export is still useful instead of empty.
            fields = _split_fields_by_scope(
                list(bridge.state.available_log_fields),
            ).get(scope, [])
            fields = _order_fields_for_scope(
                fields, loop_order, loop_signal_map,
            )

        if not fields:
            ui.notify(
                'No columns selected to save.',
                color='warning',
            )
            return

        case_name = _resolve_case_name()

        if fmt == 'csv':
            payload = _build_csv_bytes(step_history, fields)
            filename = _build_export_filename(case_name, scope, 'csv')
            _trigger_download(payload, filename, 'text/csv')
            return

        if fmt == 'json':
            payload = _build_json_bytes(
                step_history,
                fields,
                case_name=case_name,
                scope=scope,
            )
            filename = _build_export_filename(case_name, scope, 'json')
            _trigger_download(payload, filename, 'application/json')
            return

        ui.notify(f'Unknown export format: {fmt}', color='negative')

    # ──────────────────────────────────────────────────────────
    # Header / picker row (table-header style)
    # ──────────────────────────────────────────────────────────

    def _scope_options(scope: str) -> list[str]:
        scoped = _split_fields_by_scope(
            list(bridge.state.available_log_fields),
        ).get(scope, [])
        return _order_fields_for_scope(scoped, loop_order, loop_signal_map)

    def _build_header_grid(scope: str) -> None:
        """Render the header row as one toggleable cell per signal.

        The first three cells are read-only prefix columns
        (``realtime``, ``step``, ``sim_min``) that mirror the bridge's
        ``_format_log_header`` prefix; everything after is one
        clickable column header per available scope signal. A click
        toggles that column on/off in the log below.
        """
        cells_ref = scope_select_refs[scope]['cells'] = {}

        with ui.row().classes('data-logger-header-grid'):
            # Read-only prefix columns ------------------------------
            for prefix_label in ('realtime', 'step', 'sim_min'):
                with ui.element('div').classes(
                    'data-logger-header-cell '
                    'data-logger-header-cell-readonly',
                ):
                    ui.label(prefix_label).classes(
                        'data-logger-header-cell-tag',
                    )
                    ui.label('fixed').classes(
                        'data-logger-header-cell-meta',
                    )

            # Per-signal columns ------------------------------------
            options = _scope_options(scope)
            active = set(_selected_for_scope(scope))

            if not options:
                ui.label(
                    '(no fields available for this scope)',
                ).classes('data-logger-header-grid-empty')
                return

            for field_name in options:
                _, _, tag = field_name.partition(':')
                is_active = field_name in active
                unit = _unit_for_field(field_name, loop_signal_map)

                cell = ui.element('div').classes(
                    'data-logger-header-cell '
                    + (
                        'data-logger-header-cell-active'
                        if is_active
                        else 'data-logger-header-cell-inactive'
                    ),
                )
                with cell:
                    ui.label(tag).classes(
                        'data-logger-header-cell-tag',
                    )
                    # Meta slot = inferred unit. When no unit is
                    # inferred (e.g. unusual custom tags), fall back
                    # to a thin dot character so the meta line
                    # doesn't collapse the cell height.
                    ui.label(unit or '·').classes(
                        'data-logger-header-cell-meta',
                    )

                cell.on(
                    'click',
                    lambda _event, s=scope, f=field_name: (
                        _on_scope_cell_click(s, f)
                    ),
                )
                cells_ref[field_name] = cell

    def _build_scope_card(scope: str) -> None:
        with ui.card().classes('data-logger-scope-card'):
            with ui.row().classes('data-logger-scope-card-header'):
                with ui.column().classes('data-logger-scope-title-group'):
                    ui.label(_SCOPE_TITLES[scope]).classes(
                        'data-logger-scope-title',
                    )
                    ui.label(_SCOPE_HINTS[scope]).classes(
                        'data-logger-scope-hint',
                    )

                # Per-scope save button — opens a small menu with
                # CSV / JSON for this scope only. Keeps the global
                # Save menu uncluttered for quick "save just inputs"
                # workflows.
                with ui.button(icon='save').props(
                    'flat dense round size=sm',
                ).classes('data-logger-scope-save-btn'):
                    with ui.menu().classes('data-logger-save-menu'):
                        # NiceGUI's menu_item hands the handler a
                        # ClickEventArguments; accept-and-ignore it via
                        # ``_`` so the captured ``scope`` keeps its str type
                        # for the ``_save_scope_as`` call.
                        ui.menu_item(
                            f'{_SCOPE_TITLES[scope].title()}  →  CSV',
                            lambda _, s=scope: _save_scope_as(s, 'csv'),
                        )
                        ui.menu_item(
                            f'{_SCOPE_TITLES[scope].title()}  →  JSON',
                            lambda _, s=scope: _save_scope_as(s, 'json'),
                        )

            ui.separator().classes('data-logger-separator')

            # ── Header row: one cell per signal (table-header) ──
            header_container = ui.element('div').classes(
                'data-logger-header-container',
            )
            scope_select_refs[scope]['grid_container'] = header_container
            with header_container:
                _build_header_grid(scope)

            # ── Streamed log widget for this scope ──
            log_widget = ui.log(max_lines=400).classes('data-logger-log')
            scope_log_refs[scope]['log'] = log_widget

    # ──────────────────────────────────────────────────────────
    # Layout
    # ──────────────────────────────────────────────────────────

    with ui.column().classes('data-logger-root'):
        # ── Title row ──
        with ui.row().classes('data-logger-page-title-row'):
            ui.label('DATA LOGGER').classes('data-logger-page-title')
            with ui.row().classes('data-logger-page-actions'):
                ui.button(
                    'All outputs',
                    on_click=_use_outputs,
                ).props('flat no-caps dense').classes(
                    'data-logger-action-btn',
                )
                ui.button(
                    'All fields',
                    on_click=_use_all,
                ).props('flat no-caps dense').classes(
                    'data-logger-action-btn',
                )
                ui.button(
                    'Clear log',
                    on_click=_clear_all_logs,
                ).props('flat no-caps dense').classes(
                    'data-logger-action-btn data-logger-action-btn-danger',
                )

                # ── Save menu (CSV / JSON, all scopes or per scope) ──
                # Single button that opens a Quasar menu attached to
                # itself. Each menu item triggers one export combination
                # — "All scopes → CSV" is the most common pick and
                # appears first so it's a two-click save.
                with ui.button('Save').props(
                    'flat no-caps dense icon-right=expand_more',
                ).classes('data-logger-action-btn data-logger-save-btn'):
                    with ui.menu().classes('data-logger-save-menu'):
                        ui.menu_item(
                            'All scopes  →  CSV',
                            lambda: _save_scope_as(None, 'csv'),
                        )
                        ui.menu_item(
                            'All scopes  →  JSON',
                            lambda: _save_scope_as(None, 'json'),
                        )
                        ui.separator()
                        for scope_key in _SCOPE_ORDER:
                            scope_label = _SCOPE_TITLES[scope_key].title()
                            # See note above: accept-and-ignore the
                            # ClickEventArguments NiceGUI passes so the
                            # captured scope_key stays typed as str.
                            ui.menu_item(
                                f'{scope_label} only  →  CSV',
                                lambda _, s=scope_key: _save_scope_as(s, 'csv'),
                            )
                            ui.menu_item(
                                f'{scope_label} only  →  JSON',
                                lambda _, s=scope_key: _save_scope_as(s, 'json'),
                            )

        ui.separator().classes('data-logger-separator')

        # ── Three scoped cards ──
        for scope in _SCOPE_ORDER:
            _build_scope_card(scope)

        # ── Info card at the very bottom ──
        with ui.card().classes(
            'data-logger-scope-card data-logger-info-card',
        ):
            with ui.row().classes('data-logger-scope-card-header'):
                ui.label('INFO').classes('data-logger-scope-title')
                ui.label(
                    'Run / Stop / Reset, mode changes, status messages',
                ).classes('data-logger-scope-hint')

            ui.separator().classes('data-logger-separator')

            info_log = ui.log(max_lines=200).classes(
                'data-logger-log data-logger-info-log',
            )
            info_log_ref['log'] = info_log

        # Seed each scope card with its history once everything exists.
        refresh_all_refs['fn'] = _replay_all_scopes
        _replay_all_scopes()

        # ──────────────────────────────────────────────────────
        # Flush timer
        # ──────────────────────────────────────────────────────
        def _flush_log() -> None:
            # ── Reset detection ──
            # If the engine bridge was reset (its ``state.last_step``
            # went backwards), wipe our local replay buffer and every
            # scope's log widget so the first post-reset step records
            # aren't dropped by the watermark check below. We update
            # ``_last_seen_last_step`` *before* the drain so the
            # follow-up append can pick up the new step_index.
            #
            # Exception: if the previous run finished naturally (i.e.
            # reached ``time_end``), the worker restart on a "continue"
            # legitimately re-uses ``last_step + 1`` as the next
            # step_index. In that case the bridge flips
            # ``state.natural_stop = True`` and we must NOT wipe —
            # otherwise a "continue" would erase the chart/log history
            # the user wants to keep.
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
                _reset_buffers()
            _last_seen_last_step[0] = current_last_step

            # If the available field set changed (e.g. a new session
            # rebuilt it), rebuild every scope's per-signal header
            # grid and replay current history into each scope.
            try:
                current_available = list(
                    getattr(bridge.state, 'available_log_fields', []) or [],
                )
                if current_available != last_available_fields:
                    last_available_fields[:] = current_available
                    for scope in _SCOPE_ORDER:
                        container = scope_select_refs[scope].get(
                            'grid_container',
                        )
                        if container is None:
                            continue
                        try:
                            container.clear()
                            with container:
                                _build_header_grid(scope)
                        except Exception:
                            pass
                    _replay_all_scopes()
            except Exception:
                pass

            try:
                records = bridge.drain_records()
            except Exception:
                return

            step_count_this_flush = 0
            # Buffers for batch-pushing to each scope log widget.
            # One multi-line push per scope per flush is far cheaper
            # than individual DOM updates for every row.
            _batch_by_scope: dict[str, list[str]] = {
                scope: [] for scope in _SCOPE_ORDER
            }

            for record in records:
                kind = getattr(record, 'kind', None)

                if kind == 'status':
                    info_widget = info_log_ref.get('log')
                    if info_widget is None:
                        continue
                    try:
                        # DCS-style status row: [wall-clock ms]
                        # INFO  [mode] message. The 4-char padded
                        # level (``INFO``/``WARN``/``ERR ``) keeps
                        # the boundary aligned vertically with the
                        # step rows above it; the wall-clock with
                        # milliseconds matches the ``_format_log_row``
                        # DCS prefix character-for-character.
                        timestamp = datetime.now().strftime(
                            '%Y-%m-%d %H:%M:%S.%f',
                        )[:-3]
                        mode_str = getattr(record, 'mode', '') or ''
                        mode_part = f'[{mode_str:<10}] ' if mode_str else ''
                        message = getattr(record, 'message', '')
                        # Categorise so the user can scan: a record
                        # whose message starts with the bridge's
                        # error phrases (``failed``, ``error``) is
                        # ERR, ``stopped``/``paused``/``warning``
                        # → WARN, everything else → INFO. Cheap
                        # heuristic, no API change to BridgeRecord.
                        msg_lower = str(message).lower()
                        if any(k in msg_lower for k in ('error', 'failed', 'exception')):
                            level = 'ERR '
                        elif any(k in msg_lower for k in ('stopped', 'paused', 'warn')):
                            level = 'WARN'
                        else:
                            level = 'INFO'
                        info_widget.push(
                            f'[{timestamp}] {level} {mode_part}{message}',
                        )
                    except Exception:
                        try:
                            info_widget.push(bridge.format_record(record))
                        except Exception:
                            pass
                    continue

                if kind == 'header':
                    # Header records hint that the column set may have
                    # changed; refresh the per-scope header preview so
                    # the new realtime stamp / column list shows up.
                    for scope in _SCOPE_ORDER:
                        _refresh_header_label(scope)
                    continue

                if kind == 'step':
                    step_index = getattr(record, 'step_index', None)

                    if (
                        step_index is not None
                        and step_index <= _watermark[0]
                    ):
                        continue

                    if step_index is not None:
                        _watermark[0] = step_index

                    try:
                        step_history.append(
                            {
                                'step_index': record.step_index,
                                'time_min': getattr(record, 'time_min', None),
                                'inputs': dict(getattr(record, 'inputs', {}) or {}),
                                'states': dict(getattr(record, 'states', {}) or {}),
                                'outputs': dict(getattr(record, 'outputs', {}) or {}),
                            },
                        )
                    except Exception:
                        pass

                    if step_count_this_flush < _ROWS_PER_FLUSH_CAP:
                        for scope in _SCOPE_ORDER:
                            fields = _selected_for_scope(scope)
                            if not fields:
                                continue
                            units = [
                                _unit_for_field(f, loop_signal_map)
                                for f in fields
                            ]
                            row = _format_scoped_row(
                                bridge, record, fields, units=units,
                            )
                            if row:
                                _batch_by_scope[scope].append(row)

                    step_count_this_flush += 1
                    continue

                # Anything else → push to info as a generic line.
                info_widget = info_log_ref.get('log')
                if info_widget is None:
                    continue
                try:
                    info_widget.push(bridge.format_record(record))
                except Exception:
                    pass

            # ── Batch-push accumulated rows to each scope widget ──
            # A single multi-line push per scope replaces N individual
            # DOM insertions, eliminating the visible jank at high
            # acceleration.
            for scope in _SCOPE_ORDER:
                lines = _batch_by_scope.get(scope)
                if not lines:
                    continue
                widget = scope_log_refs[scope].get('log')
                if widget is None:
                    continue
                try:
                    widget.push('\n'.join(lines))
                except Exception:
                    pass

            # If we dropped step records because of the row cap, let
            # the operator know once per flush via the info log.
            if step_count_this_flush > _ROWS_PER_FLUSH_CAP:
                skipped = step_count_this_flush - _ROWS_PER_FLUSH_CAP
                info_widget = info_log_ref.get('log')
                if info_widget is not None:
                    try:
                        info_widget.push(
                            f'… {skipped} step records skipped '
                            f'(throttled at {_ROWS_PER_FLUSH_CAP} '
                            f'per {_FLUSH_INTERVAL_S:g}s flush) …',
                        )
                    except Exception:
                        pass

        ui.timer(_FLUSH_INTERVAL_S, _flush_log)


# ──────────────────────────────────────────────────────────────
# Small event-extractor (mirrors tests/main.py)
# ──────────────────────────────────────────────────────────────

def _event_value(event: Any, fallback: Any = None) -> Any:
    """Pull the actual value out of a NiceGUI event object.

    NiceGUI on_change / update:model-value handlers receive either
    a ``ValueChangeEventArguments`` with ``.value`` set, or a
    generic event whose ``.args`` is a dict keyed by
    ``value`` / ``newValue`` / ``modelValue`` — or, for a chip
    multi-select, the new array directly.
    """
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
    elif isinstance(args, list):
        return args
    elif args is not None:
        return args

    return fallback
