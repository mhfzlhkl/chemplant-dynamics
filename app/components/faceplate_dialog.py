# app/components/faceplate_dialog.py

"""Faceplate — dialog-based, draggable, resizable, minimizable.

The original faceplate was a *right-side drawer* built from raw
``<aside class="pid-right-drawer">`` + CSS class toggling via
``ui.run_javascript``. This module replaces that approach with a
proper :class:`ui.dialog` (via the
:class:`app.components.floating_window.DraggableCard` helper)
that mirrors the Runtime Manager dialog's affordances:

* **Draggable** — pointer-event drag on the card header.
* **Resizable** — 8 invisible JS handles (N/E/S/W + NE/SE/SW/NW).
* **Minimizable** — the operator can collapse the body to a
  header strip (the same affordance the runtime manager offers
  when an operator "shelves" a faceplate).
* **Position + size persisted** to ``sessionStorage`` per case,
  so the operator's preferred placement survives close / reopen
  and tab switches.

The body content (tag/title header, mode badge, operational +
tuning inputs, Apply button, three vertical bargraphs) is the
same UI as the legacy drawer — only the host changed. The
content is wrapped in a card with class
``faceplate-dialog-card`` so the DraggableCard JS finders can
locate it across Quasar DOM swaps. The card's header row (tag +
title + mode badge + close + minimize buttons) is the drag
handle, marked with class ``faceplate-dialog-header``.

Backward-compatibility surface
------------------------------

* :class:`FaceplateDialog` exposes the same public methods the
  legacy :class:`app.components.faceplate.FaceplatePanel` did:
  ``register_modal``, ``open_for``, ``close``, ``refresh``,
  ``set_drawer`` (now a no-op — there is no drawer to attach to).
* :class:`FaceplateSpec` is re-exported from
  :mod:`app.components.faceplate` so existing imports
  (``from app.components.faceplate import FaceplateSpec``) keep
  working — the legacy module becomes a thin re-export + spec
  helper.

The dialog is constructed lazily: ``__init__`` does not create
the ``ui.dialog``; the host page calls :meth:`build` after
registering all modals so the body has a full set of
``_modals`` / ``_specs`` to draw from on first ``open_for``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from nicegui import ui

from app import config as app_config
from app.components.floating_window import DraggableCard
from app.components.faceplate import FaceplateSpec
from app.hub.input_focus_tracker import (
    attach_focus_tracker,
    is_user_editing,
)


# CSS classes the DraggableCard JS uses to find the card and
# header. Keeping them as module-level constants so the CSS in
# ``app/static/css/faceplate.css`` (or wherever the new
# faceplate styles land) can target them by name.
CARD_CLASS = 'faceplate-dialog-card'
HEADER_CLASS = 'faceplate-dialog-header'


@dataclass(frozen=True)
class FaceplateDialogConfig:
    """Static config for a single per-page :class:`FaceplateDialog`.

    ``case_slug`` is used to scope the drag/resize persistence
    keys in ``sessionStorage`` so two open control panels (e.g.
    sthr + biodiesel in two tabs) don't clobber each other.

    ``on_close`` and ``on_minimize`` are forwarded from the
    runtime manager pattern — they let the host subscribe to
    dialog lifecycle events without subclassing.
    """

    case_slug: str
    on_close: Optional[Callable[[], None]] = None
    on_minimize: Optional[Callable[[], None]] = None


class FaceplateDialog:
    """Floating, draggable faceplate dialog for one case page.

    The dialog is constructed lazily by :meth:`build`; the host
    page calls ``build()`` after constructing this instance and
    then opens it on demand via :meth:`open_for`.
    """

    def __init__(self, config: FaceplateDialogConfig) -> None:
        self._case_slug = str(config.case_slug)
        self._on_close = config.on_close
        self._on_minimize = config.on_minimize

        # tag (uppercase) -> modal instance
        self._modals: Dict[str, Any] = {}
        # tag -> FaceplateSpec
        self._specs: Dict[str, FaceplateSpec] = {}
        # Currently displayed tag, or None when dialog is closed
        self._active_tag: Optional[str] = None

        # DOM element handles rebuilt every time the active
        # tag changes. The list mirrors the legacy
        # FaceplatePanel — all of these are populated by
        # :meth:`_render_body` and updated by :meth:`refresh`.
        self._tag_label: Optional[ui.label] = None
        self._title_label: Optional[ui.label] = None
        self._mode_badge: Optional[ui.label] = None
        self._status_dot: Optional[ui.element] = None

        # Three bargraphs (PV, SP, OP)
        self._pv_fill: Optional[ui.element] = None
        self._pv_value: Optional[ui.label] = None
        self._pv_marker: Optional[ui.element] = None
        self._sp_fill: Optional[ui.element] = None
        self._sp_value: Optional[ui.label] = None
        self._op_fill: Optional[ui.element] = None
        self._op_value: Optional[ui.label] = None

        # Direct references to the bargraph columns (used to
        # hide SP/OP for read-only indicators without
        # traversing the DOM via ``parent_element``).
        self._pv_col: Optional[ui.column] = None
        self._sp_col: Optional[ui.column] = None
        self._op_col: Optional[ui.column] = None

        # Live value label below the bargraphs
        self._pv_unit_label: Optional[ui.label] = None
        self._sp_unit_label: Optional[ui.label] = None
        self._op_unit_label: Optional[ui.label] = None

        # Extended controls
        self._mode_select: Optional[ui.select] = None
        self._sp_input: Optional[ui.number] = None
        self._pv_input: Optional[ui.number] = None
        self._op_input: Optional[ui.number] = None
        self._kc_input: Optional[ui.number] = None
        self._taui_input: Optional[ui.number] = None
        self._taud_input: Optional[ui.number] = None
        self._apply_btn: Optional[ui.button] = None

        # Row containers for sections (hidden when irrelevant)
        self._op_row: Optional[Any] = None
        self._tuning_section: Optional[Any] = None
        self._bars_row: Optional[ui.element] = None

        # The DraggableCard helper is constructed here; the
        # actual ``ui.dialog`` is built in :meth:`build`.
        self._card = DraggableCard(
            case_slug=self._case_slug,
            card_class=CARD_CLASS,
            header_class=HEADER_CLASS,
            install_resize_handles=True,
            min_width=320,
            min_height=360,
            position_storage_key=f'faceplateDialog:{self._case_slug}',
            size_storage_key=f'faceplateDialogSize:{self._case_slug}',
            drawer_offset_var='--faceplate-drawer-offset',
        )

    # Registration

    def register_modal(
        self,
        modal: Any,
        *,
        spec: Optional[FaceplateSpec] = None,
    ) -> None:
        """Register a controller/indicator modal with the dialog.

        Mirrors the legacy :class:`FaceplatePanel.register_modal`
        so existing call sites don't need to change. If
        ``spec`` is not provided, the dialog infers a default
        :class:`FaceplateSpec` from the modal's public
        attributes (``controller_tag``, ``pv_unit``, ``mv_unit``,
        ``param_keys``, ``has_tuning``,
        ``supports_operator_output``).
        """
        tag = str(getattr(modal, 'controller_tag', '')).strip().upper()
        if not tag:
            return
        self._modals[tag] = modal
        if spec is not None:
            self._specs[tag] = spec
        else:
            self._specs[tag] = self._infer_spec(modal)

    def _infer_spec(self, modal: Any) -> FaceplateSpec:
        """Build a :class:`FaceplateSpec` from a modal's public API.

        Read-only modals (no SP, no OP) collapse to a single PV
        bargraph. Tunable modals keep all three bargraphs.
        """
        tag = str(getattr(modal, 'controller_tag', '')).strip().upper()
        svg_id = tag.lower()

        # Unit / range resolution
        pv_unit = str(getattr(modal, 'pv_unit', '') or '') \
            or str(getattr(modal, 'unit', '') or '')
        sp_unit = pv_unit
        op_unit = str(getattr(modal, 'mv_unit', '') or '%')

        # Range lookups via the existing CONTROLLER_DRAWER_CONFIG
        cfg = app_config.CONTROLLER_DRAWER_CONFIG.get(svg_id, {}) \
            if isinstance(app_config.CONTROLLER_DRAWER_CONFIG, dict) else {}
        params = cfg.get('params', []) if isinstance(cfg, dict) else []

        def _range(ui_key: str, fallback: tuple) -> tuple:
            for item in params:
                if not isinstance(item, dict):
                    continue
                if item.get('key') == ui_key or item.get('field') == ui_key:
                    lo = item.get('min')
                    hi = item.get('max')
                    if lo is not None and hi is not None:
                        return float(lo), float(hi)
            return fallback

        sp_min, sp_max = _range('sp', (0.0, 1000.0))
        if svg_id == 'fi-101':
            sp_min, sp_max = _range('feed_flow', (0.0, 200.0))
        if svg_id == 'ti-100':
            sp_min, sp_max = _range('feed_temp', (50.0, 250.0))

        # PV range: same as SP range for most controllers; for
        # read-only indicators use sensible per-tag defaults.
        pv_min, pv_max = sp_min, sp_max
        if not params:
            if 'lb/min' in pv_unit:
                pv_min, pv_max = 0.0, 100.0
            elif '%' in pv_unit and (
                'vp' in svg_id or 'valve' in svg_id.lower()
            ):
                pv_min, pv_max = 0.0, 100.0
            elif 'ft³' in pv_unit:
                pv_min, pv_max = 0.0, 200.0
            else:
                pv_min, pv_max = 0.0, 100.0

        has_tuning = bool(getattr(modal, 'has_tuning', False))
        has_mode = (
            not isinstance(modal, type(None))
            and hasattr(modal, 'mode_options')
        )
        has_op = bool(getattr(modal, 'supports_operator_output', False))

        # Bargraph layout — only tunable controllers (TIC-100
        # with Kc/τI/τD) keep the full three-bar layout. All
        # other controllers collapse to a single PV bar.
        show_sp_bar = bool(has_tuning)
        show_op_bar = bool(has_tuning)

        # Decimal places from the live flusher's per-tag map.
        decimals_map = {
            'tic-100': (1, 1, 1),
            'fi-100':  (2, 1, 1),
            'fi-101':  (1, 1, 1),
            'ti-100':  (1, 1, 1),
            'li-100':  (1, 1, 1),
            'fi-102':  (1, 1, 1),
            'vp-100':  (1, 1, 1),
        }
        pv_d, sp_d, op_d = decimals_map.get(svg_id, (1, 1, 1))

        return FaceplateSpec(
            tag=tag,
            svg_id=svg_id,
            title=str(getattr(modal, 'title', tag) or tag),
            pv_unit=pv_unit,
            sp_unit=sp_unit,
            op_unit=op_unit,
            pv_min=pv_min,
            pv_max=pv_max,
            sp_min=sp_min,
            sp_max=sp_max,
            op_min=0.0,
            op_max=100.0,
            pv_decimals=pv_d,
            sp_decimals=sp_d,
            op_decimals=op_d,
            has_mode=has_mode,
            has_op=has_op,
            has_tuning=has_tuning,
            show_sp_bar=show_sp_bar,
            show_op_bar=show_op_bar,
        )

    # Build

    def build(self) -> 'FaceplateDialog':
        """Build the dialog (idempotent within an instance).

        Emits the faceplate body inside a card with class
        ``faceplate-dialog-card`` so the DraggableCard JS
        finders can locate it across Quasar DOM swaps.
        """
        self._card.build(self._build_body)
        return self

    def _build_body(self, card: DraggableCard) -> None:
        """Render the faceplate body (called by DraggableCard.build).

        Layout (top → bottom):

            ┌─ Header (tag, title, mode badge, minimize, close) ─┐
            ├─ Operational Parameters (Mode/SP/PV/OP) ───────────┤
            ├─ Controller Parameters (Kc/τI/τD) ─────────────────┤
            ├─ Apply button ─────────────────────────────────────┤
            ├─ Separator ────────────────────────────────────────┤
            └─ Three small vertical bargraphs (PV/SP/OP) ────────┘
        """
        with ui.card().classes(
            f'w-full faceplate-root {CARD_CLASS}',
        ):
            # Header — tag, title, mode badge, minimize + close.
            # This row is the drag handle; the class must match
            # the DraggableCard's ``header_class`` config.
            with ui.row().classes(
                f'faceplate-header {HEADER_CLASS} no-wrap',
            ):
                with ui.column().classes('faceplate-header-text'):
                    self._tag_label = ui.label('—').classes('faceplate-tag')
                    self._title_label = ui.label(
                        'Select a controller',
                    ).classes('faceplate-title')
                with ui.row().classes(
                    'faceplate-header-right no-wrap',
                ):
                    with ui.row().classes('faceplate-mode-badge'):
                        self._status_dot = (
                            ui.element('span')
                            .classes(
                                'faceplate-status-dot '
                                'faceplate-status-auto',
                            )
                        )
                        self._mode_badge = ui.label('AUTO').classes(
                            'faceplate-mode-text',
                        )
                    # Minimize button. The runtime manager's
                    # DraggableCard registration tuple convention
                    # keeps icon + tooltip in lockstep.
                    minimize_btn = (
                        ui.button(
                            icon='horizontal_rule', color=None,
                        )
                        .props('flat round dense size=sm')
                        .classes('faceplate-minimize-btn')
                    )
                    minimize_btn.on(
                        'click',
                        lambda _,
                        c=card: (
                            c.toggle_minimize(),
                            self._on_minimize() if self._on_minimize
                            else None,
                        ),
                    )
                    minimize_tooltip = ui.tooltip('Minimize')
                    card.register_minimize_button(
                        minimize_btn, minimize_tooltip,
                    )
                    ui.button(
                        icon='close', color=None,
                    ).props('flat round dense size=sm').classes(
                        'faceplate-close-btn',
                    ).on(
                        'click',
                        lambda _: (
                            self.close(),
                            self._on_close() if self._on_close
                            else None,
                        ),
                    )

            # Extended controls — operational parameters.
            with ui.column().classes('faceplate-section'):
                ui.label('Operational Parameters').classes(
                    'faceplate-section-title',
                )
                with ui.element('div').classes('faceplate-input-row'):
                    ui.label('Mode').classes('faceplate-input-label')
                    self._mode_select = (
                        ui.select(
                            options={
                                'off': 'Off',
                                'manual': 'Manual',
                                'auto': 'Auto',
                            },
                            value='auto',
                        )
                        .props(
                            'dense borderless '
                            'popup-content-class="faceplate-mode-popup"',
                        )
                        .classes(
                            'faceplate-input-field faceplate-mode-select',
                        )
                    )
                    self._mode_select.on_value_change(self._on_mode_change)
                    ui.label('').classes('faceplate-input-unit')

                with ui.element('div').classes('faceplate-input-row'):
                    ui.label('SP').classes('faceplate-input-label')
                    self._sp_input = self._build_input(
                        'SP', 0.0, 1000.0, 0.01, field_name='SP',
                    )
                    ui.label('').classes(
                        'faceplate-input-unit faceplate-input-unit-sp',
                    )

                with ui.element('div').classes('faceplate-input-row'):
                    ui.label('PV').classes('faceplate-input-label')
                    self._pv_input = self._build_input(
                        'PV', 0.0, 1000.0, 0.01,
                        readonly=True, field_name='PV',
                    )
                    ui.label('').classes(
                        'faceplate-input-unit faceplate-input-unit-pv',
                    )

                self._op_row = ui.element('div').classes(
                    'faceplate-input-row',
                )
                with self._op_row:
                    ui.label('OP').classes('faceplate-input-label')
                    self._op_input = self._build_input(
                        'OP', 0.0, 100.0, 0.01, field_name='OP',
                    )
                    ui.label('').classes(
                        'faceplate-input-unit faceplate-input-unit-op',
                    )

            # Extended controls — tuning.
            self._tuning_section = ui.column().classes(
                'faceplate-section',
            )
            with self._tuning_section:
                ui.label('Controller Parameters').classes(
                    'faceplate-section-title',
                )
                with ui.element('div').classes('faceplate-input-row'):
                    ui.label('Kc').classes('faceplate-input-label')
                    self._kc_input = self._build_input(
                        'Kc', 0.0, 50.0, 0.01, field_name='Kc',
                    )
                    ui.label('%CO/%TO').classes('faceplate-input-unit')
                with ui.element('div').classes('faceplate-input-row'):
                    ui.label('τI').classes('faceplate-input-label')
                    self._taui_input = self._build_input(
                        'tauI', 0.01, 100.0, 0.01, field_name='tauI',
                    )
                    ui.label('min').classes('faceplate-input-unit')
                with ui.element('div').classes('faceplate-input-row'):
                    ui.label('τD').classes('faceplate-input-label')
                    self._taud_input = self._build_input(
                        'tauD', 0.0, 50.0, 0.01, field_name='tauD',
                    )
                    ui.label('min').classes('faceplate-input-unit')

            # Apply button.
            self._apply_btn = ui.button(
                'Apply', color=None,
            ).props('flat dense').classes('faceplate-apply-btn')
            self._apply_btn.on('click', self._on_apply)

            ui.separator().classes('faceplate-section-separator')

            # Vertical bargraphs.
            self._bars_row = ui.element('div').classes(
                'faceplate-bars faceplate-bars-3',
            )
            with self._bars_row:
                self._pv_col = ui.column().classes('faceplate-bar-col')
                with self._pv_col:
                    ui.label('PV').classes(
                        'faceplate-bar-label faceplate-bar-label-pv',
                    )
                    with ui.element('div').classes('faceplate-bar-track'):
                        self._pv_fill = (
                            ui.element('div')
                            .classes(
                                'faceplate-bar-fill '
                                'faceplate-bar-fill-pv',
                            )
                        )
                        self._pv_marker = (
                            ui.element('div')
                            .classes('faceplate-bar-sp-marker')
                        )
                    self._pv_value = ui.label('—').classes(
                        'faceplate-bar-value',
                    )
                    self._pv_unit_label = ui.label('').classes(
                        'faceplate-bar-unit',
                    )

                self._sp_col = ui.column().classes('faceplate-bar-col')
                with self._sp_col:
                    ui.label('SP').classes(
                        'faceplate-bar-label faceplate-bar-label-sp',
                    )
                    with ui.element('div').classes('faceplate-bar-track'):
                        self._sp_fill = (
                            ui.element('div')
                            .classes(
                                'faceplate-bar-fill '
                                'faceplate-bar-fill-sp',
                            )
                        )
                    self._sp_value = ui.label('—').classes(
                        'faceplate-bar-value',
                    )
                    self._sp_unit_label = ui.label('').classes(
                        'faceplate-bar-unit',
                    )

                self._op_col = ui.column().classes('faceplate-bar-col')
                with self._op_col:
                    ui.label('OP').classes(
                        'faceplate-bar-label faceplate-bar-label-op',
                    )
                    with ui.element('div').classes('faceplate-bar-track'):
                        self._op_fill = (
                            ui.element('div')
                            .classes(
                                'faceplate-bar-fill '
                                'faceplate-bar-fill-op',
                            )
                        )
                    self._op_value = ui.label('—').classes(
                        'faceplate-bar-value',
                    )
                    self._op_unit_label = ui.label('').classes(
                        'faceplate-bar-unit',
                    )

            # Initial placeholder.
            self._set_bar(self._pv_fill, 0.0)
            self._set_bar(self._sp_fill, 0.0)
            self._set_bar(self._op_fill, 0.0)

    # Public API — mirrors FaceplatePanel

    def open_for(self, tag: str) -> None:
        """Open (or refocus) the faceplate on ``tag``."""
        tag = str(tag).strip().upper()
        if tag not in self._modals:
            return
        self._active_tag = tag
        self._rebuild_active_body()
        self._card.open()
        # Pull the latest values from the modal's store
        self.refresh()

    def close(self) -> None:
        """Close the faceplate dialog."""
        self._active_tag = None
        self._card.close()

    def toggle(self) -> None:
        """Open the dialog if hidden, close it if visible."""
        self._card.toggle()

    @property
    def card(self) -> DraggableCard:
        """The underlying DraggableCard helper (for testing)."""
        return self._card

    def set_drawer(self, drawer: Any) -> None:
        """No-op kept for backward compatibility with FaceplatePanel.

        The dialog is hosted in a Quasar ``<q-dialog>`` portal,
        not a page aside, so there is no drawer element to
        attach to. The argument is accepted but ignored.
        """
        del drawer  # explicitly unused

    # Live refresh — called by the page's live flusher

    def refresh(self) -> None:
        """Update bargraph fills, numeric labels, and the SP marker.

        Safe to call when the dialog is closed (no-op) or when
        no tag is active (no-op). Mirrors the legacy
        :class:`FaceplatePanel.refresh` exactly so the
        :class:`app.hub.children.FaceplateChild` can drive
        either implementation.
        """
        if not self._active_tag:
            return
        if (
            self._pv_fill is None
            or self._sp_fill is None
            or self._op_fill is None
        ):
            return

        modal = self._modals.get(self._active_tag)
        spec = self._specs.get(self._active_tag)
        if modal is None or spec is None:
            return

        # Post-reset input-push suppression. The live flusher
        # sets ``_suppress_input_push`` on this dialog for one
        # tick after an engine reset. We still repaint the
        # bargraphs and SP marker (those reflect simulation
        # state, not operator input) but skip the
        # store→input write below so the operator's last-typed
        # numeric values stay on screen.
        suppress = bool(getattr(self, '_suppress_input_push', False))

        # PV
        pv = self._read_field(modal, 'pv', fallback=spec.pv_min)
        pv_pct = self._to_percent(pv, spec.pv_min, spec.pv_max)
        self._set_bar(self._pv_fill, pv_pct)
        if self._pv_value is not None:
            self._pv_value.set_text(self._fmt(pv, spec.pv_decimals))
        if self._pv_marker is not None:
            sp = self._read_field(modal, 'sp', fallback=spec.sp_min)
            sp_pct = self._to_percent(sp, spec.pv_min, spec.pv_max)
            self._set_marker(self._pv_marker, sp_pct)

        # SP
        if spec.show_sp_bar:
            sp = self._read_field(modal, 'sp', fallback=spec.sp_min)
            sp_pct = self._to_percent(sp, spec.sp_min, spec.sp_max)
            self._set_bar(self._sp_fill, sp_pct)
            if self._sp_value is not None:
                self._sp_value.set_text(self._fmt(sp, spec.sp_decimals))

        # OP
        if spec.show_op_bar:
            op = self._read_field(modal, 'op', fallback=spec.op_min)
            op_pct = self._to_percent(op, spec.op_min, spec.op_max)
            self._set_bar(self._op_fill, op_pct)
            if self._op_value is not None:
                self._op_value.set_text(self._fmt(op, spec.op_decimals))

        # Mode badge.
        try:
            status = (
                modal._selected_status()
                if hasattr(modal, '_selected_status') else 'auto'
            )
        except Exception:
            status = 'auto'

        if self._mode_badge is not None:
            self._mode_badge.set_text(status.upper())
            if self._status_dot is not None:
                cls_map = {
                    'off': 'faceplate-status-off',
                    'manual': 'faceplate-status-manual',
                    'auto': 'faceplate-status-auto',
                }
                for cls in cls_map.values():
                    self._status_dot.classes(remove=cls)
                self._status_dot.classes(
                    add=cls_map.get(status, 'faceplate-status-auto'),
                )

        if not suppress:
            self._sync_input_from_store(
                self._sp_input,
                'sp',
                self._read_field(modal, 'sp', fallback=spec.sp_min),
            )
            self._sync_input_from_store(
                self._pv_input,
                'pv',
                self._read_field(modal, 'pv', fallback=spec.pv_min),
            )
            if spec.show_op_bar and self._op_input is not None:
                self._sync_input_from_store(
                    self._op_input,
                    'op',
                    self._read_field(modal, 'op', fallback=spec.op_min),
                )
            self._sync_input_from_store(
                self._kc_input,
                'kc',
                self._read_field(modal, 'kc', fallback=0.0),
            )
            self._sync_input_from_store(
                self._taui_input,
                'tau_i',
                self._read_field(modal, 'tau_i', fallback=0.0),
            )
            self._sync_input_from_store(
                self._taud_input,
                'tau_d',
                self._read_field(modal, 'tau_d', fallback=0.0),
            )

        # Readonly state — keep the dialog inputs in lockstep
        # with the modal's per-mode readonly map.
        try:
            ro_map = (
                modal.read_only_map(status)
                if hasattr(modal, 'read_only_map') else None
            )
        except Exception:
            ro_map = None
        if ro_map:
            self._apply_readonly_map(ro_map, spec)

    # Body rebuild — re-renders tag-specific sections when the
    # active tag changes.

    def _rebuild_active_body(self) -> None:
        tag = self._active_tag
        if not tag:
            return
        modal = self._modals.get(tag)
        spec = self._specs.get(tag)
        if modal is None or spec is None:
            return

        # Header
        if self._tag_label is not None:
            self._tag_label.set_text(spec.tag)
        if self._title_label is not None:
            self._title_label.set_text(spec.title)
        if self._pv_unit_label is not None:
            self._pv_unit_label.set_text(spec.pv_unit)
        if self._sp_unit_label is not None:
            self._sp_unit_label.set_text(spec.sp_unit)
        if self._op_unit_label is not None:
            self._op_unit_label.set_text(spec.op_unit)

        # SP / OP bargraph visibility
        if self._sp_col is not None:
            self._sp_col.set_visibility(spec.show_sp_bar)
        if self._op_col is not None:
            self._op_col.set_visibility(spec.show_op_bar)
        if self._bars_row is not None:
            visible_count = (
                (1 if spec.show_sp_bar else 0)
                + (1 if spec.show_op_bar else 0)
                + 1
            )
            try:
                self._bars_row.classes(
                    remove='faceplate-bars-1 faceplate-bars-3',
                )
                self._bars_row.classes(
                    add=(
                        'faceplate-bars-3' if visible_count == 3
                        else 'faceplate-bars-1'
                    ),
                )
            except Exception:
                pass

        # Extended controls
        if self._mode_select is not None:
            mode_value = 'auto'
            try:
                mode_value = modal._selected_status()
            except Exception:
                pass
            self._mode_select.value = mode_value
            self._mode_select.set_visibility(spec.has_mode)

        for inp, ui_key, default in (
            (self._sp_input, 'sp', spec.sp_min),
            (self._pv_input, 'pv', spec.pv_min),
            (self._op_input, 'op', spec.op_min),
            (self._kc_input, 'kc', 0.0),
            (self._taui_input, 'tau_i', 0.0),
            (self._taud_input, 'tau_d', 0.0),
        ):
            if inp is None:
                continue
            try:
                val = modal._default_value(ui_key, default)
            except Exception:
                val = default
            inp.value = val

        if self._op_row is not None:
            self._op_row.set_visibility(spec.has_op)
        if self._tuning_section is not None:
            self._tuning_section.set_visibility(spec.has_tuning)
        if self._apply_btn is not None:
            self._apply_btn.set_visibility(spec.has_tuning or spec.has_mode)

    # Internal helpers

    def _build_input(
        self,
        name: str,
        min_value: float,
        max_value: float,
        step: float,
        *,
        readonly: bool = False,
        field_name: Optional[str] = None,
    ) -> ui.number:
        """Build a small numeric input matching the faceplate's row grid."""
        field = (
            ui.number(value=0.0, min=min_value, max=max_value, step=step)
            .props(
                'dense borderless'
                + (' readonly' if readonly else '')
                + (
                    f' tooltip="Press Enter or click Apply to commit {name}"'
                    if not readonly else ''
                ),
            )
            .classes('faceplate-input-field')
        )

        attach_focus_tracker(field)

        if field_name and not readonly:
            modal_field = field_name

            def _commit(_=None, fld=field, m_field=modal_field):
                modal = None
                if self._active_tag:
                    modal = self._modals.get(self._active_tag)
                if modal is None:
                    return
                apply = getattr(modal, '_apply_numeric_value', None)
                if callable(apply):
                    try:
                        apply(m_field, fld)
                    except Exception:
                        pass

            for evt in ('blur', 'keydown.enter'):
                try:
                    field.on(evt, _commit)
                except Exception:
                    pass

        return field

    def _on_mode_change(self, _=None) -> None:
        """Route the Mode select edit into the active modal."""
        if not self._active_tag:
            return
        modal = self._modals.get(self._active_tag)
        if modal is None or self._mode_select is None:
            return
        commit = getattr(modal, 'commit_mode_change', None)
        if not callable(commit):
            return
        try:
            commit(
                str(self._mode_select.value or 'auto'),
                include_tuning=False,
            )
        except Exception:
            pass
        self.refresh()

    def _sync_input_from_store(
        self,
        field: Optional[ui.number],
        _key: str,
        value: Any,
    ) -> None:
        """Push a fresh store value into a dialog input.

        Skips the write if the field is currently focused (so
        we don't clobber the user's in-progress text) and
        skips the write if the value is already in sync.
        """
        if field is None:
            return
        if is_user_editing(field):
            return
        try:
            current = field.value
        except Exception:
            current = None
        try:
            if current is not None and current != '' and value is not None:
                if float(current) == float(value):
                    return
        except (TypeError, ValueError):
            if str(current) == str(value):
                return
        try:
            field.value = value
        except Exception:
            pass

    def _set_field_readonly(
        self,
        field: Optional[Any],
        readonly: bool,
    ) -> None:
        """Toggle the readonly state of a dialog input."""
        if field is None:
            return
        try:
            if readonly:
                field.props('readonly')
                field.classes(add='faceplate-readonly')
            else:
                field.props(remove='readonly')
                field.classes(remove='faceplate-readonly')
        except Exception:
            pass

    def _apply_readonly_map(
        self,
        ro_map: Dict[str, bool],
        spec: FaceplateSpec,
    ) -> None:
        """Apply the modal's per-mode readonly flags to dialog inputs."""
        if self._mode_select is not None:
            self._set_field_readonly(
                self._mode_select,
                bool(ro_map.get('mode', False)),
            )

        self._set_field_readonly(
            self._sp_input,
            bool(ro_map.get('sp', True)) if spec.show_sp_bar else True,
        )
        self._set_field_readonly(
            self._pv_input,
            bool(ro_map.get('pv', True)),
        )
        if self._op_input is not None and spec.has_op:
            self._set_field_readonly(
                self._op_input,
                bool(ro_map.get('op', True)),
            )

        if spec.has_tuning:
            self._set_field_readonly(
                self._kc_input,
                bool(ro_map.get('kc', True)),
            )
            self._set_field_readonly(
                self._taui_input,
                bool(ro_map.get('tau_i', True)),
            )
            self._set_field_readonly(
                self._taud_input,
                bool(ro_map.get('tau_d', True)),
            )

    def _on_apply(self) -> None:
        """Apply the faceplate's edits to the active modal."""
        if not self._active_tag:
            return
        modal = self._modals.get(self._active_tag)
        if modal is None:
            return

        field_map = {
            'sp': (self._sp_input, 'SP'),
            'pv': (self._pv_input, 'PV'),
            'op': (self._op_input, 'OP'),
            'kc': (self._kc_input, 'Kc'),
            'tau_i': (self._taui_input, 'tauI'),
            'tau_d': (self._taud_input, 'tauD'),
        }
        for ui_key, (field, modal_field) in field_map.items():
            if field is None:
                continue
            try:
                apply = getattr(modal, '_apply_numeric_value', None)
                if callable(apply):
                    apply(modal_field, field)
            except Exception:
                pass

        if self._mode_select is not None and hasattr(
            modal, 'commit_mode_change'
        ):
            try:
                modal.commit_mode_change(
                    str(self._mode_select.value or 'auto'),
                    include_tuning=True,
                )
            except Exception:
                pass

        try:
            modal.apply_dialog_values()
        except Exception:
            pass
        self.refresh()

    def _read_field(
        self, modal: Any, ui_key: str, *, fallback: float,
    ) -> float:
        """Read a numeric value from the modal's store, with fallbacks."""
        try:
            modal.refresh_modal_values(
                force_op_refresh=False, force_sp_refresh=False,
            )
        except Exception:
            pass
        store = getattr(modal, 'store', None)
        if store is not None and hasattr(store, 'get'):
            engine_key = ui_key
            param_keys = getattr(modal, 'param_keys', None) or {}
            if isinstance(param_keys, dict) and ui_key in param_keys:
                engine_key = param_keys[ui_key]
            try:
                return float(store.get(engine_key, fallback))
            except Exception:
                return fallback
        if ui_key == 'pv':
            pv_key = getattr(modal, 'pv_key', None)
            if pv_key and store is not None and hasattr(store, 'get'):
                try:
                    return float(store.get(pv_key, fallback))
                except Exception:
                    return fallback
            return float(getattr(modal, 'pv_default', fallback))
        return fallback

    @staticmethod
    def _to_percent(value: float, lo: float, hi: float) -> float:
        """Map a value in [lo, hi] to a [0, 100] bargraph fill height."""
        try:
            v = float(value)
        except (TypeError, ValueError):
            return 0.0
        if hi <= lo:
            return 0.0
        pct = (v - lo) / (hi - lo) * 100.0
        if pct < 0.0:
            return 0.0
        if pct > 100.0:
            return 100.0
        return pct

    @staticmethod
    def _set_bar(
        fill_element: Optional[ui.element], pct: float,
    ) -> None:
        """Drive a bargraph fill's height in % via inline style."""
        if fill_element is None:
            return
        try:
            fill_element.style(f'height: {pct:.1f}%;')
        except Exception:
            pass

    @staticmethod
    def _set_marker(
        marker_element: Optional[ui.element], pct: float,
    ) -> None:
        """Position the SP marker on the PV bargraph."""
        if marker_element is None:
            return
        try:
            marker_element.style(f'bottom: {pct:.1f}%;')
        except Exception:
            pass

    @staticmethod
    def _fmt(value: float, decimals: int) -> str:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return '—'
        return f'{round(v, decimals):.{decimals}f}'


__all__ = [
    'FaceplateDialog',
    'FaceplateDialogConfig',
    'FaceplateSpec',
    'CARD_CLASS',
    'HEADER_CLASS',
]
