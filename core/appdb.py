# engine_root/core/appdb.py

"""AppDB — the in-memory historian used by every case.

This module is intentionally case-agnostic. Historically it imported
``cases.sthr.config`` to read the timeseries backend settings, which
made ``core`` depend on a specific case. That coupling has been
removed: the timeseries backend is now resolved per case via
:meth:`set_active_case_config` (called by the bridge when a case is
bound) or falls back to the in-memory backend if no case is active.
"""

from __future__ import annotations

import csv
import os
from typing import Any, Dict, Iterable, List, Mapping, Protocol


class AppDB:
    def __init__(self):
        # --- TAG SYSTEM ---
        self.tags: Dict[str, object] = {}  # tag_name -> Tag

        # --- SESSION ---
        self.sessions: Dict[str, object] = {}  # session_id -> SimulationSession

        # --- HISTORIAN ---
        self.timeseries: List[Dict] = []  # list of dict (time-series data)


# global singleton
appdb = AppDB()


# Per-active-case timeseries parameters. Set by the bridge when a case
# is bound (or by tests that exercise a single case in isolation).
# When empty, the in-memory backend is used.
_ACTIVE_CASE_PARAMS: Dict[str, Any] = {}


def set_active_case_config(simulation_params: Mapping[str, Any] | None) -> None:
    """Update the active case's timeseries parameters.

    Called by :class:`gateway.bridge_class.Bridge.bind_profile`
    whenever a case is loaded. Pass ``None`` (or an empty mapping) to
    clear and fall back to the in-memory backend.

    The case-name → params mapping is stored globally because
    ``appdb`` is a process-wide singleton; in practice only one case
    runs at a time per process, so a single slot is sufficient.
    """
    global _ACTIVE_CASE_PARAMS
    if simulation_params is None:
        _ACTIVE_CASE_PARAMS = {}
    else:
        _ACTIVE_CASE_PARAMS = dict(simulation_params)


def _current_simulation_params() -> Mapping[str, Any]:
    """Return the active case's ``SIMULATION_PARAMS`` (or empty)."""
    return _ACTIVE_CASE_PARAMS


def log_timeseries(appdb, plant_id, tag_name, t, value):
    record = {"plant_id": plant_id, "tag": tag_name, "t": t, "value": value}
    try:
        _get_backend().append(record)
    except Exception:
        # Backend unavailable — write to in-memory list only.
        try:
            appdb.timeseries.append(record)
        except Exception:
            pass
        return
    # Mirror to in-memory list for tests/compat.
    try:
        appdb.timeseries.append(record)
    except Exception:
        pass


class _CsvTimeseriesBackend:
    def __init__(self, path: str):
        self.path = path
        # ensure directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # write header if file empty
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            with open(path, "a", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(["plant_id", "tag", "t", "value"])

    def append(self, record: dict) -> None:
        with open(self.path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    record.get("plant_id"),
                    record.get("tag"),
                    record.get("t"),
                    record.get("value"),
                ]
            )

    def extend(self, records: Iterable[dict]) -> None:
        with open(self.path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            for r in records:
                writer.writerow(
                    [r.get("plant_id"), r.get("tag"), r.get("t"), r.get("value")]
                )


class _MemoryBackend:
    def append(self, record: dict) -> None:
        # no-op; memory is in appdb.timeseries
        pass

    def extend(self, records: Iterable[dict]) -> None:
        # no-op; memory is in appdb.timeseries
        pass


class _TimeseriesBackend(Protocol):
    def extend(self, records: Iterable[dict]) -> None: ...

    def append(self, record: dict) -> None: ...


_CSV_BACKEND_CACHE: dict[str, _TimeseriesBackend] = {}


def _get_backend() -> _TimeseriesBackend:
    params = _current_simulation_params()
    backend_type = str(params.get("timeseries_backend", "memory")).lower()
    if backend_type == "csv":
        path = params.get("timeseries_csv_path", "./timeseries.csv")
        # reuse cached backend per path
        if path not in _CSV_BACKEND_CACHE:
            try:
                _CSV_BACKEND_CACHE[path] = _CsvTimeseriesBackend(path)
            except Exception:
                _CSV_BACKEND_CACHE[path] = _MemoryBackend()
        return _CSV_BACKEND_CACHE[path]
    return _MemoryBackend()


def append_timeseries_records(appdb, records: Iterable[dict]):
    """Append an iterable of timeseries records using the configured backend.

    On success: writes via backend and mirrors to ``appdb.timeseries``.
    On failure: writes to ``appdb.timeseries`` only (no double-write).
    """
    recs = list(records)
    backend_ok = False
    try:
        _get_backend().extend(recs)
        backend_ok = True
    except Exception:
        pass

    if not backend_ok:
        # Backend failed — write to in-memory list only.
        for r in recs:
            try:
                appdb.timeseries.append(r)
            except Exception:
                continue
        return

    # Mirror into in-memory list for tests/compat.
    try:
        appdb.timeseries.extend(recs)
    except Exception:
        for r in recs:
            try:
                appdb.timeseries.append(r)
            except Exception:
                continue


def add_tag(appdb, tag):
    appdb.tags[tag.name] = tag
