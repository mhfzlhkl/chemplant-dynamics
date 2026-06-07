# app/config.py

"""Static configuration for the app UI.

Pure UI configuration — no engine, no services, no gateway.
All values are taken verbatim from V1.1's config.py so that the
SVG content and the controller modals keep the same look & feel.
"""

from pathlib import Path

# ── Paths ──
PUBLIC_DIR = Path(__file__).parent / 'static' / 'public'
STATIC_DIR = Path(__file__).parent / 'static'

# ── Debug ──
DEBUG_GRID = False

# ── Menu ──
MENU_ITEMS = [
    'Stirred Tank Heater',
]

# ── Plant Parameters ──
PLANT_PARAMS = {
    'rho': 68.0,
    'Cp': 0.80,
    'V': 120.0,
    'A': 241.5,
    'Cm': 265.68,
    'U': 2.1,
    'lamb': 966.0,
}

# ── Sensor / Transmitter ──
SENSOR_PARAMS = {
    'Thi': 200.0,
    'Tlow': 100.0,
    'tauT': 0.75,
}

# ── PID Controller ──
PID_PARAMS = {
    'mode': 'PIDS',
    'Kc': 6.13,
    'tauI': 2.30,
    'tauD': 0.58,
    'Alpha': 0.125,
    'M_min': 0.0,
    'M_max': 100.0,
}

# ── Actuator / Valve ──
ACTUATOR_PARAMS = {
    'tauV': 0.2,
    'fmax': 84.4,
    'vp_min': 0.0,
    'vp_max': 100.0,
    'valve_type': 'equal_percentage',
}

# ── Simulation Timing ──
SIM_PARAMS = {
    'Ts': 0.01,
    'steps_per_tick': 1,
    'tick_interval': 0.1,
}

# ── Initial Conditions ──
INITIAL_CONDITIONS = {
    'T': 150.0,
    'Ts': 230.0,
    'Tm': 150.0,
    'SP': 150.0,
    'F': 15.0,
    'Ti': 100.0,
    'W': 42.23,
    'vp': 82.3,
    'I': 82.3,
    'D': 50.0,
    'C': 50.0,
    'M': 82.3,
    'R': 50.0,
    'V': 120.0,
}

# ── Signal Definitions ──
SIGNALS_CONFIG = {
    'T':  {'label': 'Tank Temp',      'unit': '°F',     'color': '#FF6B6B', 'low': 100, 'high': 200},
    'Ts': {'label': 'Coil Temp',      'unit': '°F',     'color': '#FFA726', 'low': 150, 'high': 400},
    'C':  {'label': 'Transmitter',    'unit': '%TO',    'color': '#42A5F5', 'low': 0,   'high': 100},
    'M':  {'label': 'Controller Out', 'unit': '%CO',    'color': '#AB47BC', 'low': 0,   'high': 100},
    'W':  {'label': 'Steam Flow',     'unit': 'lb/min', 'color': '#66BB6A', 'low': 0,   'high': 84.4},
    'R':  {'label': 'Reference',      'unit': '%',      'color': '#FFEE58', 'low': 0,   'high': 100},
    'vp': {'label': 'Valve Pos',      'unit': '%vp',    'color': '#26C6DA', 'low': 0,   'high': 100},
    'SP': {'label': 'Set Point',      'unit': '°F',     'color': '#FFEE58', 'low': 0,   'high': 100},
}

SIGNAL_IDS = list(SIGNALS_CONFIG.keys())

# ── Display Map: SVG element id → signal key + display unit ──
DISPLAY_MAP = {
    'fi-100':  {'signal': 'W',  'unit': 'lb/min'},
    'fi-101':  {'signal': 'F',  'unit': 'ft³/min'},
    'tic-100': {'signal': 'T',  'unit': '°F'},
    'ti-100':  {'signal': 'Ti', 'unit': '°F'},
    'li-100':  {'signal': 'V',  'unit': 'ft³'},
    'fi-102':  {'signal': 'F',  'unit': 'ft³/min'},
    'vp-100':  {'signal': 'vp', 'unit': '%'},
}

# ── Chart ──
CHART_DISPLAY_WINDOW = 200
MAX_HISTORY = 5000

# ── Animation CSS selectors ──
ANIM_SEL = (
    '.pump-blades, .stirred-upper-blades, .stirred-lower-blades, '
    '.fluid-body, .fluid-wave-1, .fluid-wave-2, .fluid-wave-3'
)

# ══════════════════════════════════════════════════════════════
# CONTROLLER DRAWER CONFIG
# Maps each clickable SVG card id → drawer title + tunable params.
# 'field' is the local key the modal uses (no engine here — UI only).
# ══════════════════════════════════════════════════════════════
CONTROLLER_DRAWER_CONFIG = {
    'tic-100': {
        'label': 'TIC-100 — Temperature Controller',
        'params': [
            {
                'key': 'sp',
                'label': 'Set Point (°F)',
                'field': 'sp',
                'min': 50.0,
                'max': 300.0,
                'step': 0.1,
            },
            {
                'key': 'kc',
                'label': 'Gain (Kc)',
                'field': 'kc',
                'min': 0.0,
                'max': 50.0,
                'step': 0.01,
            },
            {
                'key': 'tau_i',
                'label': 'Integral Time (τI) min',
                'field': 'tau_i',
                'min': 0.01,
                'max': 100.0,
                'step': 0.01,
            },
            {
                'key': 'tau_d',
                'label': 'Derivative Time (τD) min',
                'field': 'tau_d',
                'min': 0.0,
                'max': 50.0,
                'step': 0.01,
            },
        ],
    },
    'fi-100': {
        'label': 'FI-100 — Steam Flow Indicator',
        'params': [],
    },
    'fi-101': {
        'label': 'FI-101 — Feed Flow Indicator',
        'params': [
            {
                'key': 'feed_flow',
                'label': 'Feed Flow Rate (ft³/min)',
                'field': 'feed_flow',
                'min': 0.0,
                'max': 200.0,
                'step': 0.1,
            },
        ],
    },
    'ti-100': {
        'label': 'TI-100 — Feed Temperature Indicator',
        'params': [
            {
                'key': 'feed_temp',
                'label': 'Feed Temperature (°F)',
                'field': 'feed_temp',
                'min': 50.0,
                'max': 250.0,
                'step': 0.1,
            },
        ],
    },
    'li-100': {
        'label': 'LI-100 — Level Indicator',
        'params': [],
    },
    'fi-102': {
        'label': 'FI-102 — Product Flow Indicator',
        'params': [],
    },
    'vp-100': {
        'label': 'VP-100 — Valve Position',
        'params': [],
    },
}
