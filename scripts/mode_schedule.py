# engine_root/scripts/mode_schedule.py

import json
import logging
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path so local packages (core, engine, gateway, models) import correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.appdb import appdb
from engine.runtime.simulation_engine import SimulationEngine, SimulationPhase


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        force=True,
    )


CONFIG_PATH = Path(__file__).with_name("mode_schedule.json")


def load_schedule_config(config_path: Path = CONFIG_PATH) -> list[SimulationPhase]:
    with config_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    phases = []
    for item in payload.get("phases", []):
        if "duration" in item:
            duration = float(item.get("duration", 0.0))
            duration_unit = item.get("duration_unit")
        else:
            duration = float(item.get("duration_min", 0.0))
            duration_unit = "minutes"

        phases.append(
            SimulationPhase(
                mode=item.get("mode"),
                duration_min=duration if duration_unit == "minutes" else 0.0,
                duration=duration,
                duration_unit=duration_unit,
                external_inputs=item.get("external_inputs", {}) or {},
            )
        )

    return phases


print_fields = [
    "OUT:STHR.T",
    "OUT:STHR.Ts",
    "OUT:TT-100.C",
]


def run_schedule(schedule):
    SimulationEngine(appdb=appdb, print_fields=print_fields).run_phases(schedule)


if __name__ == "__main__":
    configure_logging()
    run_schedule(load_schedule_config())
