import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

import control as ct
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from models import (
    ActuatorSystem,
    ControllerSystem,
    SensorTransmitterSystem,
    SetPointSystem,
    STHRSystem,
)
from systems.configs.sthr_config import (
    ACTUATOR_PARAMS,
    CONTROLLER_PARAMS,
    PROCESS_PARAMS,
    SENSOR_TRANSMITTER_PARAMS,
    SETPOINT_PARAMS,
)

Ts = 0.01

# PROCESS
plant = STHRSystem(**PROCESS_PARAMS, dt=Ts)
# print(f'{plant.system}')

# ACTUATORS
TIC_100_TV = ActuatorSystem(**ACTUATOR_PARAMS["TIC-100"], dt=Ts)
# print(f'{TIC_100_TV.system}')

# CONTROLLERS
TIC_100_TC = ControllerSystem(**CONTROLLER_PARAMS["TIC-100"], dt=Ts)
# print(f'{TIC_100_TC.system}')

# SENSORS & TRANSMITTERS
TIC_100_TT = SensorTransmitterSystem(**SENSOR_TRANSMITTER_PARAMS["TIC-100"], dt=Ts)
# print(f'{TIC_100_TT.system}')

# SETPOINTS
TIC_100_TSP = SetPointSystem(**SETPOINT_PARAMS["TIC-100"], dt=Ts)
# print(f'{TIC_100_TSP.system}')

connections = [
    ["STHR.W", "TV-100.F"],
    ["TT-100.PV", "STHR.T"],
]

inplist = ["TV-100.M", "STHR.F", "STHR.Ti"]

outlist = [
    "STHR.T",
    "STHR.Ts",
    "TT-100.C",
    "TV-100.F",
]

clsys = ct.InterconnectedSystem(
    syslist=[
        plant.system,
        TIC_100_TT.system,
        TIC_100_TV.system,
    ],
    connections=connections,
    inplist=inplist,
    outlist=outlist,
    name="STHR_OpenLoopSystem",
)

print(f"{clsys}")

# SIMULATION
time_end = 30.0
time = np.arange(0, time_end + Ts, Ts)

# SETPOINTS
nom_TV_100_M = 82.3

TV_100_M = np.full_like(time, nom_TV_100_M)

TV_100_M[time >= 1.0] = 82.3

# INPUTS/DISTURBANCES
nom_STHR_F = 15.0
nom_STHR_Ti = 100.0

STHR_F = np.full_like(time, nom_STHR_F)
STHR_Ti = np.full_like(time, nom_STHR_Ti)

STHR_F[time >= 1.0] = 15.0
STHR_Ti[time >= 1.0] = 100.0

U = np.vstack([TV_100_M, STHR_F, STHR_Ti])

# STATES
T_ss = 150.0
Ts_ss = 230.0
TT_100_PVm_ss = 150.0
TV_100_vp_ss = 82.3

X0 = np.array([T_ss, Ts_ss, TT_100_PVm_ss, TV_100_vp_ss])

response = ct.input_output_response(clsys, T=time, U=U, X0=X0, return_x=True)

"""
Outputs:
 * y[0] <- STHR.T
 * y[1] <- STHR.Ts
 * y[2] <- TT-100.C
 * y[3] <- TV-100.F

"""

outputs_dict = {outlist[idx]: response.outputs[idx, :] for idx in range(len(outlist))}

"""
States :
 * x[0] <- STHR_T
 * x[1] <- STHR_Ts
 * x[2] <- TT-100_PVm
 * x[3] <- TV-100_vp

"""

states_dict = {
    clsys.state_labels[idx]: response.states[idx, :]
    for idx in range(len(clsys.state_labels))
}

print("✓ Outputs and states extracted successfully using outlist  mapping")
print(f"  Total outputs: {len(outputs_dict)}")
print(f"  Total states: {len(states_dict)}")

T = outputs_dict["STHR.T"]
Ts = outputs_dict["STHR.Ts"]
TV_100_F = outputs_dict["TV-100.F"]

plt.style.use("dark_background")
fig, ax = plt.subplots(3, 1, sharex=True, figsize=(10, 8))

ax[0].plot(time, T, label="T", color="y")
ax[0].set_ylabel("T")
ax[0].grid(True)

ax[1].plot(time, Ts, label="Ts", color="y")
ax[1].set_ylabel("Ts")
ax[1].grid(True)

ax[2].plot(time, TV_100_M, label="TV-100.M", color="y")
ax[2].set_ylabel("m")
ax[2].set_xlabel("Time (s)")
ax[2].grid(True)

plt.tight_layout()
plt.show()
