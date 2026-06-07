# app/pid/sthr/hub_factory.py

"""STHR :class:`SignalHub` factory.

Owns the per-browser bridge registry for STHR. A single bridge per
browser session is reused across reloads so that pressing Run on
one tab doesn't desynchronise a sibling tab — they read from the
same engine worker.

The shutdown hook is installed once at module import (idempotent,
because NiceGUI only runs the registered hooks at the process's
shutdown, not per-page).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from nicegui import app

from app import config as app_config
from app.hub.signal_hub import SignalHub
from app.pid.sthr.registry import STHR_REGISTRY


logger = logging.getLogger(__name__)


# ── Engine connection (lazy import) ──
# Imported lazily so the app can start even if the engine package
# is missing (e.g. during pure-UI development). When import fails
# ``build_sthr_hub`` returns ``None`` and the page renders an
# "engine not available" placeholder.
_ENGINE_AVAILABLE = False
_GenericBridge: Any = None
_get_case_config: Any = None

try:
    from gateway.bridge import Bridge as _GenericBridge
    from gateway.config_registry import get_case_config as _get_case_config
    _ENGINE_AVAILABLE = True
except Exception as exc:  # pragma: no cover - environment dependent
    logger.warning(
        'STHR engine gateway not importable — page will not start: %s', exc,
    )


# Per-browser bridge registry. Keyed by ``profile_key`` so each
# browser session keeps its own bridge across page reloads.
_STHR_BRIDGE_REGISTRY: Dict[str, Any] = {}


def _shutdown_bridges() -> None:
    """Stop every STHR bridge on application shutdown."""
    for bridge in _STHR_BRIDGE_REGISTRY.values():
        try:
            bridge.stop()
        except Exception:
            logger.exception('Failed to stop STHR bridge on shutdown')


if _ENGINE_AVAILABLE:
    # Register the shutdown hook exactly once at module import.
    app.on_shutdown(_shutdown_bridges)


def _get_bridge(profile_key: str) -> Any:
    """Return an existing STHR bridge for the profile, or create a new one."""
    bridge = _STHR_BRIDGE_REGISTRY.get(profile_key)
    if bridge is None:
        bridge = _GenericBridge(case_name='sthr')
        _STHR_BRIDGE_REGISTRY[profile_key] = bridge
    return bridge


def _initial_pv_seed() -> Dict[str, float]:
    """Seed the hub snapshot with the same display values the SVG was
    baked with.

    The SVG is rendered by :func:`app.sthr_drawing.build_sthr_drawing`
    using values from ``DISPLAY_MAP`` → ``INITIAL_CONDITIONS`` /
    ``PLANT_PARAMS``. Without this seed, the hub's snapshot is empty
    until the first engine step record arrives, and every controller
    card momentarily renders as ``0`` on first login.
    """
    seed: Dict[str, float] = {}
    display_map = getattr(app_config, 'DISPLAY_MAP', {}) or {}
    initials = getattr(app_config, 'INITIAL_CONDITIONS', {}) or {}
    plant = getattr(app_config, 'PLANT_PARAMS', {}) or {}

    # SVG controller id → modal PV key — mirrors the per-spec
    # ``modal_key`` ↔ ``svg_id`` mapping in
    # ``app/pid/sthr/registry.py``.
    controller_to_pv_key: Dict[str, str] = {
        'tic-100': 'pv',
        'fi-100':  'fi100_pv',
        'fi-101':  'fi101_pv',
        'ti-100':  'ti100_pv',
        'li-100':  'li100_pv',
        'fi-102':  'fi102_pv',
        'vp-100':  'vp100_pv',
    }
    for svg_id, pv_key in controller_to_pv_key.items():
        mapping = display_map.get(svg_id) or {}
        signal = mapping.get('signal')
        if not signal:
            continue
        if signal in initials:
            seed[pv_key] = float(initials[signal])
        elif signal in plant:
            seed[pv_key] = float(plant[signal])
    return seed


def build_sthr_hub(
    *,
    initial: Optional[Dict[str, float]] = None,
) -> Optional[SignalHub]:
    """Build (or reuse) the per-browser bridge and wrap it in a SignalHub.

    Returns ``None`` when the engine gateway is unavailable — the
    page handles that by showing an "engine not connected" placeholder.
    """
    if not _ENGINE_AVAILABLE:
        return None

    try:
        case_cfg = _get_case_config('sthr')
        case_runtime = getattr(case_cfg, 'CASE_RUNTIME', None)
        case_default_mode = str(getattr(case_runtime, 'default_mode', 'automatic'))
        case_default_mode_display = (
            case_default_mode
            if any(ch.isupper() for ch in case_default_mode)
            else case_default_mode.capitalize()
        )

        browser_id = str(app.storage.browser.get('id', 'default-browser'))
        profile_key = f'{_GenericBridge.profile_storage_prefix}:sthr:{browser_id}'
        profile = app.storage.user.setdefault(profile_key, {})

        bridge = _get_bridge(profile_key)
        bridge.bind_profile(browser_id, profile)

        if not str(bridge.state.controller_mode or '').strip():
            bridge.state.controller_mode = case_default_mode_display

        # Apply the initial runtime config so the first Run click works
        # immediately.
        bridge.apply_runtime_configuration(restart_if_needed=False)

        seed = _initial_pv_seed()
        if initial:
            seed.update(initial)

        return SignalHub(bridge, STHR_REGISTRY, initial=seed, tick_s=0.05)
    except Exception:
        logger.exception('build_sthr_hub failed')
        return None


__all__ = ['build_sthr_hub', '_ENGINE_AVAILABLE']
