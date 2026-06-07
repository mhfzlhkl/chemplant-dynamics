/* chemplant_state.js
 *
 * Client-side live state cache for ChemPlant Dynamics.
 *
 * The server (``app.ui.bridge_store``) calls
 * ``window.__chemPlantState.updateBatch(payload)`` once per engine
 * tick (20 Hz). The payload contains:
 *
 *   {
 *     "deltaKeys": ["tic100_pv", "fi100_pv", ...],
 *     "values":    {"tic100_pv": "150.0", "fi100_pv": "12.3", ...},
 *     "raw":       {"tic100_pv": 150.0123, "fi100_pv": 12.34, ...},
 *     "simTime":   4.5,
 *     "status":    "running",
 *     "mode":      "Auto",
 *     "tick":      87
 *   }
 *
 * We expose:
 *
 *   window.__chemPlantState.values[key]   — formatted string ("" if absent)
 *   window.__chemPlantState.raw[key]      — float (NaN if absent)
 *   window.__chemPlantState.simTime       — float
 *   window.__chemPlantState.status        — string
 *   window.__chemPlantState.mode          — string
 *   window.__chemPlantState.tick          — integer (monotonic counter)
 *
 * The store is also wired to drive a small set of DOM updates
 * client-side via ``requestAnimationFrame``. The server
 * ``SvgChild`` registers its target text elements here once via
 * ``bindTextElement(modalKey, elementId)``; the rAF loop then
 * writes the latest formatted value into the element if it has
 * changed since the last write.
 *
 * Why client-side DOM updates?
 *
 *   1. **Zero round-trip for repaint.** The NiceGUI server pushes
 *      a single batched JS call per tick; the browser does the
 *      N text writes locally.
 *   2. **Deterministic ordering under jitter.** With per-element
 *      ``ui.run_javascript`` calls under on_air's variable RTT,
 *      late batches can clobber newer ones. A single batched
 *      update + local rAF is order-stable.
 *   3. **Lower CPU on the server.** The format() work still
 *      happens on the server (where the per-tag decimals live),
 *      but the textContent writes are local.
 *
 * The module is plain ES5 + 1 rAF — no framework, no build step,
 * ~3 KB minified. Loaded via a single ``<script src>`` tag in
 * ``app/main.py`` via ``ui.add_head_html``.
 */

(function () {
    'use strict';

    if (window.__chemPlantState && window.__chemPlantState.__installed) {
        // Idempotent — re-running this script (e.g. on hot-reload)
        // is a no-op.
        return;
    }

    var store = {
        // Public state
        values: Object.create(null),
        raw:    Object.create(null),
        simTime: 0.0,
        status:  'idle',
        mode:    'Automatic',
        tick:    0,
        lastUpdate: 0,

        // Internal: text-element bindings (modalKey → elementId).
        _bindings: Object.create(null),
        // Internal: monorepo of "last formatted value written" so the
        // rAF loop can short-circuit when nothing changed.
        _lastWritten: Object.create(null),
        // Internal: pending DOM writes (batched into the rAF).
        _dirty: false,

        __installed: true,
    };

    function isPlainObject(value) {
        return value !== null
            && typeof value === 'object'
            && !Array.isArray(value);
    }

    function safeNumber(value, fallback) {
        var n = Number(value);
        return isFinite(n) ? n : fallback;
    }

    function applyBatch(payload) {
        if (!isPlainObject(payload)) {
            return;
        }
        // 1. Values + raw.
        var incomingValues = isPlainObject(payload.values) ? payload.values : null;
        var incomingRaw    = isPlainObject(payload.raw)    ? payload.raw    : null;

        if (incomingValues) {
            for (var k in incomingValues) {
                if (Object.prototype.hasOwnProperty.call(incomingValues, k)) {
                    store.values[k] = String(incomingValues[k]);
                }
            }
        }
        if (incomingRaw) {
            for (var k2 in incomingRaw) {
                if (Object.prototype.hasOwnProperty.call(incomingRaw, k2)) {
                    store.raw[k2] = safeNumber(incomingRaw[k2], NaN);
                }
            }
        }
        // 2. Sim-time / status / mode / tick.
        if (typeof payload.simTime === 'number') {
            store.simTime = payload.simTime;
        }
        if (typeof payload.status === 'string') {
            store.status = payload.status;
        }
        if (typeof payload.mode === 'string') {
            store.mode = payload.mode;
        }
        if (typeof payload.tick === 'number') {
            store.tick = payload.tick;
        }
        store.lastUpdate = Date.now();
        store._dirty = true;
    }

    function bindTextElement(modalKey, elementId) {
        if (!modalKey || !elementId) {
            return;
        }
        store._bindings[modalKey] = String(elementId);
    }

    function unbindTextElement(modalKey) {
        if (modalKey && store._bindings[modalKey]) {
            delete store._bindings[modalKey];
            delete store._lastWritten[modalKey];
        }
    }

    function flushDom() {
        if (!store._dirty) {
            return;
        }
        for (var modalKey in store._bindings) {
            if (!Object.prototype.hasOwnProperty.call(store._bindings, modalKey)) {
                continue;
            }
            var elementId = store._bindings[modalKey];
            var el = document.getElementById(elementId);
            if (!el) {
                continue;
            }
            var next = Object.prototype.hasOwnProperty.call(store.values, modalKey)
                ? store.values[modalKey]
                : '';
            if (store._lastWritten[modalKey] === next) {
                continue;
            }
            el.textContent = next;
            store._lastWritten[modalKey] = next;
        }
        store._dirty = false;
    }

    // requestAnimationFrame loop — writes bound DOM elements when the
    // store has a new batch. 60 Hz max; idle if no batch has arrived.
    function loop() {
        flushDom();
        window.__chemPlantRafId = window.requestAnimationFrame(loop);
    }
    window.__chemPlantRafId = window.requestAnimationFrame(loop);

    // Expose.
    window.__chemPlantState = {
        // Public reads
        get values()    { return store.values; },
        get raw()       { return store.raw; },
        get simTime()   { return store.simTime; },
        get status()    { return store.status; },
        get mode()      { return store.mode; },
        get tick()      { return store.tick; },
        get lastUpdate(){ return store.lastUpdate; },
        // Public writes
        updateBatch:    applyBatch,
        bindTextElement: bindTextElement,
        unbindTextElement: unbindTextElement,
        // Diagnostics — handy for the browser console.
        __bindingCount: function () {
            var n = 0;
            for (var k in store._bindings) {
                if (Object.prototype.hasOwnProperty.call(store._bindings, k)) n++;
            }
            return n;
        },
        __installed: true,
    };
})();
