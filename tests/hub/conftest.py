# tests/hub/conftest.py

"""Shared fakes for the hub unit tests.

Pure-Python — no NiceGUI / no engine. ``SignalHub.start`` falls
back silently when ``nicegui.ui.timer`` isn't available, so the
tests drive ``hub.tick_once()`` manually.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from queue import Queue
from typing import Any

import pytest

from app.hub.controller_registry import ControllerRegistry, ControllerSpec
from app.hub.signal_hub import SignalHub


@dataclass
class FakeBridgeState:
    real_time: bool = True
    acceleration: float = 1.0
    controller_mode: str = 'Automatic'
    scenario: str = 'operational'
    status: str = 'idle'
    global_sim_time: float = 0.0
    last_step: int = -1
    input_overrides: dict[str, float] = field(default_factory=dict)


@dataclass
class FakeStepRecord:
    kind: str = 'step'
    message: str = ''
    step_index: int | None = None
    time_min: float | None = None
    real_time: str | None = None
    mode: str | None = None
    inputs: dict = field(default_factory=dict)
    states: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)
    selected_fields: list = field(default_factory=list)


class FakeBridge:
    """Minimal bridge stand-in — exposes the surface the hub uses."""

    def __init__(self) -> None:
        self.state = FakeBridgeState()
        self._records: Queue = Queue()
        # Call counters so tests assert one-line-to-engine guarantees.
        self.calls: dict[str, int] = {
            'start': 0,
            'pause': 0,
            'reset': 0,
            'apply_runtime_configuration': 0,
            'set_input_value': 0,
            'set_time_end_from_ui': 0,
            'drain_records': 0,
        }
        # Track the args for the more interesting calls.
        self.last_set_input: tuple[str, float] | None = None
        self.last_time_end: Any = None
        self.last_apply_kwargs: dict | None = None

    # ── Engine surface ──────────────────────────────────────
    def start(self) -> None:
        self.calls['start'] += 1
        self.state.status = 'running'

    def pause(self) -> None:
        self.calls['pause'] += 1
        self.state.status = 'paused'

    def reset(self) -> None:
        self.calls['reset'] += 1
        self.state.status = 'idle'
        self.state.last_step = -1
        self.state.global_sim_time = 0.0
        # Re-queue is not required by the hub tests — the hub's
        # ``reset_snapshot_to_seed`` handles the snapshot side.

    def apply_runtime_configuration(self, *, restart_if_needed: bool = True) -> None:
        self.calls['apply_runtime_configuration'] += 1
        self.last_apply_kwargs = {'restart_if_needed': bool(restart_if_needed)}

    def set_input_value(self, name: str, value: float) -> None:
        self.calls['set_input_value'] += 1
        self.last_set_input = (name, float(value))
        self.state.input_overrides[name] = float(value)

    def set_time_end_from_ui(self, value: Any) -> None:
        self.calls['set_time_end_from_ui'] += 1
        self.last_time_end = value

    # ── Records queue (real Queue, real semantics) ──────────
    def emit_step(
        self,
        *,
        step_index: int,
        time_min: float,
        mode: str = 'Automatic',
        outputs: dict | None = None,
        inputs: dict | None = None,
        states: dict | None = None,
    ) -> None:
        rec = FakeStepRecord(
            kind='step',
            step_index=step_index,
            time_min=time_min,
            mode=mode,
            outputs=dict(outputs or {}),
            inputs=dict(inputs or {}),
            states=dict(states or {}),
        )
        self._records.put(rec)
        self.state.last_step = step_index
        self.state.global_sim_time = time_min

    def drain_records(self, max_records: int = 300) -> list:
        self.calls['drain_records'] += 1
        out: list = []
        while len(out) < max_records:
            if self._records.empty():
                break
            out.append(self._records.get_nowait())
        return out


class RecordingChild:
    """Subscriber that records every ``on_tick`` invocation verbatim.

    The hub guarantees every subscriber receives the SAME
    ``snapshot`` mapping in the SAME turn, so the tests check
    object identity (``is``) against the snapshot the first child
    saw.
    """

    def __init__(self, name: str = 'child') -> None:
        self.name = name
        self.ticks: list[tuple[frozenset, dict, Any]] = []

    def on_tick(self, delta_keys, snapshot, meta) -> None:
        # We deliberately store the snapshot mapping by identity — the
        # hub gives every child the SAME view object per tick.
        self.ticks.append((delta_keys, snapshot, meta))


def _make_simple_registry() -> ControllerRegistry:
    return ControllerRegistry([
        ControllerSpec(
            modal_key='pv', engine_tag='STHR.T', svg_id='tic-100',
            unit='°F', decimals=1, role='pv', writable=False,
        ),
        ControllerSpec(
            modal_key='sp', engine_tag='TSP-100.SP',
            unit='°F', decimals=1, role='sp', writable=True,
        ),
        ControllerSpec(
            modal_key='tic_status', engine_tag=None, role='status',
            writable=True,
        ),
        ControllerSpec(
            modal_key='fi101_pv', engine_tag='STHR.F', svg_id='fi-101',
            unit='ft³/min', decimals=1, role='pv', writable=False,
        ),
        ControllerSpec(
            modal_key='fi102_pv', engine_tag=None, svg_id='fi-102',
            unit='ft³/min', decimals=1, role='pv', writable=False,
            derived_from='fi101_pv',
        ),
    ])


@pytest.fixture
def fake_bridge() -> FakeBridge:
    return FakeBridge()


@pytest.fixture
def simple_registry() -> ControllerRegistry:
    return _make_simple_registry()


@pytest.fixture
def hub(fake_bridge: FakeBridge, simple_registry: ControllerRegistry) -> SignalHub:
    return SignalHub(fake_bridge, simple_registry, initial={'pv': 150.0})
