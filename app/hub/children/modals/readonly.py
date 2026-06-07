# app/hub/children/modals/readonly.py

"""Read-only :class:`ReadOnlyControllerModal` (indicator dialog).

Rewritten from the legacy ``app/pid/sthr/controller_modal.py``
during the v1 purge. Same visual shell as :class:`ControllerModal`
but with only a read-only PV display and an optional description —
no mode selector, no parameter inputs, no Apply button.

Used for indicator-only controllers (FI-100, LI-100, FI-102,
VP-100, TI-100, TI-101..104, PI-100, LV-100, TV-100, FV-100..102).
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from app.hub.children.modals.placement import _SmartPlacementMixin


__all__ = ['ReadOnlyControllerModal']


class ReadOnlyControllerModal(_SmartPlacementMixin):
    """Read-only indicator modal.

    Mirrors the :class:`ControllerModal` UI shell (close button,
    header, footer with Face plate button, SVG hover / click
    affordance) but contains only a read-only PV display row and
    an optional role description. No mode, no SP, no tuning.
    """

    def __init__(
        self,
        html_element: ui.element,
        controller_tag: str,
        *,
        unit: str = '',
        description: str = '',
        pv_key: str | None = None,
        pv_default: float = 0.0,
        title: str | None = None,
        store: Any = None,
    ) -> None:
        self.html_element = html_element
        self.controller_tag = str(controller_tag).strip().upper()
        self.controller_svg_id = self.controller_tag.lower()
        self.unit = unit
        self.description = description
        self.pv_key = pv_key or f'{self.controller_svg_id.replace("-", "_")}_pv'
        self.pv_default = float(pv_default)
        self.title = title or f'{self.controller_tag} — {description or "Indicator"}'
        # Optional engine-backed store. When provided the hub's
        # ``ModalChild`` per-tick refresh pulls the live PV from the
        # store and re-renders the dialog label — otherwise the
        # dialog stays at ``pv_default`` forever.
        self.store = store

        self.dialog_is_open = False

        # Optional reference to the right-drawer faceplate. Wired
        # by the host page after construction.
        self._faceplate: Any = None

        # Unique per-modal CSS class — same scheme as
        # :class:`ControllerModal`. Keeps the smart-placement JS
        # selector targeted at this modal even when several
        # read-only modals share the page.
        self._dialog_uid = f'tic-param-uid-{id(self):x}'

        # Build dialog
        with ui.dialog().props('persistent') as self.dialog, \
                ui.card().classes(f'tic-param-dialog-card {self._dialog_uid}') as self.dialog_card:

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
                    ui.button(
                        icon='close', color=None,
                        on_click=self.dialog.close,
                    ).props('flat round dense size=sm').classes(
                        'tic-param-close-btn',
                    )

            with ui.column().classes('tic-param-dialog-content'):
                self._build_readonly_section()

            with ui.row().classes('tic-param-footer w-full'):
                ui.button(
                    'Face plate', on_click=self.open_faceplate
                ).props('flat dense').classes('tic-param-faceplate-btn')
                # No Apply button — read-only

        # Bind events
        self.dialog.on('hide', self.hide_dialog)
        self._install_svg_hooks()

    # -------------------------------
    # UI builders
    # -------------------------------

    def _build_readonly_section(self) -> None:
        with ui.card().tight().classes('tic-param-section'):
            ui.label('Live Reading').classes('tic-param-section-title')
            with ui.element('div').classes('tic-param-inputs'):
                with ui.element('div').classes('tic-param-row'):
                    ui.label('PV').classes('tic-param-variable')
                    self.pv_label = (
                        ui.label('—')
                        .classes('tic-param-value tic-param-readonly-value-text')
                    )
                    ui.label(self.unit).classes('tic-param-unit')

        if self.description:
            with ui.card().tight().classes('tic-param-section'):
                ui.label('Description').classes('tic-param-section-title')
                ui.label(self.description).classes(
                    'tic-param-readonly-description'
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
                group.setAttribute('title', '{self.controller_tag}: click to view indicator');

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

    # -------------------------------
    # Event handlers
    # -------------------------------

    def hide_dialog(self) -> None:
        self.dialog_is_open = False
        self._set_active(False)

    def set_faceplate(self, faceplate: Any) -> None:
        """Attach the right-drawer faceplate to this read-only modal."""
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
        left: float | None = None,
        top: float | None = None,
        right: float | None = None,
        bottom: float | None = None,
    ) -> None:
        del left, top, right, bottom  # explicitly unused

        # Refresh + mark active BEFORE opening so the operator
        # sees the freshest live value and the SVG hover glow
        # flips to "active" on the first paint — same ordering
        # as :meth:`ControllerModal.open`.
        self.refresh_value()
        self.dialog_is_open = True
        self._set_active(True)
        self.dialog.open()
        self._apply_manual_position_js()

    def refresh_value(self, value: float | None = None) -> None:
        """Update the live value shown in the dialog."""
        if value is None:
            value = self.pv_default
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = self.pv_default

        if isinstance(value, float):
            display_val = f'{value:.2f}' if 'lb' in self.unit else f'{value:.1f}'
        else:
            display_val = str(value)

        self.pv_label.set_text(f'{display_val} {self.unit}'.strip())

    def refresh_modal_values(
        self, force_op_refresh: bool = False, force_sp_refresh: bool = False,
    ) -> None:
        """Hub-side hook — mirror the snapshot into the open dialog.

        :class:`ModalChild` calls this every tick on every modal
        that reports ``dialog_is_open=True``. Read-only modals have
        no SP/PV/OP inputs to mirror, so the only thing that needs
        to update is the live PV label.

        The value is read from ``self.store`` when a store is
        available (engine-backed path); otherwise we fall back to
        ``pv_default`` so pure-UI mode still renders sensibly.
        """
        if not getattr(self, 'dialog_is_open', False):
            return

        if getattr(self, 'store', None) is not None:
            try:
                live = self.store.get(self.pv_key, self.pv_default)
            except Exception:
                live = self.pv_default
        else:
            live = self.pv_default

        self.refresh_value(value=live)

    def handle_svg_click(self, e) -> None:
        """Click handler for the shared click emitter on the html element."""
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

        if target_id != self.controller_svg_id:
            return

        self.open(left=left, top=top, right=right, bottom=bottom)
