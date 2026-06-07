from __future__ import annotations

from core.appdb import AppDB
from cases.biodiesel import config as cfg
from cases.biodiesel.session import BiodieselSimulationSession


def test_biodiesel_session_supports_all_modes() -> None:
    db = AppDB()

    for mode in ("Automatic", "Manual", "Off"):
        session = BiodieselSimulationSession(appdb=db)
        session.mode = mode
        session.mode_key = mode.lower()
        (
            system,
            inplist,
            outlist,
            x0,
            _input_tags,
            _state_tags,
            _output_tags,
        ) = session.resolve_runtime(mode, session.Ts)

        assert system is not None
        assert inplist
        assert outlist
        assert x0


def test_biodiesel_session_automatic_honors_per_loop_modes() -> None:
    db = AppDB()

    original = dict(cfg.CONTROLLER_MODE)
    try:
        cfg.CONTROLLER_MODE["Mode"] = "Automatic"
        cfg.CONTROLLER_MODE["LoopModes"] = {
            "TIC-100": "manual",
            "LIC-100": "off",
            "FIC-101": "manual",
        }

        session = BiodieselSimulationSession(appdb=db)
        system, inplist, outlist, _x0, _in_tags, _st_tags, _out_tags = session.resolve_runtime(
            "Automatic", session.Ts
        )

        assert system is not None
        assert "TV-100.M" in inplist
        assert "TC-100.Kc" not in inplist
        assert "TSP-100.SP" not in inplist
        assert "FV-101.M" in inplist
        assert "FC-101.Kc" not in inplist
        assert "FSP-101.SP" not in inplist
        assert "biodiesel_reactor.f_FAME" in inplist
        assert "LC-100.Kc" not in inplist
        assert "LSP-100.SP" not in inplist
        assert "FSP-100.SP" in inplist
        assert "TC-100.M" not in outlist
        assert "TSP-100.R" not in outlist
    finally:
        cfg.CONTROLLER_MODE.clear()
        cfg.CONTROLLER_MODE.update(original)


def test_biodiesel_session_off_mode_allows_single_loop_auto_override() -> None:
    db = AppDB()

    original = dict(cfg.CONTROLLER_MODE)
    try:
        cfg.CONTROLLER_MODE["Mode"] = "Off"
        cfg.CONTROLLER_MODE["LoopModes"] = {
            "TIC-100": "automatic",
        }

        session = BiodieselSimulationSession(appdb=db)
        _system, inplist, outlist, _x0, _in_tags, _st_tags, _out_tags = session.resolve_runtime(
            "Off", session.Ts
        )

        # Base mode off -> loops off by default, except explicit override.
        assert "biodiesel_reactor.f_FAME" in inplist
        assert "biodiesel_reactor.f_oil" in inplist
        assert "TV-100.M" not in inplist
        assert "TC-100.Kc" in inplist
        assert "TSP-100.SP" in inplist
        assert "TT-100.C" in outlist
        assert "TV-100.F" in outlist
    finally:
        cfg.CONTROLLER_MODE.clear()
        cfg.CONTROLLER_MODE.update(original)
