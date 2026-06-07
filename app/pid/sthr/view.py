# app/pid/sthr/view.py

"""STHR P&ID view.

Wraps :func:`app.sthr_drawing.build_sthr_drawing` and wires the
controller modals to a hub-backed store adapter
(:class:`HubStoreAdapter`) so each modal's existing ``store.get`` /
``store.set`` calls route through :meth:`SignalHub.request_write`
on the way down and :meth:`SignalHub.snapshot` on the way back up.
"""

from __future__ import annotations

from nicegui import ui

from app.hub.children.modal_child import HubStoreAdapter
from app.hub.children.modals import (
    ControllerModal,
    Fi100ControllerModal,
    Fi101ControllerModal,
    Fi102ControllerModal,
    Li100ControllerModal,
    ReadOnlyControllerModal,
    Ti100ControllerModal,
    Tic100ControllerModal,
    Vp100ControllerModal,
)
from app.hub.signal_hub import SignalHub
from app.sthr_drawing import build_sthr_drawing


def render_sthr_pid_svg(hub: SignalHub):
    """Render the STHR P&ID and wire the controller modals to ``hub``.

    Returns the ``ui.html`` element; ``html_element.controller_modals``
    is set on it (same protocol the faceplate / modal child expect)
    so :class:`ModalChild` and :class:`FaceplateChild` can pull it out
    of the page directly.
    """
    store = HubStoreAdapter(hub)
    html_element = ui.html(
        build_sthr_drawing(), sanitize=False,
    ).classes('sthr-pid-svg')

    tunable_modals: dict[str, ControllerModal] = {
        'tic-100': Tic100ControllerModal(store, html_element),
        'fi-101':  Fi101ControllerModal(store, html_element),
        'ti-100':  Ti100ControllerModal(store, html_element),
    }
    readonly_modals: dict[str, ReadOnlyControllerModal] = {
        'fi-100':  Fi100ControllerModal(store, html_element),
        'li-100':  Li100ControllerModal(store, html_element),
        'fi-102':  Fi102ControllerModal(store, html_element),
        'vp-100':  Vp100ControllerModal(store, html_element),
    }
    all_modals: dict[str, object] = {}
    all_modals.update(tunable_modals)
    all_modals.update(readonly_modals)
    setattr(html_element, 'controller_modals', all_modals)
    return html_element


__all__ = ['render_sthr_pid_svg']
