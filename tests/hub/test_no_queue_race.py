# tests/hub/test_no_queue_race.py

"""No-race property: ``drain_records`` is called once per tick.

In the legacy stack three independent consumers each called
``bridge.drain_records()`` on their own ``ui.timer`` — a destructive
queue, so the records were racing. The v2 hub is the SINGLE drain
point; this test pins that.
"""

from __future__ import annotations

from tests.hub.conftest import RecordingChild


def test_drain_records_called_exactly_once_per_tick(fake_bridge, hub) -> None:
    # Even with 4 subscribers, only the hub drains.
    for i in range(4):
        hub.subscribe(RecordingChild(f'c{i}'))
    assert fake_bridge.calls['drain_records'] == 0

    hub.tick_once()
    assert fake_bridge.calls['drain_records'] == 1

    hub.tick_once()
    assert fake_bridge.calls['drain_records'] == 2


def test_every_record_is_processed_no_loss(fake_bridge, hub) -> None:
    """No records get dropped, regardless of subscriber count.

    The legacy bug: a destructive ``Queue.get_nowait`` meant
    whichever consumer fired its 50 ms timer first stole the
    record; the others saw an empty queue. With ONE drain point
    and N subscribers each receiving the SAME snapshot, none can
    miss anything.
    """
    children = [RecordingChild(f'c{i}') for i in range(4)]
    for child in children:
        hub.subscribe(child)

    # Push 10 step records before the tick.
    for i in range(10):
        fake_bridge.emit_step(
            step_index=i, time_min=float(i) * 0.1,
            outputs={'STHR.T': 150.0 + i},
        )

    hub.tick_once()

    # Drain called once (records fetched in a batch).
    assert fake_bridge.calls['drain_records'] == 1
    # Every child saw ONE tick (the per-tick fan-out, not one per record).
    for child in children:
        assert len(child.ticks) == 1
    # The hub folded all 10 records into one snapshot — the final value
    # comes from the last record, i.e. 150 + 9 = 159.
    for child in children:
        _, snapshot, meta = child.ticks[0]
        assert snapshot['pv'] == 159.0
        assert meta.step_index == 9


def test_subscribe_during_dispatch_takes_effect_next_tick(
    fake_bridge, hub,
) -> None:
    """A child subscribed mid-iteration must NOT receive the current
    tick (the hub takes a tuple snapshot of subscribers under the
    lock before fanning out). Pins the iteration safety.
    """
    late = RecordingChild('late')

    class EarlyChild:
        def __init__(self) -> None:
            self.ticks: list = []

        def on_tick(self, delta_keys, snapshot, meta) -> None:
            self.ticks.append((delta_keys, snapshot, meta))
            # Subscribe mid-tick — must not deliver THIS tick to ``late``.
            hub.subscribe(late)

    early = EarlyChild()
    hub.subscribe(early)

    fake_bridge.emit_step(
        step_index=0, time_min=0.1, outputs={'STHR.T': 152.0},
    )
    hub.tick_once()

    assert len(early.ticks) == 1
    assert late.ticks == []   # not delivered this turn

    fake_bridge.emit_step(
        step_index=1, time_min=0.2, outputs={'STHR.T': 153.0},
    )
    hub.tick_once()
    assert len(late.ticks) == 1
