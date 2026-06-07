from __future__ import annotations

import numpy as np

from cases.biodiesel import config as cfg
from engine.runtime.step_io_runner import StepInputOutputRunner
from systems.builders.biodiesel_builder import build_biodiesel_closed_loop_system


def test_biodiesel_closed_loop_builder_step() -> None:
    ts = float(cfg.to_minutes(cfg.SIMULATION_PARAMS.get("Ts", 0.5), "seconds"))
    system, inplist, outlist = build_biodiesel_closed_loop_system(ts)

    assert system is not None
    assert inplist
    assert outlist
    assert "TSP-100.SP" in inplist
    assert "TV-100.F" in outlist

    x0 = [0.0] * len(getattr(system, "state_labels", []))

    runner = StepInputOutputRunner(
        sys=system,
        dt=ts,
        x0=x0,
        input_labels=inplist,
        output_labels=outlist,
        output_timing="pre",
    )

    u = {name: 0.0 for name in inplist}
    u.update(cfg.default_inputs_for_mode("automatic"))
    y = runner.step(u)

    assert len(y) == len(outlist)
    assert np.isfinite(np.asarray(list(y.values()), dtype=float)).all()


def test_biodiesel_closed_loop_builder_supports_independent_loop_modes() -> None:
    ts = float(cfg.to_minutes(cfg.SIMULATION_PARAMS.get("Ts", 0.5), "seconds"))
    system, inplist, outlist = build_biodiesel_closed_loop_system(
        ts,
        loop_modes={
            "LIC-100": "automatic",
            "TIC-100": "manual",
            "FIC-100": "automatic",
            "FIC-101": "manual",
            "FIC-102": "automatic",
        },
    )

    assert system is not None
    assert "TC-100.Kc" not in inplist
    assert "TSP-100.SP" not in inplist
    assert "TV-100.M" in inplist
    assert "FC-101.Kc" not in inplist
    assert "FSP-101.SP" not in inplist
    assert "FV-101.M" in inplist

    # Auto loops still expose controller and setpoint channels.
    assert "LC-100.Kc" in inplist
    assert "LSP-100.SP" in inplist
    assert "FC-100.Kc" in inplist
    assert "FSP-100.SP" in inplist
    assert "FC-102.Kc" in inplist
    assert "FSP-102.SP" in inplist

    assert "TC-100.M" not in outlist
    assert "TSP-100.R" not in outlist
    assert "FC-101.M" not in outlist
    assert "FSP-101.R" not in outlist

    assert "LC-100.M" in outlist
    assert "LSP-100.R" in outlist
    assert "FC-100.M" in outlist
    assert "FSP-100.R" in outlist
    assert "FC-102.M" in outlist
    assert "FSP-102.R" in outlist


def test_biodiesel_closed_loop_builder_supports_loop_off_mode() -> None:
    ts = float(cfg.to_minutes(cfg.SIMULATION_PARAMS.get("Ts", 0.5), "seconds"))
    system, inplist, outlist = build_biodiesel_closed_loop_system(
        ts,
        loop_modes={
            "LIC-100": "off",
            "TIC-100": "automatic",
            "FIC-100": "manual",
            "FIC-101": "off",
            "FIC-102": "automatic",
        },
    )

    assert system is not None

    # Off loops expose plant MV directly, without controller/actuator/sensor I/O.
    assert "biodiesel_reactor.f_FAME" in inplist
    assert "LC-100.Kc" not in inplist
    assert "LSP-100.SP" not in inplist
    assert "LV-100.M" not in inplist
    assert "LT-100.C" not in outlist
    assert "LV-100.F" not in outlist

    assert "biodiesel_reactor.f_MeOH" in inplist
    assert "FC-101.Kc" not in inplist
    assert "FSP-101.SP" not in inplist
    assert "FV-101.M" not in inplist
    assert "FT-101.C" not in outlist
    assert "FV-101.F" not in outlist

    # Manual and automatic loops remain available in the same mixed system.
    assert "FV-100.M" in inplist
    assert "FC-100.Kc" not in inplist
    assert "TC-100.Kc" in inplist
    assert "TSP-100.SP" in inplist
