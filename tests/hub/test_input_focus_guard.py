# tests/hub/test_input_focus_guard.py

"""Guard tests for the editable-while-running fix.

Pins two invariants:

1. The focus tracker installed by ``attach_focus_tracker`` flips
   ``_user_is_editing`` exactly when the underlying DOM focus/blur
   events fire — and it is idempotent.
2. The patched ``ControllerModal._set_field_value`` honours both:
   the user-editing guard (skip overwrite while typing) and the
   already-equal short-circuit (skip a no-op assignment).

The tests use a tiny ``FakeField`` stub — no NiceGUI / no DOM —
because the patched code paths only depend on ``.value`` and
``.on(event, callback)``.
"""

from __future__ import annotations

from typing import Any, Callable

from app.hub.input_focus_tracker import (
    attach_focus_tracker,
    is_user_editing,
)


# ── A tiny stub that mimics the surface of ``ui.number`` ────────────

class FakeField:
    """Stand-in for ``ui.number``.

    - ``value``: read/write attribute (initial: ``None``).
    - ``.on(event, callback)``: stores callbacks by event name so a
      test can trigger them with ``fire(event)``.
    """

    def __init__(self, value: Any = None) -> None:
        self.value: Any = value
        self._handlers: dict[str, list[Callable]] = {}

    def on(self, event: str, callback: Callable) -> 'FakeField':
        self._handlers.setdefault(event, []).append(callback)
        return self

    def fire(self, event: str) -> None:
        for cb in self._handlers.get(event, []):
            cb()


# ── attach_focus_tracker / is_user_editing ──────────────────────────

def test_is_user_editing_defaults_false_for_untracked_field() -> None:
    field = FakeField(value=150.0)
    assert is_user_editing(field) is False


def test_attach_focus_tracker_initialises_flag_to_false() -> None:
    field = FakeField(value=150.0)
    attach_focus_tracker(field)
    assert is_user_editing(field) is False


def test_focus_flips_flag_true_blur_flips_back_false() -> None:
    field = FakeField(value=150.0)
    attach_focus_tracker(field)

    field.fire('focus')
    assert is_user_editing(field) is True

    field.fire('blur')
    assert is_user_editing(field) is False


def test_attach_focus_tracker_is_idempotent() -> None:
    field = FakeField(value=150.0)
    attach_focus_tracker(field)
    attach_focus_tracker(field)
    attach_focus_tracker(field)

    # Each event should have exactly ONE handler — re-attaching is
    # a no-op, not a multiplier.
    assert len(field._handlers.get('focus', [])) == 1
    assert len(field._handlers.get('blur', [])) == 1

    # And the flag still behaves correctly.
    field.fire('focus')
    assert is_user_editing(field) is True


def test_attach_focus_tracker_handles_none_safely() -> None:
    # Should not raise; the modal sometimes carries Optional[ui.number].
    attach_focus_tracker(None)


def test_attach_focus_tracker_handles_field_without_on_method() -> None:
    class NoOnField:
        value: Any = 1.0

    field = NoOnField()
    attach_focus_tracker(field)
    # Wiring failed silently; the flag stays False.
    assert is_user_editing(field) is False


# ── ControllerModal._set_field_value (the patched method) ──────────
#
# We don't instantiate the full ControllerModal — its __init__ touches
# NiceGUI's ui.dialog / ui.card. Instead we bind the unbound method to
# a bare object and test it as a pure function over a FakeField.


def _set_field_value(field: Any, value: Any) -> None:
    """Mirror of the patched ``ControllerModal._set_field_value``.

    Kept here as a tiny re-implementation so the test stays a pure
    unit test (no NiceGUI ui.dialog imports). The body MUST match
    the patched method byte-for-byte; see
    ``app/pid/sthr/controller_modal.py`` _set_field_value.
    """
    from app.hub.children.modals.base import ControllerModal
    # Call the actual method via its descriptor — ControllerModal
    # never references self in _set_field_value's body so we can
    # pass any object as ``self``.
    return ControllerModal._set_field_value(  # type: ignore[arg-type]
        object(), field, value,
    )


def test_set_field_value_overwrites_when_not_focused() -> None:
    field = FakeField(value=150.0)
    attach_focus_tracker(field)
    # No focus event fired → not editing → overwrite allowed.
    _set_field_value(field, 175.0)
    assert field.value == 175.0


def test_set_field_value_skips_when_user_is_editing() -> None:
    field = FakeField(value=150.0)
    attach_focus_tracker(field)
    field.fire('focus')   # operator clicks into the field

    _set_field_value(field, 999.0)
    # The store said 999 but the operator was typing — skip.
    assert field.value == 150.0

    # When the operator blurs out, the next refresh writes through.
    field.fire('blur')
    _set_field_value(field, 999.0)
    assert field.value == 999.0


def test_set_field_value_skips_when_value_equals_current() -> None:
    field = FakeField(value=150.0)
    attach_focus_tracker(field)
    # Track .value mutations so we can assert "no write happened".
    writes: list[Any] = []

    class TrackingFakeField(FakeField):
        def __setattr__(self, name: str, value: Any) -> None:
            if name == 'value' and hasattr(self, 'value'):
                writes.append(value)
            super().__setattr__(name, value)

    tracking = TrackingFakeField(value=150.0)
    attach_focus_tracker(tracking)
    writes.clear()

    _set_field_value(tracking, 150.0)
    # No actual ``.value = ...`` write — values already match.
    assert writes == []
    assert tracking.value == 150.0


def test_set_field_value_writes_when_value_differs_numerically() -> None:
    field = FakeField(value=150.0)
    attach_focus_tracker(field)
    _set_field_value(field, 150.5)
    assert field.value == 150.5


def test_set_field_value_handles_field_none() -> None:
    # Must not raise — modal sometimes constructs without an OP input
    # (read-only indicators) so callers pass ``None``.
    _set_field_value(None, 1.0)


def test_set_field_value_handles_non_numeric_current_value() -> None:
    # If a non-numeric junk value somehow lands in the field, the
    # equality short-circuit must fall through to the write.
    field = FakeField(value='nan-string')
    attach_focus_tracker(field)
    _set_field_value(field, 150.0)
    assert field.value == 150.0
