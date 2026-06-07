# app/hub/children/modals/sthr.py

"""STHR-specific controller modal subclasses.

Each class wires its tag's ``param_keys`` (modal key → store key)
and ``param_defaults`` (initial values matching the engine's
configured initial conditions in ``cases/sthr/config.py``) into
the generic :class:`ControllerModal` / :class:`ReadOnlyControllerModal`
shells defined in :mod:`app.hub.children.modals.base` /
:mod:`app.hub.children.modals.readonly`.

Ported verbatim from the legacy ``app/pid/sthr/controller_modal.py``
during the v1 purge — same per-tag constants, same titles, same
defaults (Kc=6.10 / tauI=2.30 / tauD=0.58 for TIC-100 etc.).
"""

from __future__ import annotations

from nicegui import ui

from app.hub.children.modals.base import ControllerModal
from app.hub.children.modals.readonly import ReadOnlyControllerModal
from app.hub.local_store import LocalStore


__all__ = [
    'Tic100ControllerModal',
    'Fi100ControllerModal',
    'Fi101ControllerModal',
    'Ti100ControllerModal',
    'Li100ControllerModal',
    'Fi102ControllerModal',
    'Vp100ControllerModal',
]


class Tic100ControllerModal(ControllerModal):
    """TIC-100 — Stirred tank heater temperature controller."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        param_keys = {
            'status': 'tic_status',
            'sp': 'sp',
            'pv': 'pv',
            'op': 'op',
            'kc': 'kc',
            'tau_i': 'tau_i',
            'tau_d': 'tau_d',
        }
        # Defaults match ``cases.sthr.config.CONTROLLER_INPUT`` so
        # the modal shows the same numbers the engine was initialized
        # with (Kc=6.10, tauI=2.30, tauD=0.58).
        param_defaults = {
            'sp': 150.0,
            'pv': 150.0,
            'op': 82.3,
            'kc': 6.10,
            'tau_i': 2.30,
            'tau_d': 0.58,
        }
        super().__init__(
            store, html_element, 'TIC-100', param_keys,
            param_defaults=param_defaults,
            title='TIC-100 Controller Parameters',
        )


class Fi100ControllerModal(ReadOnlyControllerModal):
    """FI-100 — Steam flow indicator (read-only)."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        super().__init__(
            html_element, 'FI-100',
            unit='lb/min',
            description='Steam flow indicator on the coil feed line.',
            pv_key='fi100_pv',
            pv_default=42.23,
            title='FI-100 — Steam Flow',
            store=store,
        )


class Fi101ControllerModal(ControllerModal):
    """FI-101 — Feed flow controller / indicator."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        param_keys = {
            'status': 'fi101_status',
            'sp': 'feed_flow',
            'pv': 'fi101_pv',
            'op': 'op',
        }
        param_defaults = {
            'sp': 15.0,
            'pv': 15.0,
            'op': 0.0,
        }
        super().__init__(
            store, html_element, 'FI-101', param_keys,
            param_defaults=param_defaults,
            title='FI-101 — Feed Flow',
        )


class Ti100ControllerModal(ControllerModal):
    """TI-100 — Feed temperature controller / indicator."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        param_keys = {
            'status': 'ti100_status',
            'sp': 'feed_temp',
            'pv': 'ti100_pv',
            'op': 'op',
        }
        param_defaults = {
            'sp': 100.0,
            'pv': 100.0,
            'op': 0.0,
        }
        super().__init__(
            store, html_element, 'TI-100', param_keys,
            param_defaults=param_defaults,
            title='TI-100 — Feed Temp',
        )


class Li100ControllerModal(ReadOnlyControllerModal):
    """LI-100 — Tank level indicator (read-only)."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        super().__init__(
            html_element, 'LI-100',
            unit='ft³',
            description='Tank level indicator on the stirred tank heater.',
            pv_key='li100_pv',
            pv_default=120.0,
            title='LI-100 — Level',
            store=store,
        )


class Fi102ControllerModal(ReadOnlyControllerModal):
    """FI-102 — Product flow indicator (read-only)."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        super().__init__(
            html_element, 'FI-102',
            unit='ft³/min',
            description='Product flow indicator on the pump discharge line.',
            pv_key='fi102_pv',
            pv_default=15.0,
            title='FI-102 — Product Flow',
            store=store,
        )


class Vp100ControllerModal(ReadOnlyControllerModal):
    """VP-100 — Steam valve position indicator (read-only)."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        super().__init__(
            html_element, 'VP-100',
            unit='%',
            description='Control valve position indicator on the steam feed line.',
            pv_key='vp100_pv',
            pv_default=82.3,
            title='VP-100 — Valve Position',
            store=store,
        )
