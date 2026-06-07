from __future__ import annotations

from core.appdb import appdb
from gateway.bridge import Bridge as GenericBridge
from gateway.config_registry import list_case_configs


def test_generic_bridge_bootstrap_all_cases() -> None:
    cases = list_case_configs()
    assert cases, "Expected at least one discoverable case config"

    for case_name in cases:
        bridge = GenericBridge(appdb=appdb, case_name=case_name)
        bridge.bind_profile(browser_id=f"pytest-{case_name}", profile_storage={})

        assert bridge.case_name == case_name
        assert bridge.cfg is not None
        assert bridge.supported_modes()


def test_generic_bridge_controller_mode_change_refreshes_available_input_fields() -> None:
    bridge = GenericBridge(appdb=appdb, case_name='sthr')
    bridge.bind_profile(browser_id='pytest-sthr-mode-refresh', profile_storage={})

    assert 'input:TC-100.Kc' in bridge.state.available_log_fields

    bridge.state.controller_mode = 'Off'
    bridge.apply_runtime_configuration(restart_if_needed=False)
    assert 'input:TC-100.Kc' not in bridge.state.available_log_fields

    bridge.state.controller_mode = 'Automatic'
    bridge.apply_runtime_configuration(restart_if_needed=False)
    assert 'input:TC-100.Kc' in bridge.state.available_log_fields


def test_generic_bridge_startup_scenario_preserves_valve_positions_on_mode_change() -> None:
    """Verify that startup scenario maintains valve position 0 when switching from Off to Automatic."""
    bridge = GenericBridge(appdb=appdb, case_name='biodiesel')
    bridge.bind_profile(browser_id='pytest-biodiesel-startup', profile_storage={})

    # Set scenario to startup and mode to Off (as per main.py scenario logic)
    bridge.state.scenario = 'startup'
    bridge.state.controller_mode = 'Off'
    bridge.apply_runtime_configuration(restart_if_needed=False)

    # Check that valve commands are at 0 (Off mode)
    assert bridge.state.input_overrides.get('LV-100.M') == 0.0
    assert bridge.state.input_overrides.get('TV-100.M') == 100.0  # reverse/fail-open -> vp=0

    # Switch to Automatic mode while staying in startup scenario
    bridge.state.controller_mode = 'Automatic'
    bridge.apply_runtime_configuration(restart_if_needed=False)

    # Verify valve commands still at 0 (startup scenario forces actuator inputs)
    assert bridge.state.input_overrides.get('LV-100.M') == 0.0, 'LV-100.M should remain 0 in startup/auto'
    assert bridge.state.input_overrides.get('TV-100.M') == 100.0, 'TV-100.M should remain 100 in startup/auto'
    # But now controller parameters should be present
    assert 'LC-100.Kc' in bridge.state.input_overrides
    assert 'TC-100.Kc' in bridge.state.input_overrides
