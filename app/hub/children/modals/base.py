# app/hub/children/modals/base.py

"""Tunable :class:`ControllerModal` (the dialog shown when an
operator clicks a controlling element in the P&ID SVG).

Rewritten from the legacy ``app/pid/sthr/controller_modal.py``
during the v1 purge. The visual layout, JS hover effects, mode
badge sync, post-reset suppress flag, and faceplate hook are
preserved byte-for-byte — the rewrite is purely a relocation +
file split.

API contract (kept stable so v2 views only had to change import
paths):

- ``__init__(store, html_element, controller_tag, param_keys,
              param_defaults=None, title=None)``
- ``controller_tag``, ``controller_svg_id``, ``store``,
  ``dialog_is_open``, ``mode_options``, ``has_tuning``,
  ``supports_operator_output``, ``mode_select``, ``sp_input``,
  ``pv_input``, ``op_input``, ``kc_input``, ``taui_input``,
  ``taud_input``, ``apply_button``, ``param_keys``, ``param_defaults``
- ``refresh_modal_values(force_op_refresh=False, force_sp_refresh=False)``
- ``apply_mode_state(status=None)``
- ``read_only_map(status=None)``
- ``_selected_status()``
- ``_apply_numeric_value(field_name, field)``
- ``commit_mode_change(status, include_tuning)``
- ``apply_dialog_values()``
- ``set_faceplate(faceplate)`` / ``open_faceplate()``
- ``open(left=None, top=None, right=None, bottom=None)``
- ``handle_svg_click(e)``
- ``_default_value(key, fallback)``
- ``_set_field_value(field, value)`` — guarded by the focus tracker
- (transient) ``_suppress_input_push`` — set by FaceplateChild after
  a reset for one tick.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from nicegui import ui

from app import config
from app.hub.children.modals.placement import _SmartPlacementMixin
from app.hub.input_focus_tracker import (
    attach_focus_tracker,
    is_user_editing,
)
from app.hub.local_store import LocalStore


__all__ = ['ControllerModal']


class ControllerModal(_SmartPlacementMixin):
    """Generic controller modal used for different controller types."""

    def __init__(
        self,
        store: LocalStore,
        html_element: ui.element,
        controller_tag: str,
        param_keys: Dict[str, str],
        param_defaults: Dict[str, Any] | None = None,
        title: str | None = None,
    ) -> None:
        self.store = store
        self.html_element = html_element
        self.controller_tag = str(controller_tag).strip().upper()
        self.controller_svg_id = self.controller_tag.lower()
        self.param_keys = param_keys
        self.drawer_cfg = (
            config.CONTROLLER_DRAWER_CONFIG.get(self.controller_svg_id, {})
            if isinstance(config.CONTROLLER_DRAWER_CONFIG, dict)
            else {}
        )
        drawer_label = (
            self.drawer_cfg.get('label')
            if isinstance(self.drawer_cfg, dict) else None
        )
        self.title = title or str(drawer_label or f'{self.controller_tag} Parameters')

        self.dialog_is_open = False
        self.mode_syncing = False

        self.param_defaults = param_defaults or {}
        self.mode_options = {'off': 'Off', 'manual': 'Manual', 'auto': 'Automatic'}

        self.sp_unit = self._display_unit(self.controller_tag)
        self.pv_unit = self._display_unit(self.controller_tag)
        self.mv_unit = config.DISPLAY_MAP.get('vp-100', {}).get('unit', '%')
        self.kc_unit = '%CO/%TO'
        self.taui_unit = 'minutes'
        self.taud_unit = 'minutes'
        self.supports_operator_output = (
            self.controller_tag == 'TIC-100' and bool(self._engine_key('op'))
        )

        self.mode_select: Optional[ui.select] = None
        self.status_select: Optional[ui.select] = None
        self.field_refs: dict[str, ui.number] = {}

        # Optional reference to the right-drawer faceplate. When
        # the host page wires the faceplate in, clicking the modal's
        # "Face plate" button opens the drawer with this
        # controller's PV/SP/OP bargraphs instead of showing a no-op
        # notification.
        self._faceplate: Any = None

        self.sp_input: Optional[ui.number] = None
        self.pv_input: Optional[ui.number] = None
        self.op_input: Optional[ui.number] = None
        self.kc_input: Optional[ui.number] = None
        self.taui_input: Optional[ui.number] = None
        self.taud_input: Optional[ui.number] = None

        self.has_tuning = all(
            self._engine_key(key) for key in ('kc', 'tau_i', 'tau_d')
        )

        # Unique per-modal CSS class so the smart-placement JS
        # selectors only ever target THIS modal's card — there can
        # be a dozen modals on a single PID page (one per
        # controller) and they all share the
        # ``.tic-param-dialog-card`` class. Without a per-instance
        # discriminator a ``document.querySelector('.tic-param-dialog-card')``
        # would pick the first one in the DOM, not the one that
        # was just opened.
        self._dialog_uid = f'tic-param-uid-{id(self):x}'

        # Build dialog
        with ui.dialog().props('persistent') as self.dialog, \
                ui.card().classes(f'tic-param-dialog-card {self._dialog_uid}') as self.dialog_card:

            # Header — faceplate-style: tag + short title cluster
            # on the left, mode badge + close button in a single
            # right cluster. Markup mirrors :meth:`FaceplatePanel.render`
            # exactly (same ``ui.row``/``ui.column`` nesting, same
            # ``no-wrap`` Quasar prop) so the modal and the
            # persistent right-drawer faceplate read as a single
            # control surface.
            with ui.row().classes('tic-param-dialog-header no-wrap'):
                with ui.column().classes('tic-param-dialog-header-text'):
                    ui.label(self.controller_tag).classes(
                        'tic-param-dialog-tag',
                    )
                    short_title = self.title
                    if ' — ' in short_title:
                        short_title = short_title.split(' — ', 1)[1]
                    ui.label(short_title).classes(
                        'tic-param-dialog-title',
                    )

                with ui.row().classes('tic-param-dialog-header-right no-wrap'):
                    with ui.row().classes('tic-param-mode-badge') as badge_row:
                        self.mode_badge = badge_row
                        self.mode_badge_dot = ui.element('span').classes(
                            'tic-param-status-dot tic-param-status-auto',
                        )
                        self.mode_badge_text = ui.label('AUTO').classes(
                            'tic-param-mode-text',
                        )

                    ui.button(
                        icon='close', color=None,
                        on_click=self.dialog.close,
                    ).props('flat round dense size=sm').classes(
                        'tic-param-close-btn',
                    )

            with ui.column().classes('tic-param-dialog-content'):
                self._build_operation_section()
                if self.has_tuning:
                    self._build_tuning_section()

            with ui.row().classes('tic-param-footer w-full'):
                ui.button(
                    'Face plate', on_click=self.open_faceplate
                ).props('flat dense').classes('tic-param-faceplate-btn')
                self.apply_button = ui.button(
                    'Apply', on_click=self.apply_dialog_values
                ).props('flat dense').classes('tic-param-apply-btn')

        # Bind events
        if self.mode_select is not None:
            self.mode_select.on_value_change(self.on_mode_change)
        self.dialog.on('hide', self.hide_dialog)

        self._install_svg_hooks()
        try:
            self.refresh_modal_values(force_op_refresh=True)
        except Exception:
            import traceback
            import tempfile
            import os
            log_path = os.path.join(
                tempfile.gettempdir(), 'app_modal_trace.log',
            )
            with open(log_path, 'a', encoding='utf-8') as _f:
                _f.write(
                    f'=== {self.controller_tag} refresh_modal_values FAILED ===\n'
                )
                traceback.print_exc(file=_f)
                _f.write('\n')
            raise

    # -------------------------------
    # Helpers — labels, units, meta
    # -------------------------------

    def _display_unit(self, tag: str) -> str:
        key = str(tag).strip().lower()
        cfg = (
            config.DISPLAY_MAP.get(key, {})
            if isinstance(config.DISPLAY_MAP, dict) else {}
        )
        return str(cfg.get('unit', ''))

    def _engine_key(self, ui_key: str) -> Optional[str]:
        value = self.param_keys.get(ui_key)
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    def _param_meta(self, ui_key: str) -> dict[str, Any]:
        params = (
            self.drawer_cfg.get('params', [])
            if isinstance(self.drawer_cfg, dict) else []
        )
        engine_field = self._engine_key(ui_key)

        for item in params:
            if not isinstance(item, dict):
                continue
            item_field = str(item.get('field', '')).strip()
            item_key = str(item.get('key', '')).strip()
            if (engine_field and item_field == engine_field) or item_key == ui_key:
                return {
                    'min': item.get('min'),
                    'max': item.get('max'),
                    'step': item.get('step', 0.01),
                    'label': item.get('label'),
                }

        return {'min': None, 'max': None, 'step': 0.01, 'label': None}

    def _unit_from_label(self, label: Optional[str]) -> str:
        text = str(label or '').strip()
        if not text:
            return ''

        match = re.search(r'\(([^)]+)\)', text)
        if match:
            return str(match.group(1)).strip()

        lowered = text.lower()
        if lowered.endswith(' min'):
            return 'min'
        if lowered.endswith(' minutes'):
            return 'minutes'

        return ''

    def _sp_row_label(self) -> str:
        sp_field = str(self._engine_key('sp') or '').strip().lower()
        if sp_field == 'sp':
            return 'SP'
        if sp_field == 'feed_flow':
            return 'F'
        if sp_field == 'feed_temp':
            return 'Ti'
        return 'SP'

    def _sp_row_unit(self) -> str:
        sp_meta = self._param_meta('sp')
        from_label = self._unit_from_label(sp_meta.get('label'))
        if from_label:
            return from_label
        return self.sp_unit

    def _row_label_from_meta(self, ui_key: str, fallback: str) -> str:
        meta = self._param_meta(ui_key)
        raw_label = str(meta.get('label') or '').strip()
        if not raw_label:
            return fallback

        no_unit = re.sub(r'\s*\([^)]*\)\s*', '', raw_label)
        compact = no_unit.replace('Time', '').replace('time', '').strip()
        if not compact:
            return fallback

        lower = compact.lower()
        if lower.startswith('gain'):
            return 'Kc'
        if 'integral' in lower:
            return 'tauI'
        if 'derivative' in lower:
            return 'tauD'

        return fallback

    def _row_unit_from_meta(self, ui_key: str, fallback: str) -> str:
        meta = self._param_meta(ui_key)
        raw_label = str(meta.get('label') or '').strip()
        if not raw_label:
            return fallback

        if ui_key in {'kc', 'tau_i', 'tau_d'}:
            lower = raw_label.lower()
            if lower.endswith(' min'):
                return 'min'
            if lower.endswith(' minutes'):
                return 'minutes'
            if '%' in raw_label or '/' in raw_label:
                parsed = self._unit_from_label(raw_label)
                return parsed or fallback
            return fallback

        from_label = self._unit_from_label(raw_label)
        return from_label or fallback

    def _default_value(self, key: str, fallback: float) -> float:
        value = self.param_defaults.get(key, fallback)
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(fallback)

    def _coerce_float(self, value: Any) -> Optional[float]:
        if value in (None, ''):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _set_field_value(self, field: Optional[ui.number], value: Any) -> None:
        if field is None:
            return
        # ── Guard: skip the overwrite while the operator is typing ──
        # The hub's ModalChild calls ``refresh_modal_values`` every
        # tick, which in turn writes every input via this method.
        # Without this guard, an operator typing a new SP gets
        # clobbered every 50 ms by the snapshot value.
        if is_user_editing(field):
            return
        # ── Skip the write if the value is already in sync ──
        # Avoids triggering a no-op ``on_value_change`` round-trip
        # and keeps the per-tick cost down to a no-op when the
        # engine hasn't actually moved the value.
        try:
            current = field.value
            if (
                current is not None
                and current != ''
                and value is not None
                and float(current) == float(value)
            ):
                return
        except (TypeError, ValueError):
            pass
        field.value = value

    def _field_engine_key(self, field_name: str) -> Optional[str]:
        key_map = {
            'SP': 'sp',
            'PV': 'pv',
            'OP': 'op',
            'Kc': 'kc',
            'tauI': 'tau_i',
            'tauD': 'tau_d',
        }
        ui_key = key_map.get(field_name)
        return self._engine_key(ui_key) if ui_key else None

    def _apply_numeric_value(self, field_name: str, field: ui.number) -> None:
        """Write the value into the local store (engine replacement)."""
        value = self._coerce_float(field.value)
        if value is None:
            return
        engine_key = self._field_engine_key(field_name)
        if engine_key:
            self.store.set(engine_key, value)

    # -------------------------------
    # UI builders
    # -------------------------------

    def _build_number_row(
        self,
        label: str,
        field_name: str,
        default_key: str,
        unit: str,
        *,
        min_value: Optional[float],
        max_value: Optional[float],
        step: float,
        precision: int = 2,
        extra_classes: str = '',
    ) -> ui.number:
        with ui.element('div').classes('tic-param-row'):
            ui.label(label).classes('tic-param-variable')
            field = self._number_field(
                field_name,
                self._default_value(default_key, 0.0),
                precision=precision,
                min_value=min_value,
                max_value=max_value,
                step=step,
                extra_classes=extra_classes,
            )
            ui.label(unit).classes('tic-param-unit')
        return field

    def _set_readonly(self, field: Optional[ui.number], readonly: bool) -> None:
        if field is None:
            return
        if readonly:
            field.props('readonly')
            field.classes(add='tic-param-readonly-value')
        else:
            field.props(remove='readonly')
            field.classes(remove='tic-param-readonly-value')

    def _number_field(
        self, name: str, value: float, precision: int = 2,
        min_value: Optional[float] = None, max_value: Optional[float] = None,
        step: float = 0.01, extra_classes: str = '',
    ) -> ui.number:
        field = (
            ui.number(
                value=value, precision=precision,
                min=min_value, max=max_value, step=step,
            )
            .props(
                'dense borderless '
                f'tooltip="Press Enter or click Apply to commit {name}"',
            )
            .classes(f'tic-param-value {extra_classes}'.strip())
        )
        self.field_refs[name] = field

        # ── Commit on blur or Enter only ──
        # The value is held in the input until the operator confirms
        # by pressing Enter, tabbing/blurring out of the field, or
        # clicking the dialog's Apply button. The Apply path goes
        # through :meth:`apply_dialog_values` → :meth:`commit_mode_change`
        # which iterates every field and writes the value, so Apply
        # still works as a "commit all" action.
        def _commit(_=None, fld=field, key=name):
            self._apply_numeric_value(key, fld)

        for evt in ('blur', 'keydown.enter'):
            try:
                field.on(evt, _commit)
            except Exception:
                pass

        # ── Focus tracker ──
        # Wires DOM focus/blur to a transient ``_user_is_editing``
        # flag on the field. ``_set_field_value`` consults this flag
        # so the per-tick refresh doesn't clobber a value the
        # operator is typing.
        attach_focus_tracker(field)

        return field

    def _build_mode_row(self) -> None:
        with ui.element('div').classes('tic-param-row'):
            ui.label('Mode').classes('tic-param-variable')
            self.mode_select = (
                ui.select(options=self.mode_options, value='auto')
                .props('dense borderless popup-content-class="tic-param-mode-popup"')
                .classes('tic-param-mode')
            )
            self.status_select = self.mode_select
            ui.label('').classes('tic-param-unit')

    def _build_operation_section(self) -> None:
        sp_meta = self._param_meta('sp')
        sp_label = self._sp_row_label()
        sp_unit = self._sp_row_unit()
        sp_min = sp_meta.get('min') if sp_meta.get('min') is not None else 0.0
        sp_max = sp_meta.get('max') if sp_meta.get('max') is not None else 1000.0
        sp_step = float(sp_meta.get('step', 0.01) or 0.01)

        with ui.card().tight().classes('tic-param-section'):
            ui.label('Operational Parameters').classes('tic-param-section-title')
            with ui.element('div').classes('tic-param-inputs'):
                self._build_mode_row()
                self.sp_input = self._build_number_row(
                    sp_label, 'SP', 'sp', sp_unit,
                    min_value=sp_min, max_value=sp_max, step=sp_step,
                )
                self.pv_input = self._build_number_row(
                    'PV', 'PV', 'pv', self.pv_unit,
                    min_value=0.0, max_value=1000.0, step=0.01,
                )

                if self.supports_operator_output:
                    self.op_input = self._build_number_row(
                        'MV', 'OP', 'op', self.mv_unit,
                        min_value=0.0, max_value=100.0, step=0.01,
                    )

    def _build_tuning_section(self) -> None:
        kc_meta = self._param_meta('kc')
        taui_meta = self._param_meta('tau_i')
        taud_meta = self._param_meta('tau_d')
        kc_label = self._row_label_from_meta('kc', 'Kc')
        taui_label = self._row_label_from_meta('tau_i', 'tauI')
        taud_label = self._row_label_from_meta('tau_d', 'tauD')
        kc_unit = self._row_unit_from_meta('kc', self.kc_unit)
        taui_unit = self._row_unit_from_meta('tau_i', self.taui_unit)
        taud_unit = self._row_unit_from_meta('tau_d', self.taud_unit)
        kc_min = kc_meta.get('min') if kc_meta.get('min') is not None else 0.0
        taui_min = taui_meta.get('min') if taui_meta.get('min') is not None else 0.0
        taud_min = taud_meta.get('min') if taud_meta.get('min') is not None else 0.0

        with ui.card().tight().classes('tic-param-section'):
            ui.label('Controller Parameters').classes('tic-param-section-title')
            with ui.element('div').classes('tic-param-inputs'):
                self.kc_input = self._build_number_row(
                    kc_label, 'Kc', 'kc', kc_unit,
                    min_value=kc_min, max_value=kc_meta.get('max'),
                    step=float(kc_meta.get('step', 0.01) or 0.01),
                )
                self.taui_input = self._build_number_row(
                    taui_label, 'tauI', 'tau_i', taui_unit,
                    min_value=taui_min, max_value=taui_meta.get('max'),
                    step=float(taui_meta.get('step', 0.01) or 0.01),
                )
                self.taud_input = self._build_number_row(
                    taud_label, 'tauD', 'tau_d', taud_unit,
                    min_value=taud_min, max_value=taud_meta.get('max'),
                    step=float(taud_meta.get('step', 0.01) or 0.01),
                )

    # -------------------------------
    # SVG affordance + click handling
    # -------------------------------

    def _set_active(self, active: bool) -> None:
        ui.run_javascript(f'''(() => {{
            const group = document.querySelector('[id="{self.controller_svg_id}"]');
            if (group && typeof group.__tic_set_active === 'function') {{
                group.__tic_set_active({str(bool(active)).lower()});
            }}
        }})();''')

    def _install_svg_hooks(self) -> None:
        ui.run_javascript(
            f"""
            (() => {{
                const group = document.querySelector('[id="{self.controller_svg_id}"]');
                if (!group || group.__tic_affordance_attached) return;
                group.__tic_affordance_attached = true;
                let isActive = false;

                group.style.cursor = 'pointer';
                group.setAttribute('title', '{self.controller_tag}: click to edit controller parameters');

                const applyGlow = (active) => {{
                    const nodes = group.querySelectorAll('*');
                    nodes.forEach(node => {{
                        node.style.cursor = 'pointer';
                        if (node.tagName && node.tagName.toLowerCase() === 'path') {{
                            node.style.transition = 'stroke 0.15s ease';
                            node.style.stroke = active ? '#ffd600' : '#ffffff';
                        }}
                    }});
                }};

                group.__tic_set_active = (active) => {{
                    isActive = !!active;
                    applyGlow(isActive);
                }};

                group.addEventListener('mouseenter', () => applyGlow(true));
                group.addEventListener('mouseleave', () => applyGlow(isActive));
            }})();
            """
        )

        self.html_element.on(
            'click',
            self.handle_svg_click,
            js_handler='''(evt) => {
                const withId = evt.target && evt.target.closest ? evt.target.closest('[id]') : null;
                if (!withId) return;
                const rect = withId.getBoundingClientRect();
                emit({
                    target_id: withId.id,
                    left:   rect ? rect.left   : null,
                    top:    rect ? rect.top    : null,
                    right:  rect ? rect.right  : null,
                    bottom: rect ? rect.bottom : null,
                });
            }''',
        )

    # -------------------------------
    # Value sync
    # -------------------------------

    def refresh_modal_values(
        self, force_op_refresh: bool = False, force_sp_refresh: bool = False,
    ) -> None:
        # ── Suppress input push for one tick after a reset ──
        # When the engine bridge is reset, the FaceplateChild /
        # ModalChild set ``_suppress_input_push`` on this modal so
        # the store→input write below is skipped. That keeps the
        # operator's last-typed numeric values visible on screen
        # even though the store was just re-seeded to case-config
        # defaults. The mode badge and the modal's chrome still
        # refresh.
        suppress = bool(getattr(self, '_suppress_input_push', False))

        status_key = self._engine_key('status')
        status_map = {0.0: 'off', 1.0: 'manual', 2.0: 'auto'}
        if status_key is None:
            status = 'auto'
        else:
            raw_status = self.store.get(status_key, 2.0)
            try:
                raw_status = float(raw_status)
            except (TypeError, ValueError):
                raw_status = 2.0
            try:
                status = status_map.get(round(float(raw_status)), 'auto')
            except TypeError:
                status = 'auto'

        if self.mode_select is not None:
            self.mode_syncing = True
            try:
                self.mode_select.value = status
            finally:
                self.mode_syncing = False

        # Keep the faceplate-style mode badge in lockstep with the
        # Mode select. Done here (not only on user-driven
        # ``on_mode_change``) so a store-driven refresh — e.g. the
        # hub pushing AUTO→MANUAL from the engine bridge, or the
        # very first ``refresh_modal_values`` at init time when the
        # store already holds a non-default status — also updates
        # the header badge.
        self._refresh_mode_badge(status)

        # ── Skip the input-widget write if we're suppressing the
        #    post-reset push ──
        # The mode badge above is still refreshed (the user didn't
        # type it), but the SP / PV / OP / Kc / tauI / tauD inputs
        # are left as-is so the operator's last-typed value stays
        # visible until they explicitly press Enter or Apply.
        if suppress:
            self.apply_mode_state(status)
            return

        sp_engine_field = self._engine_key('sp')
        if self.sp_input is not None:
            if sp_engine_field in {'feed_flow', 'feed_temp'} and not force_sp_refresh:
                pass
            else:
                key = sp_engine_field or 'sp'
                self._set_field_value(
                    self.sp_input,
                    self.store.get(key, self._default_value('sp', 150.0)),
                )

        if self.pv_input is not None:
            key = self._engine_key('pv') or 'pv'
            self._set_field_value(
                self.pv_input,
                self.store.get(key, self._default_value('pv', 150.0)),
            )

        op_key = self._engine_key('op') or 'op'
        if self.supports_operator_output and self.op_input is not None:
            if status == 'manual' and not force_op_refresh:
                pass
            else:
                self._set_field_value(
                    self.op_input,
                    self.store.get(op_key, self._default_value('op', 82.3)),
                )

        for field_name, field in (
            ('Kc', self.kc_input),
            ('tauI', self.taui_input),
            ('tauD', self.taud_input),
        ):
            if field is None:
                continue
            engine_key = self._field_engine_key(field_name)
            if not engine_key:
                continue
            if engine_key in self.store.all():
                self._set_field_value(field, self.store.get(engine_key, 0.0))
            else:
                existing = field.value
                if existing in (None, '') or isinstance(existing, str):
                    self._set_field_value(field, 0.0)
                else:
                    self._set_field_value(field, existing)

        self.apply_mode_state(status)

    def apply_mode_state(self, status: Optional[str] = None) -> None:
        effective_status = (status or self._selected_status()).lower()

        self._set_readonly(self.pv_input, True)
        sp_engine_field = self._engine_key('sp')
        if effective_status == 'auto':
            state = {'sp': False, 'op': True, 'kc': False, 'tauI': False, 'tauD': False}
        elif effective_status == 'manual':
            state = {
                'sp': sp_engine_field not in {'feed_flow', 'feed_temp'},
                'op': False,
                'kc': True,
                'tauI': True,
                'tauD': True,
            }
        else:
            state = {'sp': True, 'op': True, 'kc': True, 'tauI': True, 'tauD': True}

        for field_name, readonly in state.items():
            self._set_readonly(
                {
                    'sp': self.sp_input,
                    'op': self.op_input,
                    'kc': self.kc_input,
                    'tauI': self.taui_input,
                    'tauD': self.taud_input,
                }[field_name],
                readonly,
            )

    def read_only_map(self, status: Optional[str] = None) -> Dict[str, bool]:
        """Return per-field readonly flags for the current mode.

        The faceplate uses this to keep its own inputs in lockstep
        with the modal: any time the mode changes (whether the
        edit came from the modal or the drawer), the drawer
        applies the same readonly flags to its inputs. PV is
        always ``True`` (process value is read-only). Mode is
        always ``False`` (the operator can always change the
        mode). The other fields follow :meth:`apply_mode_state`.
        """
        effective_status = (status or self._selected_status()).lower()
        sp_engine_field = self._engine_key('sp')

        if effective_status == 'auto':
            flags = {
                'sp': False,
                'op': True,
                'kc': False,
                'tau_i': False,
                'tau_d': False,
            }
        elif effective_status == 'manual':
            flags = {
                'sp': sp_engine_field not in {'feed_flow', 'feed_temp'},
                'op': False,
                'kc': True,
                'tau_i': True,
                'tau_d': True,
            }
        else:  # 'off' or unknown
            flags = {
                'sp': True,
                'op': True,
                'kc': True,
                'tau_i': True,
                'tau_d': True,
            }

        flags['pv'] = True   # PV is the process value — read-only
        flags['mode'] = False  # the operator can always switch mode
        return flags

    def _selected_status(self) -> str:
        if self.mode_select is None:
            return 'auto'
        value = str(self.mode_select.value or 'auto').strip().lower()
        return value if value in {'off', 'manual', 'auto'} else 'auto'

    def commit_mode_change(self, status: str, include_tuning: bool) -> None:
        status_key = self._engine_key('status')
        if status_key:
            code = {'off': 0.0, 'manual': 1.0, 'auto': 2.0}.get(status.lower(), 2.0)
            self.store.set(status_key, code)

        if include_tuning:
            self._apply_commit_value('SP', self.sp_input)
            self._apply_commit_value('Kc', self.kc_input)
            self._apply_commit_value('tauI', self.taui_input)
            self._apply_commit_value('tauD', self.taud_input)

            if self.supports_operator_output and str(status).lower() == 'manual':
                self._apply_commit_value('OP', self.op_input)

        self.refresh_modal_values(force_op_refresh=True)
        self.apply_mode_state(status)

    def _apply_commit_value(
        self, field_name: str, field: Optional[ui.number],
        write_setpoint: bool = False,
    ) -> None:
        value = self._coerce_float(field.value if field is not None else None)
        if value is None:
            return
        engine_key = self._field_engine_key(field_name)
        if engine_key:
            self.store.set(engine_key, value)

    # -------------------------------
    # Event handlers
    # -------------------------------

    def on_mode_change(self, _=None) -> None:
        if self.mode_syncing:
            return

        self.mode_syncing = True
        try:
            self.commit_mode_change(self._selected_status(), include_tuning=False)
        finally:
            self.mode_syncing = False

        self._refresh_mode_badge()

    def _refresh_mode_badge(self, status: Optional[str] = None) -> None:
        """Update the header mode badge (status dot + text)."""
        try:
            raw = status if status is not None else self._selected_status()
            status = str(raw or 'auto').strip().lower()
        except Exception:
            status = 'auto'

        if self.mode_badge_dot is not None:
            cls_map = {
                'off': 'tic-param-status-off',
                'manual': 'tic-param-status-manual',
                'auto': 'tic-param-status-auto',
            }
            for cls in cls_map.values():
                try:
                    self.mode_badge_dot.classes(remove=cls)
                except Exception:
                    pass
            try:
                self.mode_badge_dot.classes(add=cls_map.get(status, cls_map['auto']))
            except Exception:
                pass

        if self.mode_badge_text is not None:
            try:
                self.mode_badge_text.set_text(status.upper())
            except Exception:
                pass

    def apply_dialog_values(self) -> None:
        if self.mode_syncing:
            return

        try:
            self.mode_syncing = True
            self.commit_mode_change(self._selected_status(), include_tuning=True)
        except Exception as exc:
            ui.notify(f'Failed to apply parameters: {exc}', color='negative')
        else:
            ui.notify(f'{self.controller_tag} parameters applied', color='positive')
        finally:
            self.mode_syncing = False

    def hide_dialog(self) -> None:
        self.dialog_is_open = False
        self._set_active(False)

    def set_faceplate(self, faceplate: Any) -> None:
        """Attach the right-drawer faceplate to this modal."""
        self._faceplate = faceplate

    def open_faceplate(self) -> None:
        faceplate = getattr(self, '_faceplate', None)
        if faceplate is not None and hasattr(faceplate, 'open_for'):
            try:
                faceplate.open_for(self.controller_tag)
                return
            except Exception:
                pass
        ui.notify(f'{self.controller_tag} face plate opened')

    def open(
        self,
        left: Optional[float] = None,
        top: Optional[float] = None,
        right: Optional[float] = None,
        bottom: Optional[float] = None,
    ) -> None:
        del left, top, right, bottom  # explicitly unused

        self.refresh_modal_values(force_op_refresh=True)
        self.dialog_is_open = True
        self._set_active(True)

        self.dialog.open()
        self._apply_manual_position_js()

    def handle_svg_click(self, e) -> None:
        target_id = None
        left = None
        top = None
        right = None
        bottom = None

        if hasattr(e, 'args') and isinstance(e.args, dict):
            target_id = e.args.get('target_id')
            left = e.args.get('left')
            top = e.args.get('top')
            right = e.args.get('right')
            bottom = e.args.get('bottom')

        if not target_id:
            return

        try:
            controller_map = getattr(self.html_element, 'controller_modals', None)
        except Exception:
            controller_map = None

        if isinstance(controller_map, dict):
            modal = controller_map.get(target_id)
            if modal:
                try:
                    modal.open(left=left, top=top, right=right, bottom=bottom)
                except Exception:
                    if target_id == self.controller_svg_id:
                        self.open(left=left, top=top, right=right, bottom=bottom)
                return

        if target_id == self.controller_svg_id:
            self.open(left=left, top=top, right=right, bottom=bottom)
