# app/ui/bridge_store.py

"""Server-side builder + dispatcher for the client-side live-state
cache.

What this module owns
---------------------

Every NiceGUI engine tick, the engine produces a batch of
``BridgeRecord`` objects. ``app.hub.signal_hub.SignalHub._tick``
folds the batch into a single ``snapshot`` mapping and a
``delta_keys`` set, then fans those out to subscribers
(SvgChild, FaceplateChild, ModalChild, …). The traditional
fan-out also makes one ``ui.run_javascript`` call *per child*
inside each subscriber, so the wire carries N+M round trips
per tick (N = number of changed values, M = number of children).

This module adds a parallel path: a single
``ui.run_javascript`` call per tick that pushes the *entire*
``delta_keys`` set + ``snapshot`` to a JS-side store
(``window.__chemPlantState``, defined in
``app/static/js/chemplant_state.js``). Subscribers that opt in
read from the JS store instead of round-tripping per key.

Net effect on the wire:

* Before: 1 (fan-out) + N (per-child JS pushes) per tick.
* After:  1 (fan-out) + 1 (batched JS push) per tick.

The batched push is format-stable (``json.dumps``) and idempotent
(``updateBatch`` in the JS is a no-op on identical keys).

Why a parallel path, not a replacement?
----------------------------------------

Two reasons:

1. **Roll-out safety.** Keeping the original per-child path
   means a regression in the new path can be reverted by
   toggling one flag — no race with the rest of the app.

2. **Read API.** Some children (Faceplate, Modal) need a
   per-element binding style that is more ergonomic with the
   existing per-element ``run_javascript``. They keep using
   the old path; the new path is opt-in per child.

Each child decides whether to use the JS store by checking
``window.__chemPlantState`` (the JS module is loaded once at
page mount). If absent (e.g. test environment) the child falls
back to the old path automatically.

Module surface
--------------

* :func:`payload` — build the JSON payload the client expects.
* :func:`dispatch` — push the payload to the client (one
  ``ui.run_javascript`` call). Best-effort; never raises.
* :func:`bind_text_elements` — register the SVG child so its
  text-element updates happen client-side.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from nicegui import ui


logger = logging.getLogger(__name__)


# Element-level flag so a second install is a no-op. The actual
# "is the JS store present on this client?" probe happens in
# the client itself — the server just declares the script once
# per page.
_INSTALL_FLAG = '__chemplant_state_installed'


# Path the JS file is served at. Matches the static mount in
# ``app/main.py`` (``app.add_static_files('/static', ...)``).
JS_PATH = '/static/js/chemplant_state.js'


def install_once() -> None:
    """Emit the ``<script>`` tag that loads ``chemplant_state.js``.

    Idempotent. Called once at the top of every page that uses
    the live-state cache. Safe to call from any context that has
    a NiceGUI ``ui`` (page builder, page handler, etc.).
    """
    try:
        if getattr(install_once, _INSTALL_FLAG, False):
            return
        ui.add_head_html(
            f'<script src="{JS_PATH}" defer></script>',
        )
        setattr(install_once, _INSTALL_FLAG, True)
    except Exception:
        logger.debug('bridge_store.install_once failed', exc_info=True)


def payload(
    *,
    delta_keys: Any,
    snapshot: Mapping[str, float],
    registry: Any,
    meta: Any,
    tick: int,
) -> dict[str, Any]:
    """Build the JSON payload the client ``updateBatch`` expects.

    Parameters
    ----------
    delta_keys:
        Iterable of modal keys that changed this tick. Only
        formatted values for these keys are pushed (cuts the
        payload size when the engine is idle).
    snapshot:
        Full snapshot mapping ``modal_key -> float``. We send the
        raw float for the changed keys so the client can do
        its own math (e.g. percent computations) without a
        second round-trip.
    registry:
        :class:`app.hub.controller_registry.ControllerRegistry`.
        Used to format each changed value (decimals, units).
        Pass ``None`` if the registry is unavailable — the
        payload then uses a generic ``"%.4f"`` format.
    meta:
        :class:`app.hub.signal_hub.TickMeta` — ``sim_time``,
        ``status``, ``mode``, ``reset_counter``.
    tick:
        Monotonic tick counter. The client uses it to ignore
        out-of-order batches under on_air jitter.
    """
    values: dict[str, str] = {}
    raw: dict[str, float] = {}
    for key in delta_keys:
        value = snapshot.get(key)
        if value is None:
            continue
        try:
            raw[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
        if registry is not None:
            try:
                values[str(key)] = registry.format(str(key), value)
            except Exception:
                values[str(key)] = _fallback_format(value)
        else:
            values[str(key)] = _fallback_format(value)
    return {
        'deltaKeys': sorted(values.keys()),
        'values': values,
        'raw': raw,
        'simTime': _safe_float(getattr(meta, 'sim_time', 0.0), 0.0),
        'status': str(getattr(meta, 'status', 'idle') or 'idle'),
        'mode': str(getattr(meta, 'mode', 'Automatic') or 'Automatic'),
        'tick': int(tick or 0),
    }


def dispatch(payload_dict: Mapping[str, Any]) -> None:
    """Push ``payload_dict`` to the client as a single JS call.

    Best-effort: a ``ui.run_javascript`` failure is logged at
    debug and never raised (the live-state cache is an
    optimization, not a source of truth).
    """
    try:
        body = json.dumps(dict(payload_dict), ensure_ascii=False)
    except Exception:
        logger.debug('bridge_store.dispatch: json.dumps failed', exc_info=True)
        return
    try:
        ui.run_javascript(
            f'window.__chemPlantState && '
            f'window.__chemPlantState.updateBatch({body});',
        )
    except Exception:
        logger.debug('bridge_store.dispatch: run_javascript failed', exc_info=True)


def bind_text_elements(
    *,
    bindings: Mapping[str, str],
) -> None:
    """Register a set of ``modal_key -> svg_id`` bindings with the
    client-side store.

    The store's rAF loop will then write the latest formatted
    value into ``document.getElementById(svg_id + '-value')``
    whenever the store has a new batch.

    ``bindings`` is a dict from modal_key to the SVG element id
    whose ``-value`` child should be updated. The
    ``SvgChild._render`` path is the canonical caller.
    """
    if not bindings:
        return
    try:
        body = json.dumps(
            [
                {'modalKey': str(k), 'elementId': f'{v}-value'}
                for k, v in bindings.items()
            ],
            ensure_ascii=False,
        )
    except Exception:
        return
    try:
        ui.run_javascript(
            '(function(){'
            '  var s=window.__chemPlantState;'
            '  if(!s)return;'
            f'  var arr={body};'
            '  for(var i=0;i<arr.length;i++){'
            '    s.bindTextElement(arr[i].modalKey, arr[i].elementId);'
            '  }'
            '})();'
        )
    except Exception:
        logger.debug(
            'bridge_store.bind_text_elements failed', exc_info=True,
        )


# ── helpers ──────────────────────────────────────────────────────


def _safe_float(value: Any, fallback: float) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return fallback
    if f != f:  # NaN
        return fallback
    return f


def _fallback_format(value: Any) -> str:
    try:
        return f'{float(value):.4f}'
    except (TypeError, ValueError):
        return ''


__all__ = [
    'install_once',
    'payload',
    'dispatch',
    'bind_text_elements',
    'JS_PATH',
]
