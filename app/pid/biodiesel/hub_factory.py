# app/pid/biodiesel/hub_factory.py

"""Biodiesel :class:`SignalHub` factory.

Owns the per-browser bridge registry for biodiesel. Same pattern as
:mod:`app.pid.sthr.hub_factory` — one bridge per browser session,
reused across page reloads; a single shutdown hook installed at
module import.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from nicegui import app

from app.hub.signal_hub import SignalHub
from app.pid.biodiesel.registry import BIODIESEL_REGISTRY


logger = logging.getLogger(__name__)


# ── Engine connection (lazy import) ──
_ENGINE_AVAILABLE = False
_GenericBridge: Any = None
_get_case_config: Any = None

try:
    from gateway.bridge import Bridge as _GenericBridge
    from gateway.config_registry import get_case_config as _get_case_config
    _ENGINE_AVAILABLE = True
except Exception as exc:  # pragma: no cover - environment dependent
    logger.warning(
        'Biodiesel engine gateway not importable — page will not start: %s',
        exc,
    )


# Per-browser bridge registry. Independent of the STHR registry —
# each case has its own dict and its own shutdown hook so cross-case
# isolation is preserved.
_BIODIESEL_BRIDGE_REGISTRY: Dict[str, Any] = {}


def _shutdown_bridges() -> None:
    """Stop every biodiesel bridge on application shutdown."""
    for bridge in _BIODIESEL_BRIDGE_REGISTRY.values():
        try:
            bridge.stop()
        except Exception:
            logger.exception('Failed to stop biodiesel bridge on shutdown')


if _ENGINE_AVAILABLE:
    app.on_shutdown(_shutdown_bridges)


def _get_bridge(profile_key: str) -> Any:
    """Return an existing biodiesel bridge for the profile, or create one."""
    bridge = _BIODIESEL_BRIDGE_REGISTRY.get(profile_key)
    if bridge is None:
        bridge = _GenericBridge(case_name='biodiesel')
        _BIODIESEL_BRIDGE_REGISTRY[profile_key] = bridge
    return bridge


def build_biodiesel_hub(
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
        case_cfg = _get_case_config('biodiesel')
        case_runtime = getattr(case_cfg, 'CASE_RUNTIME', None)
        case_default_mode = str(
            getattr(case_runtime, 'default_mode', 'automatic'),
        )
        case_default_mode_display = (
            case_default_mode
            if any(ch.isupper() for ch in case_default_mode)
            else case_default_mode.capitalize()
        )

        browser_id = str(app.storage.browser.get('id', 'default-browser'))
        profile_key = (
            f'{_GenericBridge.profile_storage_prefix}:biodiesel:{browser_id}'
        )
        profile = app.storage.user.setdefault(profile_key, {})

        bridge = _get_bridge(profile_key)
        bridge.bind_profile(browser_id, profile)

        if not str(bridge.state.controller_mode or '').strip():
            bridge.state.controller_mode = case_default_mode_display

        bridge.apply_runtime_configuration(restart_if_needed=False)

        return SignalHub(
            bridge, BIODIESEL_REGISTRY,
            initial=initial or {}, tick_s=0.05,
        )
    except Exception:
        logger.exception('build_biodiesel_hub failed')
        return None


__all__ = ['build_biodiesel_hub', '_ENGINE_AVAILABLE']
