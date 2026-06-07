# tests/hub/test_engine_control_oneline.py

"""User requirement: control-engine actions are one-line passthroughs.

For every public method on :class:`EngineControl` we assert that
calling it once results in EXACTLY one corresponding bridge call —
no fan-out, no notify, no broadcast. Subscribers MUST react via
the next ``_tick`` instead.
"""

from __future__ import annotations

from app.hub import SignalHub
from app.hub.controller_registry import ControllerRegistry, ControllerSpec
from tests.hub.conftest import RecordingChild


def _empty_registry() -> ControllerRegistry:
    return ControllerRegistry([
        ControllerSpec(modal_key='pv', engine_tag='STHR.T', role='pv'),
    ])


def test_run_calls_bridge_start_once(fake_bridge) -> None:
    hub = SignalHub(fake_bridge, _empty_registry())
    hub.engine_control.run()
    assert fake_bridge.calls['start'] == 1
    assert fake_bridge.calls['pause'] == 0
    assert fake_bridge.calls['reset'] == 0
    assert fake_bridge.calls['apply_runtime_configuration'] == 0


def test_stop_calls_bridge_pause_once(fake_bridge) -> None:
    hub = SignalHub(fake_bridge, _empty_registry())
    hub.engine_control.stop()
    assert fake_bridge.calls['pause'] == 1


def test_reset_calls_bridge_reset_once(fake_bridge) -> None:
    hub = SignalHub(fake_bridge, _empty_registry())
    hub.engine_control.reset()
    assert fake_bridge.calls['reset'] == 1


def test_set_real_time_writes_state_and_applies_once(fake_bridge) -> None:
    hub = SignalHub(fake_bridge, _empty_registry())
    hub.engine_control.set_real_time(False)
    assert fake_bridge.state.real_time is False
    assert fake_bridge.calls['apply_runtime_configuration'] == 1
    assert fake_bridge.last_apply_kwargs == {'restart_if_needed': False}


def test_set_mode_writes_state_and_applies_with_restart(fake_bridge) -> None:
    hub = SignalHub(fake_bridge, _empty_registry())
    hub.engine_control.set_mode('Manual')
    assert fake_bridge.state.controller_mode == 'Manual'
    assert fake_bridge.calls['apply_runtime_configuration'] == 1
    assert fake_bridge.last_apply_kwargs == {'restart_if_needed': True}


def test_set_acceleration_writes_state_and_applies_once(fake_bridge) -> None:
    hub = SignalHub(fake_bridge, _empty_registry())
    hub.engine_control.set_acceleration(4.0)
    assert fake_bridge.state.acceleration == 4.0
    assert fake_bridge.calls['apply_runtime_configuration'] == 1


def test_set_time_end_forwards_raw_value(fake_bridge) -> None:
    hub = SignalHub(fake_bridge, _empty_registry())
    hub.engine_control.set_time_end('45.5')
    assert fake_bridge.calls['set_time_end_from_ui'] == 1
    assert fake_bridge.last_time_end == '45.5'


def test_engine_control_does_not_notify_subscribers(fake_bridge) -> None:
    """run/stop/reset must NOT call ``on_tick`` on any subscriber —
    that's the hub's job during ``_tick``, not engine_control's.
    """
    hub = SignalHub(fake_bridge, _empty_registry())
    spy = RecordingChild('spy')
    hub.subscribe(spy)

    hub.engine_control.run()
    hub.engine_control.stop()
    hub.engine_control.reset()
    hub.engine_control.set_real_time(True)

    assert spy.ticks == []  # zero ticks dispatched
