# app/components/faceplate.py

"""Faceplate spec + modal inference helpers (legacy right-drawer
entry point retained for backward compatibility).

The right-drawer faceplate was replaced by a floating
:class:`ui.dialog` (see :mod:`app.components.faceplate_dialog`).
This module now hosts the shared :class:`FaceplateSpec` dataclass
and the :func:`infer_faceplate_spec` helper that the new dialog
uses to derive per-tag display metadata from a controller
modal's public API. Legacy code that imported
``FaceplatePanel`` from this module is updated at the call sites
to use :class:`FaceplateDialog`; the name is intentionally not
re-exported so an accidental import fails loudly instead of
silently instantiating the wrong class.

Background
----------

The faceplate is a per-controller extension of the modal that
mirrors the look-and-feel of a DCS HMI:

    ┌──────────────────────────────┐
    │ TAG    Description     [×]   │
    │ mode badge / status          │
    │                              │
    │   PV          SP          OP │
    │  ▓▓▓▓▓▓      ▓▓▓▓▓▓     ▓▓▓▓ │
    │  150.0       150.0      82.3 │
    │   °F          °F          %  │
    │                              │
    │ ── Operational Parameters ── │
    │ Mode [Auto ▾]                 │
    │ SP   [ 150.0 ]   °F           │
    │ PV   [ 150.0 ]   °F           │
    │ OP   [  82.3 ]   %            │
    │                              │
    │ ── Controller Parameters ──  │
    │ Kc   [  6.10 ]  %CO/%TO       │
    │ τI   [  2.30 ]  min           │
    │ τD   [  0.58 ]  min           │
    │                              │
    │ [ Apply ]                     │
    └──────────────────────────────┘

The vertical bargraphs are pure CSS. A ``.faceplate-bar-fill``
element is positioned at the bottom of its track and its
``height`` is updated in % by the live flusher. The fill colours
are DCS standard: PV = process yellow, SP = setpoint cyan, OP =
output magenta/green. The bargraph also draws a horizontal SP
marker so the operator can see at a glance how far PV is from
SP.

The body content (header, bargraphs, operational + tuning
inputs, Apply button) now lives inside a ``ui.dialog`` (see
:mod:`app.components.faceplate_dialog`); only the per-tag
display metadata and the modal-inference helper remain here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple

from app import config as app_config


# ============================================================
# CONTROLLER METADATA
# ============================================================
#
# Per-tag display metadata used by the faceplate. Mirrors
# ``app.config.DISPLAY_MAP`` for units and ``DISPLAY_MAP`` ranges
# / defaults from the modal classes for SP/PV/OP keys.
#
# Adding a new controller means adding a row here AND registering
# the modal in the page's ``render_*_pid_svg`` builder — the
# faceplate discovers which tags to show from the registered
# controller_modals dict on the html element.

@dataclass(frozen=True)
class FaceplateSpec:
    """Static display metadata for a single controller tag."""

    tag: str                  # 'TIC-100'
    svg_id: str               # 'tic-100'
    title: str                # 'Temperature Controller'
    pv_unit: str              # '°F'
    sp_unit: str              # '°F' (may differ from pv_unit for FI-101)
    op_unit: str              # '%' / '%CO'
    pv_min: float
    pv_max: float
    sp_min: float
    sp_max: float
    op_min: float             # typically 0
    op_max: float             # typically 100
    pv_decimals: int
    sp_decimals: int
    op_decimals: int
    has_mode: bool
    has_op: bool
    has_tuning: bool
    # Optional bargraph overrides (e.g. SP bargraph is shown
    # only when the controller has a writable setpoint).
    show_sp_bar: bool = True
    show_op_bar: bool = True


# ============================================================
# SPEC INFERENCE
# ============================================================
#
# Shared by :mod:`app.components.faceplate_dialog` so the new
# dialog and any future host (a non-floating right pane, an
# embedded mini-faceplate, etc.) can derive per-tag metadata
# from a controller modal's public API without duplicating the
# unit / range / decimal-place logic.

# Per-svg-id decimal place map. Mirrors the legacy flusher's
# per-tag map; kept here as a module-level constant so a future
# host can reuse it without re-importing the dialog.
_DECIMALS_MAP = {
    'tic-100': (1, 1, 1),
    'fi-100':  (2, 1, 1),
    'fi-101':  (1, 1, 1),
    'ti-100':  (1, 1, 1),
    'li-100':  (1, 1, 1),
    'fi-102':  (1, 1, 1),
    'vp-100':  (1, 1, 1),
}


def infer_faceplate_spec(modal: Any) -> FaceplateSpec:
    """Build a :class:`FaceplateSpec` from a modal's public API.

    Read-only modals (no SP, no OP) collapse to a single PV
    bargraph. Tunable modals keep all three bargraphs.

    The function is intentionally pure (no I/O, no logging, no
    fallbacks that swallow exceptions silently) so the caller
    gets a consistent spec for a given modal.
    """
    tag = str(getattr(modal, 'controller_tag', '')).strip().upper()
    svg_id = tag.lower()

    # Unit / range resolution
    pv_unit = str(getattr(modal, 'pv_unit', '') or '') \
        or str(getattr(modal, 'unit', '') or '')
    sp_unit = pv_unit
    op_unit = str(getattr(modal, 'mv_unit', '') or '%')

    # Range lookups via the existing CONTROLLER_DRAWER_CONFIG
    cfg = (
        app_config.CONTROLLER_DRAWER_CONFIG.get(svg_id, {})
        if isinstance(app_config.CONTROLLER_DRAWER_CONFIG, dict) else {}
    )
    params = cfg.get('params', []) if isinstance(cfg, dict) else []

    def _range(ui_key: str, fallback: Tuple[float, float]) -> Tuple[float, float]:
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
    # with Kc/τI/τD) keep the full three-bar layout. All other
    # controllers collapse to a single PV bar.
    show_sp_bar = bool(has_tuning)
    show_op_bar = bool(has_tuning)

    pv_d, sp_d, op_d = _DECIMALS_MAP.get(svg_id, (1, 1, 1))

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


# ============================================================
# LEGACY COMPATIBILITY
# ============================================================
#
# The legacy ``FaceplatePanel`` was a right-drawer faceplate.
# It has been replaced by :class:`app.components.faceplate_dialog.FaceplateDialog`
# (a ``ui.dialog`` with drag / resize / minimize). Importing the
# old name raises a clear error so callers that haven't been
# updated get a fast, loud failure with a migration hint
# instead of silently instantiating the wrong class.
#
# If you reach this error, replace::
#
#     from app.components.faceplate import FaceplatePanel
#     panel = FaceplatePanel()
#
# with::
#
#     from app.components.faceplate_dialog import (
#         FaceplateDialog,
#         FaceplateDialogConfig,
#     )
#     dialog = FaceplateDialog(FaceplateDialogConfig(case_slug='sthr'))
#     dialog.build()
#     for tag, modal in modals.items():
#         modal.set_faceplate(dialog)
#         dialog.register_modal(modal)
#
# Public methods on the new dialog match the legacy panel
# (``register_modal``, ``open_for``, ``close``, ``refresh``,
# ``set_drawer`` (no-op)) so the call sites only need to swap
# the class and constructor.

class FaceplatePanel:
    """Removed in favor of :class:`app.components.faceplate_dialog.FaceplateDialog`.

    Kept as a class so the existing ``from app.components.faceplate
    import FaceplatePanel`` import path resolves. Attempting to
    *instantiate* the class raises a clear error with the
    migration hint so call sites that haven't been updated get a
    fast, loud failure instead of silently instantiating the
    wrong class.

    Migration::

        # before
        from app.components.faceplate import FaceplatePanel
        panel = FaceplatePanel()
        panel.set_drawer(drawer_aside)

        # after
        from app.components.faceplate_dialog import (
            FaceplateDialog,
            FaceplateDialogConfig,
        )
        dialog = FaceplateDialog(
            FaceplateDialogConfig(case_slug='sthr'),
        )
        dialog.build()  # construct the dialog DOM once
        for tag, modal in modals.items():
            modal.set_faceplate(dialog)
            dialog.register_modal(modal)

    Public methods on the new dialog (``register_modal``,
    ``open_for``, ``close``, ``refresh``, ``set_drawer`` as a
    no-op) match the legacy panel exactly.
    """

    def __init__(self, *_args, **_kwargs) -> None:
        raise RuntimeError(
            "FaceplatePanel has been removed. The faceplate is "
            "now a ui.dialog — import FaceplateDialog from "
            "app.components.faceplate_dialog instead.\n\n"
            "Migration:\n"
            "    from app.components.faceplate_dialog import (\n"
            "        FaceplateDialog, FaceplateDialogConfig,\n"
            "    )\n"
            "    dialog = FaceplateDialog(\n"
            "        FaceplateDialogConfig(case_slug='sthr'),\n"
            "    )\n"
            "    dialog.build()\n"
            "    # The dialog's register_modal / open_for / close /\n"
            "    # refresh / set_drawer (no-op) API matches the\n"
            "    # legacy FaceplatePanel exactly.\n"
        )


__all__ = [
    'FaceplateSpec',
    'FaceplatePanel',  # legacy shim — raises on instantiation
    'infer_faceplate_spec',
]
