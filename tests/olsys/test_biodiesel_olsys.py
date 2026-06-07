from __future__ import annotations

import numpy as np

from cases.biodiesel import config as cfg
from engine.runtime.step_io_runner import StepInputOutputRunner
from systems.builders.biodiesel_builder import build_biodiesel_closed_loop_system


def test_biodiesel_open_loop_builder_step() -> None:
    ts = float(cfg.to_minutes(cfg.SIMULATION_PARAMS.get("Ts", 0.5), "seconds"))
    system, inplist, outlist = build_biodiesel_closed_loop_system(
        ts,
        loop_modes={
            "LIC-100": "manual",
            "TIC-100": "manual",
            "FIC-100": "manual",
            "FIC-101": "manual",
            "FIC-102": "manual",
        },
    )

    assert system is not None
    assert inplist
    assert outlist
    assert "TV-100.M" in inplist
    assert "TT-100.C" in outlist

    x0 = [*cfg.default_state_vector()]

    runner = StepInputOutputRunner(
        sys=system,
        dt=ts,
        x0=x0,
        input_labels=inplist,
        output_labels=outlist,
        output_timing="pre",
    )

    y = runner.step(cfg.default_inputs_for_mode("manual"))

    assert len(y) == len(outlist)
    assert np.isfinite(np.asarray(list(y.values()), dtype=float)).all()
