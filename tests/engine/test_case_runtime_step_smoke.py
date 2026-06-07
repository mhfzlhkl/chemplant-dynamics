from __future__ import annotations

from core.appdb import AppDB
from engine.runtime.case_registry import get_session_factory, list_cases


TARGET_CASES = ("sthr", "biodiesel")


def test_case_registry_runtime_step_smoke_for_target_cases() -> None:
    discovered = set(list_cases())
    missing = [case for case in TARGET_CASES if case not in discovered]
    assert not missing, f"Missing case plugins: {missing}; discovered={sorted(discovered)}"

    for case_name in TARGET_CASES:
        db = AppDB()
        session_factory = get_session_factory(case_name, db)
        session = session_factory()

        t0 = float(session.t)
        y = session.step()

        assert isinstance(y, dict)
        assert y, f"Expected non-empty outputs for case '{case_name}'"
        assert float(session.t) > t0, f"Expected simulation time to advance for '{case_name}'"

        session.flush_timeseries_buffer()
        assert db.timeseries, f"Expected historian records for case '{case_name}'"
