from __future__ import annotations

from cases.sthr import config as cfg
from cases.sthr.session import STHRSimulationSession
from core.appdb import AppDB
from systems.builders.sthr_builder import build_sthr_closed_loop_system


def test_sthr_builder_supports_automatic_manual_off_modes() -> None:
    ts = float(cfg.to_minutes(cfg.SIMULATION_PARAMS.get("Ts", 0.01), "minutes"))

    auto_sys, auto_in, auto_out = build_sthr_closed_loop_system(
        ts,
        loop_modes={"TIC-100": "automatic"},
    )
    assert auto_sys is not None
    assert "TC-100.Kc" in auto_in
    assert "TSP-100.SP" in auto_in
    assert "TV-100.M" not in auto_in
    assert "STHR.W" not in auto_in
    assert "TC-100.M" in auto_out
    assert "TV-100.F" in auto_out
    assert "TSP-100.R" in auto_out

    manual_sys, manual_in, manual_out = build_sthr_closed_loop_system(
        ts,
        loop_modes={"TIC-100": "manual"},
    )
    assert manual_sys is not None
    assert "TV-100.M" in manual_in
    assert "TC-100.Kc" not in manual_in
    assert "TSP-100.SP" not in manual_in
    assert "TV-100.F" in manual_out
    assert "TC-100.M" not in manual_out
    assert "TSP-100.R" not in manual_out

    off_sys, off_in, off_out = build_sthr_closed_loop_system(
        ts,
        loop_modes={"TIC-100": "off"},
    )
    assert off_sys is not None
    assert "STHR.W" in off_in
    assert "TV-100.M" not in off_in
    assert "TC-100.Kc" not in off_in
    assert "TSP-100.SP" not in off_in
    assert "TT-100.C" in off_out
    assert "TV-100.F" not in off_out
    assert "TC-100.M" not in off_out
    assert "TSP-100.R" not in off_out


def test_sthr_session_honors_loop_mode_override() -> None:
    db = AppDB()

    original = dict(cfg.CONTROLLER_MODE)
    try:
        cfg.CONTROLLER_MODE["Mode"] = "Automatic"
        cfg.CONTROLLER_MODE["LoopModes"] = {"TIC-100": "off"}

        session = STHRSimulationSession(appdb=db)
        system, inplist, outlist, _x0, _in_tags, _st_tags, _out_tags = session.resolve_runtime(
            "Automatic", session.Ts
        )

        assert system is not None
        assert "STHR.W" in inplist
        assert "TV-100.M" not in inplist
        assert "TC-100.Kc" not in inplist
        assert "TSP-100.SP" not in inplist
        assert "TT-100.C" in outlist
        assert "TV-100.F" not in outlist
        assert "TC-100.M" not in outlist
    finally:
        cfg.CONTROLLER_MODE.clear()
        cfg.CONTROLLER_MODE.update(original)
