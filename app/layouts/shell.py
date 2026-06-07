# app/layouts/shell.py

"""Page shells — home and control-panel.

These mirror the engine_root layout exactly. The home shell has a header
(without menu button) and a footer. The control-panel shell has a header
(with menu button + dual logos) and a footer. The control-panel content
region hosts the PID SVG, the PID navbar, and the controller modals.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from app.assets import collect_css
from app.components.drawer import DrawerMenuItem, create_control_panel_left_drawer
from app.components.footer import build_footer
from app.components.header import build_control_panel_header, build_home_header
from app.config import STATIC_DIR
from app.ui.section_loader import SectionLoader


# ============================================================
# INLINED CSS
# ============================================================
# Bundle every CSS file under ``app/static/css/`` at import time so we can
# ship a single ``<style>`` block with the page. This works in BOTH local
# and ``on_air`` modes — the on_air relay does not always forward
# ``/static/css/...`` requests reliably, so the previous ``<link>`` tags
# left the page unstyled over the cloud tunnel. See app/assets.py for
# the bundling rules.
INLINE_CSS = collect_css(STATIC_DIR)


# ============================================================
# PAGE SETUP
# ============================================================

def setup_page_shell(*, body_class: str = '') -> None:
    """Apply per-page UI setup."""

    # Inlined stylesheet — built from every *.css under app/static/css/.
    # Always emitted first so the Google Fonts <link> that follows
    # cannot accidentally override the cascade.
    ui.add_head_html(f'<style>{INLINE_CSS}</style>')
    ui.add_head_html('''
        <link
            rel="stylesheet"
            href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200"
        >
    ''')

    # Install the client-side live-state cache script on every page
    # that uses the control-panel layout. Idempotent — the helper
    # bails out after the first call per process. Loading the
    # script even on pages that don't use it is harmless (it just
    # installs a small JS store object) and keeps the page scripts
    # consistent across routes.
    try:
        from app.ui.bridge_store import install_once
        install_once()
    except Exception:
        pass

    classes = 'app-body'
    if body_class:
        classes = f'{classes} {body_class}'

    ui.query('body').classes(classes)


# ============================================================
# HOME SHELL
# ============================================================

def home_shell(content: Callable[[], None]) -> None:
    setup_page_shell(body_class='home-page')

    build_home_header()

    with ui.column().classes('home-main'):
        with ui.column().classes('home-scroll-region'):
            with ui.column().classes('home-content-layer'):
                content()

    build_footer()


# ============================================================
# CONTROL PANEL SHELL
# ============================================================

def control_panel_shell(
    *,
    sections: tuple[Any, ...],
    default_section: str,
) -> None:
    """Control panel shell that swaps sections in the same content column."""

    setup_page_shell(body_class='control-panel-page')

    drawer_state = {'open': False}

    ui.query('body').classes(
        'control-panel-drawer-closed',
        remove='control-panel-drawer-open',
    )

    section_panels: dict[str, Any] = {}
    initialized_sections: set[str] = set()
    section_builders: dict[str, Callable[[], None]] = {
        section.label: section.builder for section in sections
    }

    # Per-section ``SectionLoader``. Each owns the panel + builder
    # and runs a two-stage mount (skeleton first, real content
    # on the next tick). See ``app.ui.section_loader`` for the
    # rationale — the goal is sub-16 ms drawer-button feedback
    # even when the section is heavy (echart panels, SVG, etc).
    section_loaders: dict[str, SectionLoader] = {}

    drawer_items = tuple(
        DrawerMenuItem(label=section.label) for section in sections
    )

    def ensure_section_content(section_label: str) -> None:
        if section_label in initialized_sections:
            return
        loader = section_loaders.get(section_label)
        if loader is None:
            return
        loader.mount()
        initialized_sections.add(section_label)

    def show_section(section_label: str) -> None:
        # Synchronously flip visibility — this part is fast (one
        # CSS class swap) and gives the user the instant "section
        # changed" feedback they expect. The new section's real
        # content mounts in the background via the SectionLoader.
        for label, panel in section_panels.items():
            panel.set_visibility(label == section_label)
        ensure_section_content(section_label)

    def handle_drawer_item_click(item: DrawerMenuItem) -> None:
        show_section(item.label)

    left_drawer = create_control_panel_left_drawer(
        items=drawer_items,
        active_label=default_section,
        on_item_click=handle_drawer_item_click,
    )

    def toggle_left_drawer() -> None:
        left_drawer.toggle()
        drawer_state['open'] = not drawer_state['open']
        if drawer_state['open']:
            ui.query('body').classes(
                'control-panel-drawer-open',
                remove='control-panel-drawer-closed',
            )
        else:
            ui.query('body').classes(
                'control-panel-drawer-closed',
                remove='control-panel-drawer-open',
            )

    build_control_panel_header(on_menu_click=toggle_left_drawer)

    with ui.column().classes('control-panel-main main-content w-full'):
        with ui.column().classes('control-panel-content-stack w-full'):
            for section in sections:
                section_class = 'control-panel-section w-full'
                if 'Piping and Instrumentation Diagram' in section.label:
                    section_class = (
                        'control-panel-section '
                        'control-panel-section-pid '
                        'w-full'
                    )
                with ui.column().classes(section_class) as panel:
                    pass
                panel.set_visibility(False)
                section_panels[section.label] = panel
                # Build a SectionLoader for this panel. The loader
                # is used by ``ensure_section_content`` on the
                # first show of this section.
                section_loaders[section.label] = SectionLoader(
                    panel=panel,
                    label=section.label,
                    builder=section_builders[section.label],
                )

            # Mount the default section eagerly so the page first
            # paint already has its content + skeleton in the right
            # place. Other sections stay hidden until the user
            # clicks them.
            ensure_section_content(default_section)
            for label, panel in section_panels.items():
                panel.set_visibility(label == default_section)

    build_footer()
