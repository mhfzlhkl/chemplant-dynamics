# app/hub/children/modals/biodiesel.py

"""Biodiesel-specific controller modal subclasses.

Each class wires its tag's ``param_keys`` and ``param_defaults``
into the generic :class:`ControllerModal` / :class:`ReadOnlyControllerModal`
shells. Ported verbatim from the legacy
``app/pid/biodiesel/controller_modal.py`` during the v1 purge —
same per-tag constants, same titles, same defaults (matching
``cases/biodiesel/config.py`` initial conditions).

The biodiesel case has:

- 5 tunable control loops: LIC-100 (level), TIC-100 (temperature),
  FIC-100 (oil feed), FIC-101 (methanol feed), FIC-102 (NaOH feed).
- 5 read-only temperature indicators: TI-100..104.
- 3 read-only flow / pressure indicators: FI-100, FI-101, PI-100.
- 5 read-only valve-position indicators: LV-100, TV-100,
  FV-100, FV-101, FV-102.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from nicegui import ui

from app.hub.children.modals.base import ControllerModal
from app.hub.children.modals.readonly import ReadOnlyControllerModal
from app.hub.local_store import LocalStore


__all__ = [
    'ValvePositionModal',
    # Tunable control loops
    'Lic100ControllerModal',
    'Tic100ControllerModal',
    'Fic100ControllerModal',
    'Fic101ControllerModal',
    'Fic102ControllerModal',
    # Read-only indicators
    'Ti100ControllerModal',
    'Ti101ControllerModal',
    'Ti102ControllerModal',
    'Ti103ControllerModal',
    'Ti104ControllerModal',
    'Fi100ControllerModal',
    'Fi101ControllerModal',
    'Pi100ControllerModal',
    # Read-only valve positions
    'Lv100ValvePositionModal',
    'Tv100ValvePositionModal',
    'Fv100ValvePositionModal',
    'Fv101ValvePositionModal',
    'Fv102ValvePositionModal',
]


# ── Valve position modal ──
# Valve-position cards (LV-100, TV-100, FV-100..102) display a
# percentage (0–100 %vp) that the control loop writes into the
# actuator. The shape is the same as a read-only controller modal
# but with a 0..100 % unit range.

class ValvePositionModal(ReadOnlyControllerModal):
    """Read-only valve-position indicator.

    Mirrors :class:`ReadOnlyControllerModal` but formats the live
    value as a percentage (0–100 %vp) — the same scale the rest of
    the biodiesel case uses for valve-position outputs.
    """

    def __init__(
        self,
        store: Any,
        html_element: ui.element,
        controller_tag: str,
        pv_key: str,
        pv_default: float = 50.0,
        description: str = '',
        title: Optional[str] = None,
    ) -> None:
        super().__init__(
            html_element=html_element,
            controller_tag=controller_tag,
            unit='%',
            description=description or 'Valve position indicator.',
            pv_key=pv_key,
            pv_default=pv_default,
            title=title or f'{controller_tag} — Valve Position',
            store=store,
        )


# ── Tunable controllers (5 control loops) ──

class Lic100ControllerModal(ControllerModal):
    """LIC-100 — Reactor level controller (LC-100 → LV-100)."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        param_keys: Dict[str, str] = {
            'status': 'lic_status',
            'sp': 'lic_sp',
            'pv': 'lic_pv',
            'op': 'lic_op',
            'kc': 'lic_kc',
            'tau_i': 'lic_tau_i',
            'tau_d': 'lic_tau_d',
        }
        # Defaults match ``cases.biodiesel.config.CONTROLLER_INPUT``
        # and ``REFERENCE_INPUT`` (LC-100 SP, Kc, tauI, tauD) so the
        # modal shows the same numbers the engine was initialized
        # with.
        param_defaults: Dict[str, float] = {
            'sp': 1.50,
            'pv': 1.50,
            'op': 50.0,
            'kc': 77.80,
            'tau_i': 0.0,
            'tau_d': 0.0,
        }
        super().__init__(
            store, html_element, 'LIC-100', param_keys,
            param_defaults=param_defaults,
            title='LIC-100 — Level Controller',
        )


class Tic100ControllerModal(ControllerModal):
    """TIC-100 — Reactor temperature controller (TC-100 → TV-100)."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        param_keys: Dict[str, str] = {
            'status': 'tic_status',
            'sp': 'tic_sp',
            'pv': 'tic_pv',
            'op': 'tic_op',
            'kc': 'tic_kc',
            'tau_i': 'tic_tau_i',
            'tau_d': 'tic_tau_d',
        }
        param_defaults: Dict[str, float] = {
            'sp': 333.15,
            'pv': 333.15,
            'op': 80.0,
            'kc': 10.34,
            'tau_i': 1070.07,
            'tau_d': 267.52,
        }
        super().__init__(
            store, html_element, 'TIC-100', param_keys,
            param_defaults=param_defaults,
            title='TIC-100 — Temperature Controller',
        )


class Fic100ControllerModal(ControllerModal):
    """FIC-100 — Oil feed flow controller (FC-100 → FV-100)."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        param_keys: Dict[str, str] = {
            'status': 'fic100_status',
            'sp': 'fic100_sp',
            'pv': 'fic100_pv',
            'op': 'fic100_op',
            'kc': 'fic100_kc',
            'tau_i': 'fic100_tau_i',
            'tau_d': 'fic100_tau_d',
        }
        param_defaults: Dict[str, float] = {
            'sp': 3.29675e-04,
            'pv': 3.29675e-04,
            'op': 50.0,
            'kc': 0.33,
            'tau_i': 12.0,
            'tau_d': 0.0,
        }
        super().__init__(
            store, html_element, 'FIC-100', param_keys,
            param_defaults=param_defaults,
            title='FIC-100 — Oil Feed Flow',
        )


class Fic101ControllerModal(ControllerModal):
    """FIC-101 — Methanol feed flow controller (FC-101 → FV-101)."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        param_keys: Dict[str, str] = {
            'status': 'fic101_status',
            'sp': 'fic101_sp',
            'pv': 'fic101_pv',
            'op': 'fic101_op',
            'kc': 'fic101_kc',
            'tau_i': 'fic101_tau_i',
            'tau_d': 'fic101_tau_d',
        }
        param_defaults: Dict[str, float] = {
            'sp': 8.33750e-05,
            'pv': 8.33750e-05,
            'op': 50.0,
            'kc': 0.33,
            'tau_i': 12.0,
            'tau_d': 0.0,
        }
        super().__init__(
            store, html_element, 'FIC-101', param_keys,
            param_defaults=param_defaults,
            title='FIC-101 — Methanol Feed Flow',
        )


class Fic102ControllerModal(ControllerModal):
    """FIC-102 — NaOH catalyst feed flow controller (FC-102 → FV-102)."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        param_keys: Dict[str, str] = {
            'status': 'fic102_status',
            'sp': 'fic102_sp',
            'pv': 'fic102_pv',
            'op': 'fic102_op',
            'kc': 'fic102_kc',
            'tau_i': 'fic102_tau_i',
            'tau_d': 'fic102_tau_d',
        }
        param_defaults: Dict[str, float] = {
            'sp': 1.33405e-05,
            'pv': 1.33405e-05,
            'op': 50.0,
            'kc': 0.33,
            'tau_i': 12.0,
            'tau_d': 0.0,
        }
        super().__init__(
            store, html_element, 'FIC-102', param_keys,
            param_defaults=param_defaults,
            title='FIC-102 — NaOH Catalyst Feed',
        )


# ── Read-only temperature indicators (5 sensors) ──

class Ti100ControllerModal(ReadOnlyControllerModal):
    """TI-100 — Reactor-side temperature indicator on the jacket inlet."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        super().__init__(
            html_element=html_element,
            controller_tag='TI-100',
            unit='K',
            description='Reactor-side temperature indicator on the jacket inlet.',
            pv_key='ti100_pv',
            pv_default=90.1,
            title='TI-100 — Jacket Inlet Temperature',
            store=store,
        )


class Ti101ControllerModal(ReadOnlyControllerModal):
    """TI-101 — Methanol feed line temperature indicator."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        super().__init__(
            html_element=html_element,
            controller_tag='TI-101',
            unit='K',
            description='Methanol feed line temperature indicator.',
            pv_key='ti101_pv',
            pv_default=25.0,
            title='TI-101 — Methanol Feed Temperature',
            store=store,
        )


class Ti102ControllerModal(ReadOnlyControllerModal):
    """TI-102 — NaOH feed line temperature indicator."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        super().__init__(
            html_element=html_element,
            controller_tag='TI-102',
            unit='K',
            description='NaOH feed line temperature indicator.',
            pv_key='ti102_pv',
            pv_default=90.1,
            title='TI-102 — NaOH Feed Temperature',
            store=store,
        )


class Ti103ControllerModal(ReadOnlyControllerModal):
    """TI-103 — Coolant pump discharge temperature indicator."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        super().__init__(
            html_element=html_element,
            controller_tag='TI-103',
            unit='K',
            description='Coolant pump discharge temperature indicator.',
            pv_key='ti103_pv',
            pv_default=90.1,
            title='TI-103 — Coolant Pump Discharge',
            store=store,
        )


class Ti104ControllerModal(ReadOnlyControllerModal):
    """TI-104 — Jacket outlet temperature indicator."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        super().__init__(
            html_element=html_element,
            controller_tag='TI-104',
            unit='K',
            description='Jacket outlet temperature indicator.',
            pv_key='ti104_pv',
            pv_default=90.1,
            title='TI-104 — Jacket Outlet Temperature',
            store=store,
        )


# ── Read-only flow & pressure indicators (3 sensors) ──

class Fi100ControllerModal(ReadOnlyControllerModal):
    """FI-100 — Coolant flow indicator at the pump suction."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        super().__init__(
            html_element=html_element,
            controller_tag='FI-100',
            unit='m³/hr',
            description='Coolant flow indicator at the pump suction.',
            pv_key='fi100_pv',
            pv_default=90.1,
            title='FI-100 — Coolant Flow',
            store=store,
        )


class Fi101ControllerModal(ReadOnlyControllerModal):
    """FI-101 — Product flow indicator at the pump discharge."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        super().__init__(
            html_element=html_element,
            controller_tag='FI-101',
            unit='m³/hr',
            description='Product (FAME) flow indicator at the pump discharge.',
            pv_key='fi101_pv',
            pv_default=90.1,
            title='FI-101 — Product Flow',
            store=store,
        )


class Pi100ControllerModal(ReadOnlyControllerModal):
    """PI-100 — Vent-line pressure indicator."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        super().__init__(
            html_element=html_element,
            controller_tag='PI-100',
            unit='bar',
            description='Vent-line pressure indicator on the reactor head.',
            pv_key='pi100_pv',
            pv_default=90.1,
            title='PI-100 — Vent Pressure',
            store=store,
        )


# ── Read-only valve positions (5 valves) ──

class Lv100ValvePositionModal(ValvePositionModal):
    """LV-100 — Level-control valve (LC-100 actuator)."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        super().__init__(
            store=store,
            html_element=html_element,
            controller_tag='LV-100',
            pv_key='lic_vp',
            pv_default=50.0,
            description='Level-control valve on the FAME product line.',
            title='LV-100 — Level Valve Position',
        )


class Tv100ValvePositionModal(ValvePositionModal):
    """TV-100 — Temperature-control valve (TC-100 actuator)."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        super().__init__(
            store=store,
            html_element=html_element,
            controller_tag='TV-100',
            pv_key='tic_vp',
            pv_default=50.0,
            description='Temperature-control valve on the coolant jacket inlet.',
            title='TV-100 — Coolant Valve Position',
        )


class Fv100ValvePositionModal(ValvePositionModal):
    """FV-100 — Oil feed valve (FC-100 actuator)."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        super().__init__(
            store=store,
            html_element=html_element,
            controller_tag='FV-100',
            pv_key='fic100_vp',
            pv_default=50.0,
            description='Oil feed valve on the FC-100 feed line.',
            title='FV-100 — Oil Feed Valve Position',
        )


class Fv101ValvePositionModal(ValvePositionModal):
    """FV-101 — Methanol feed valve (FC-101 actuator)."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        super().__init__(
            store=store,
            html_element=html_element,
            controller_tag='FV-101',
            pv_key='fic101_vp',
            pv_default=50.0,
            description='Methanol feed valve on the FC-101 feed line.',
            title='FV-101 — Methanol Feed Valve Position',
        )


class Fv102ValvePositionModal(ValvePositionModal):
    """FV-102 — NaOH feed valve (FC-102 actuator)."""

    def __init__(self, store: LocalStore, html_element: ui.element) -> None:
        super().__init__(
            store=store,
            html_element=html_element,
            controller_tag='FV-102',
            pv_key='fic102_vp',
            pv_default=50.0,
            description='NaOH catalyst feed valve on the FC-102 feed line.',
            title='FV-102 — NaOH Feed Valve Position',
        )
