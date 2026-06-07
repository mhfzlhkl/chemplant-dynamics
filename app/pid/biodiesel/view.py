# app/pid/biodiesel/view.py

"""Biodiesel P&ID view."""

from __future__ import annotations

from nicegui import ui

from app.biodiesel_drawing import build_biodiesel_drawing
from app.hub.children.modal_child import HubStoreAdapter
from app.hub.children.modals.base import ControllerModal
from app.hub.children.modals.readonly import ReadOnlyControllerModal
from app.hub.children.modals.biodiesel import (
    Fi100ControllerModal,
    Fi101ControllerModal,
    Lic100ControllerModal,
    Pi100ControllerModal,
    Ti100ControllerModal,
    Ti101ControllerModal,
    Ti102ControllerModal,
    Ti103ControllerModal,
    Ti104ControllerModal,
    Tic100ControllerModal,
    Fic100ControllerModal,
    Fic101ControllerModal,
    Fic102ControllerModal,
    ValvePositionModal,
    Lv100ValvePositionModal,
    Tv100ValvePositionModal,
    Fv100ValvePositionModal,
    Fv101ValvePositionModal,
    Fv102ValvePositionModal,
)
from app.hub.signal_hub import SignalHub


def render_biodiesel_pid_svg(hub: SignalHub):
    store = HubStoreAdapter(hub)
    html_element = ui.html(
        build_biodiesel_drawing(), sanitize=False,
    ).classes('biodiesel-pid-svg')

    tunable_modals: dict[str, ControllerModal] = {
        'lic-100': Lic100ControllerModal(store, html_element),
        'tic-100': Tic100ControllerModal(store, html_element),
        'fic-100': Fic100ControllerModal(store, html_element),
        'fic-101': Fic101ControllerModal(store, html_element),
        'fic-102': Fic102ControllerModal(store, html_element),
    }
    ti_modals: dict[str, ReadOnlyControllerModal] = {
        'ti-100': Ti100ControllerModal(store, html_element),
        'ti-101': Ti101ControllerModal(store, html_element),
        'ti-102': Ti102ControllerModal(store, html_element),
        'ti-103': Ti103ControllerModal(store, html_element),
        'ti-104': Ti104ControllerModal(store, html_element),
    }
    fi_modals: dict[str, ReadOnlyControllerModal] = {
        'fi-100': Fi100ControllerModal(store, html_element),
        'fi-101': Fi101ControllerModal(store, html_element),
        'pi-100': Pi100ControllerModal(store, html_element),
    }
    vp_modals: dict[str, ValvePositionModal] = {
        'lv-100': Lv100ValvePositionModal(store, html_element),
        'tv-100': Tv100ValvePositionModal(store, html_element),
        'fv-100': Fv100ValvePositionModal(store, html_element),
        'fv-101': Fv101ValvePositionModal(store, html_element),
        'fv-102': Fv102ValvePositionModal(store, html_element),
    }
    all_modals: dict[str, object] = {}
    all_modals.update(tunable_modals)
    all_modals.update(ti_modals)
    all_modals.update(fi_modals)
    all_modals.update(vp_modals)
    setattr(html_element, 'controller_modals', all_modals)
    return html_element


__all__ = ['render_biodiesel_pid_svg']
