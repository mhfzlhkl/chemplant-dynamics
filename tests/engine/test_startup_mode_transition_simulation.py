"""
Test startup scenario simulation behavior with mode transition during run.

This test reproduces the user's issue: starting a simulation with startup scenario
in Off mode, then changing to Automatic mid-run shows incorrect controller states
compared to starting directly in Automatic mode.
"""

import pytest
from core.appdb import appdb
from gateway.bridge import Bridge as GenericBridge
import time
import logging

# Enable debug logging to see worker behavior
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_startup_scenario_off_to_auto_mode_transition_mid_run() -> None:
    """
    Reproduce the user's issue: 
    1. Start with scenario=startup, mode=Off
    2. Run simulation
    3. Change mode to Automatic mid-run
    4. Observe controller states (should show the discrepancy user reported)
    """
    bridge = GenericBridge(appdb=appdb, case_name='biodiesel')
    bridge.bind_profile(browser_id='pytest-biodiesel-off-to-auto-midrun', profile_storage={})

    # Set scenario to startup and mode to Off
    bridge.state.scenario = 'startup'
    bridge.state.controller_mode = 'Off'
    bridge.apply_runtime_configuration(restart_if_needed=False)

    print("\n=== SCENARIO: Off-to-Automatic Mode Transition ===")
    print(f"Initial mode: {bridge.state.controller_mode}")
    print(f"Initial scenario: {bridge.state.scenario}")
    print(f"Initial input_overrides keys: {list(bridge.state.input_overrides.keys())}")

    # Verify startup actuator inputs are set
    assert bridge.state.input_overrides.get('LV-100.M') == 0.0
    assert bridge.state.input_overrides.get('TV-100.M') == 100.0

    # Start the simulation (Off mode)
    bridge.start()

    print(f"\nSimulation started in {bridge.state.controller_mode} mode")
    print(f"Runtime config time_end: {bridge.cfg.SIMULATION_PARAMS.get('time_end')}")
    
    # Let simulation run for a brief moment in Off mode
    time.sleep(2.0)

    print(f"\nAfter 2.0s in Off mode - Status: {bridge.state.status}")
    print(f"  Last step: {bridge.state.last_step}")
    print(f"  Time: {bridge.state.last_sim_time:.4f}")

    # Collect initial timesteps in Off mode
    initial_steps = bridge.state.last_step

    # Now change mode to Automatic mid-run
    print(f"\n--- Changing mode to Automatic (mid-run) ---")
    bridge.state.controller_mode = 'Automatic'
    bridge.apply_runtime_configuration(restart_if_needed=False)

    print(f"Mode changed to: {bridge.state.controller_mode}")
    print(f"Input overrides after mode change: {list(bridge.state.input_overrides.keys())}")

    # Verify controller parameters are now in input_overrides
    assert 'LC-100.Kc' in bridge.state.input_overrides, "Controller Kc missing after mode switch"
    assert 'TC-100.Kc' in bridge.state.input_overrides, "Temperature controller Kc missing after mode switch"

    # Let simulation continue in Automatic mode
    time.sleep(2.0)

    print(f"\nAfter mode switch + 2.0s in Auto mode - Status: {bridge.state.status}")
    print(f"  Last step: {bridge.state.last_step}")
    print(f"  Time: {bridge.state.last_sim_time:.4f}")

    steps_in_auto = bridge.state.last_step - initial_steps
    print(f"  Steps in Auto mode after switch: {steps_in_auto}")

    # Stop the simulation
    bridge.stop()
    time.sleep(0.2)
    print(f"\nSimulation stopped")

    # Now run the same scenario but starting directly in Automatic mode
    print(f"\n\n=== SCENARIO: Direct Automatic Mode (control) ===")
    
    bridge2 = GenericBridge(appdb=appdb, case_name='biodiesel')
    bridge2.bind_profile(browser_id='pytest-biodiesel-direct-auto', profile_storage={})

    bridge2.state.scenario = 'startup'
    bridge2.state.controller_mode = 'Automatic'
    bridge2.apply_runtime_configuration(restart_if_needed=False)

    print(f"Initial mode: {bridge2.state.controller_mode}")
    print(f"Initial scenario: {bridge2.state.scenario}")
    print(f"Initial input_overrides keys: {list(bridge2.state.input_overrides.keys())}")

    # Verify startup actuator inputs are set
    assert bridge2.state.input_overrides.get('LV-100.M') == 0.0
    assert bridge2.state.input_overrides.get('TV-100.M') == 100.0

    # Start the simulation directly in Automatic mode
    bridge2.start()

    print(f"\nSimulation started in {bridge2.state.controller_mode} mode")

    # Run for the same total duration
    time.sleep(1.0)

    print(f"\nAfter 1.0s in Auto mode - Status: {bridge2.state.status}")
    print(f"  Last step: {bridge2.state.last_step}")
    print(f"  Time: {bridge2.state.last_sim_time:.4f}")

    # Stop simulation
    bridge2.stop()
    time.sleep(0.2)
    print(f"\nSimulation stopped")

    # Compare results
    print(f"\n\n=== COMPARISON ===")
    print(f"Off-to-Auto scenario: {bridge.state.last_step} steps, Time: {bridge.state.last_sim_time:.4f}")
    print(f"Direct-Auto scenario: {bridge2.state.last_step} steps, Time: {bridge2.state.last_sim_time:.4f}")

    # If controller states are different, this will show the issue
    print(f"\nOff-to-Auto last record: {bridge.last_record if hasattr(bridge, 'last_record') else 'N/A'}")
    print(f"Direct-Auto last record: {bridge2.last_record if hasattr(bridge2, 'last_record') else 'N/A'}")

    # Query appdb for controller state information
    print(f"\n\n=== DATABASE RECORDS COMPARISON ===")
    
    # Get records from session for Off-to-Auto scenario
    if bridge._session:
        historian = getattr(bridge._session, 'historian', None)
        if historian:
            print(f"\nOff-to-Auto scenario - historian records count: {historian.record_count}")
            
    # Get records from session for Direct-Auto scenario
    if bridge2._session:
        historian2 = getattr(bridge2._session, 'historian', None)
        if historian2:
            print(f"Direct-Auto scenario - historian records count: {historian2.record_count}")

    # The critical output: show what the user sees
    print(f"\n{'='*60}")
    print("If controller states differ significantly between the two scenarios,")
    print("this indicates the issue described by the user.")
    print(f"{'='*60}\n")


def test_startup_scenario_state_recovery_after_mode_change() -> None:
    """
    Test whether controller states are properly recovered/initialized
    when switching from Off to Automatic mid-run.
    
    This test examines the controller state object (I_state, D_state) to see
    if they're properly reset when mode changes.
    """
    bridge = GenericBridge(appdb=appdb, case_name='biodiesel')
    bridge.bind_profile(browser_id='pytest-biodiesel-state-recovery', profile_storage={})

    bridge.state.scenario = 'startup'
    bridge.state.controller_mode = 'Off'
    bridge.apply_runtime_configuration(restart_if_needed=False)

    print("\n=== STATE RECOVERY TEST ===")
    print(f"Initial setup: scenario={bridge.state.scenario}, mode={bridge.state.controller_mode}")

    # Start in Off mode
    bridge.start()

    time.sleep(0.3)
    initial_time = bridge.state.last_sim_time
    print(f"After 0.3s in Off mode - Time: {initial_time:.4f}")

    # Change to Automatic
    bridge.state.controller_mode = 'Automatic'
    bridge.apply_runtime_configuration(restart_if_needed=False)
    print(f"Mode changed to Automatic")

    # Run longer to see if controller accumulates state properly
    time.sleep(0.7)
    final_time = bridge.state.last_sim_time
    print(f"After 0.7s in Automatic mode - Time: {final_time:.4f}")
    print(f"Total simulation time: {final_time:.4f}")

    # Stop
    bridge.stop()
    time.sleep(0.2)

    # Check if controller state values are reasonable
    # (This is where the user would see wrong controller output if state wasn't recovered)
    print(f"\nController parameters in input_overrides:")
    for key in sorted([k for k in bridge.state.input_overrides.keys() if 'Kc' in k or 'tau' in k or 'SP' in k]):
        value = bridge.state.input_overrides[key]
        print(f"  {key}: {value}")

    print(f"\nIf you see unexpected/zero values above, it indicates state wasn't recovered properly.")
