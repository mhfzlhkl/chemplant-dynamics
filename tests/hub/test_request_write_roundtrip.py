# tests/hub/test_request_write_roundtrip.py

"""Bidirectional path — child requests, engine receives, hub fans out.

Property tested:

- ``hub.request_write('sp', 175.0)`` calls
  ``bridge.set_input_value('TSP-100.SP', 175.0)`` exactly once.
- The snapshot reflects the write immediately (no waiting for the
  engine echo).
- When the engine echoes the value back (next step record carrying
  ``inputs['TSP-100.SP']=175.0``), the hub's snapshot still says
  175.0 and every subscriber sees the same value.
- Status-key writes route through
  ``bridge.apply_runtime_configuration(restart_if_needed=True)``.
"""

from __future__ import annotations

from tests.hub.conftest import RecordingChild


def test_sp_write_calls_set_input_value_exactly_once(fake_bridge, hub) -> None:
    hub.request_write('sp', 175.0)
    assert fake_bridge.calls['set_input_value'] == 1
    assert fake_bridge.last_set_input == ('TSP-100.SP', 175.0)
    # Snapshot updated immediately.
    assert hub.snapshot()['sp'] == 175.0


def test_status_write_triggers_apply_runtime_configuration(
    fake_bridge, hub,
) -> None:
    hub.request_write('tic_status', 1.0)  # 1 = Manual
    assert fake_bridge.calls['apply_runtime_configuration'] == 1
    assert fake_bridge.last_apply_kwargs == {'restart_if_needed': True}
    assert fake_bridge.state.controller_mode == 'Manual'
    assert hub.snapshot()['tic_status'] == 1.0


def test_engine_echo_propagates_via_next_tick(fake_bridge, hub) -> None:
    a = RecordingChild('a')
    hub.subscribe(a)

    # 1. Child writes SP=175.
    hub.request_write('sp', 175.0)

    # 2. Engine emits a step whose 'inputs' echo the override.
    fake_bridge.emit_step(
        step_index=0, time_min=0.1,
        outputs={'STHR.T': 152.4},
        inputs={'TSP-100.SP': 175.0},
    )
    hub.tick_once()

    assert hub.snapshot()['sp'] == 175.0
    assert hub.snapshot()['pv'] == 152.4

    delta, snapshot, _ = a.ticks[0]
    # 'sp' came in via the input echo branch; 'pv' via output.
    assert 'sp' in delta
    assert 'pv' in delta
    assert snapshot['sp'] == 175.0


def test_read_only_pv_write_is_local_only(fake_bridge, hub) -> None:
    """A request_write to a read-only PV must NOT touch the engine."""
    hub.request_write('pv', 999.0)
    assert fake_bridge.calls['set_input_value'] == 0
    assert fake_bridge.calls['apply_runtime_configuration'] == 0
    # Snapshot still reflects the write locally (so the calling child
    # doesn't see stale data on the same tick).
    assert hub.snapshot()['pv'] == 999.0
