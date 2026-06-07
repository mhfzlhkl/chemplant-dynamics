"""Test that startup scenario produces consistent results regardless of mode initialization sequence."""

import pytest
from core.appdb import appdb
from gateway.bridge import Bridge as GenericBridge


def test_startup_scenario_consistent_results_mode_sequence() -> None:
    """
    Verify that startup scenario produces identical results whether:
    - Scenario A: Start in Automatic mode (mode set before simulation runs)
    - Scenario B: Start in Off mode, then switch to Automatic (mode changed during setup)
    
    This ensures the user's requirement is met:
    "hasil simulasi tetap tepat untuk kedua skenario baik dimulai dari off maupun dimulai dari auto"
    """
    
    # Scenario A: Startup with Automatic mode from the beginning
    bridge_a = GenericBridge(appdb=appdb, case_name='biodiesel')
    bridge_a.bind_profile(browser_id='pytest-biodiesel-startup-auto', profile_storage={})
    bridge_a.state.scenario = 'startup'
    bridge_a.state.controller_mode = 'Automatic'
    bridge_a.apply_runtime_configuration(restart_if_needed=False)
    
    # Verify startup actuator inputs are applied with Automatic mode
    assert bridge_a.state.input_overrides.get('LV-100.M') == 0.0, \
        'LV-100.M should be 0 for startup scenario regardless of mode'
    assert bridge_a.state.input_overrides.get('TV-100.M') == 100.0, \
        'TV-100.M should be 100 (reverse valve) for startup scenario'
    
    # Verify controller parameters are present in Automatic mode
    assert 'LC-100.Kc' in bridge_a.state.input_overrides, 'Controller Kc should be present in Automatic mode'
    assert 'TC-100.Kc' in bridge_a.state.input_overrides, 'Temperature controller Kc should be present'
    
    # Scenario B: Startup with Off mode first, then switch to Automatic
    bridge_b = GenericBridge(appdb=appdb, case_name='biodiesel')
    bridge_b.bind_profile(browser_id='pytest-biodiesel-startup-off-to-auto', profile_storage={})
    bridge_b.state.scenario = 'startup'
    bridge_b.state.controller_mode = 'Off'
    bridge_b.apply_runtime_configuration(restart_if_needed=False)
    
    # Verify startup actuator inputs with Off mode
    assert bridge_b.state.input_overrides.get('LV-100.M') == 0.0, \
        'LV-100.M should be 0 for startup scenario in Off mode'
    assert bridge_b.state.input_overrides.get('TV-100.M') == 100.0, \
        'TV-100.M should be 100 (reverse valve) for startup scenario'
    
    # Verify NO controller parameters in Off mode
    assert 'LC-100.Kc' not in bridge_b.state.input_overrides, \
        'Controller Kc should NOT be present in Off mode'
    assert 'TC-100.Kc' not in bridge_b.state.input_overrides, \
        'Temperature controller Kc should NOT be present in Off mode'
    
    # Now switch Scenario B to Automatic
    bridge_b.state.controller_mode = 'Automatic'
    bridge_b.apply_runtime_configuration(restart_if_needed=False)
    
    # Verify startup actuator inputs are preserved when switching to Automatic
    assert bridge_b.state.input_overrides.get('LV-100.M') == 0.0, \
        'LV-100.M should still be 0 after mode switch to Automatic'
    assert bridge_b.state.input_overrides.get('TV-100.M') == 100.0, \
        'TV-100.M should still be 100 after mode switch'
    
    # Verify controller parameters are NOW present after switch
    assert 'LC-100.Kc' in bridge_b.state.input_overrides, \
        'Controller Kc should now be present after switching to Automatic'
    assert 'TC-100.Kc' in bridge_b.state.input_overrides, \
        'Temperature controller Kc should now be present after switching'
    
    # The critical assertion: actuator commands should be IDENTICAL for both scenarios
    assert bridge_a.state.input_overrides.get('LV-100.M') == bridge_b.state.input_overrides.get('LV-100.M'), \
        'LV-100.M must be identical for both initialization sequences'
    assert bridge_a.state.input_overrides.get('TV-100.M') == bridge_b.state.input_overrides.get('TV-100.M'), \
        'TV-100.M must be identical for both initialization sequences'
    assert bridge_a.state.input_overrides.get('FV-100.M') == bridge_b.state.input_overrides.get('FV-100.M'), \
        'FV-100.M must be identical for both initialization sequences'
    assert bridge_a.state.input_overrides.get('FV-101.M') == bridge_b.state.input_overrides.get('FV-101.M'), \
        'FV-101.M must be identical for both initialization sequences'
    assert bridge_a.state.input_overrides.get('FV-102.M') == bridge_b.state.input_overrides.get('FV-102.M'), \
        'FV-102.M must be identical for both initialization sequences'
    
    # Also verify that controller parameters match in Automatic mode
    for key in ['LC-100.Kc', 'TC-100.Kc', 'TSP-100.SP', 'LSP-100.SP']:
        if key in bridge_a.state.input_overrides:
            assert bridge_a.state.input_overrides.get(key) == bridge_b.state.input_overrides.get(key), \
                f'{key} must be identical for both initialization sequences in Automatic mode'
