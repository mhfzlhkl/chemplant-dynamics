"""Template example moved into tests/examples for documentation and examples.

This is the same minimal template session implementation used previously
under `cases/template` but relocated under `tests` as an example only.
"""

from typing import Callable, Mapping


class TemplateSimulationSession:
    def __init__(self, appdb, session_id: str = "template", Ts: float = 0.01):
        self.appdb = appdb
        self.session_id = session_id
        self.t: float = 0.0
        self.Ts: float = float(Ts)
        self.runner = None
        self.input_tags = {}
        self.state_tags = {}
        self.output_tags = {}
        self.last_inputs: dict[str, float] = {}
        self.last_states: dict[str, float] = {}
        self.last_outputs: dict[str, float] = {}
        self.X0 = None
        self.mode = "Template"
        self.time_unit = "minutes"

    def step(
        self, external_inputs: Mapping[str, float] | None = None
    ) -> Mapping[str, float]:
        inputs = dict(external_inputs) if external_inputs else {}
        self.last_inputs = inputs
        self.last_states = {"TEMPLATE.X": 0.0}
        self.last_outputs = {k: float(v) for k, v in inputs.items()} if inputs else {}
        self.t += self.Ts
        return dict(self.last_outputs)


def create_session(appdb) -> Callable[[], TemplateSimulationSession]:
    def factory() -> TemplateSimulationSession:
        return TemplateSimulationSession(appdb=appdb)

    return factory
