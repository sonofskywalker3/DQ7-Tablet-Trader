import pytest

from dq7tt.errors import SessionError
from dq7tt.history import History


def test_push_undo_redo_sequence() -> None:
    h = History("a")
    h.push("b", "to b")
    h.push("c", "to c")
    assert h.current == "c"
    assert h.undo() == "b"
    assert h.undo() == "a"
    assert h.redo() == "b"
    assert h.redo() == "c"
    assert h.current == "c"


def test_push_clears_redo() -> None:
    h = History(1)
    h.push(2, "two")
    h.undo()
    assert h.can_redo
    h.push(3, "three")
    assert not h.can_redo
    assert h.redo_label is None
    assert h.undo() == 1


def test_limit_drops_oldest() -> None:
    h = History(0, limit=2)
    for n in (1, 2, 3, 4):
        h.push(n, f"to {n}")
    assert h.undo() == 3
    assert h.undo() == 2
    assert not h.can_undo
    with pytest.raises(SessionError):
        h.undo()


def test_labels() -> None:
    h = History("a")
    assert h.undo_label is None
    assert h.redo_label is None
    h.push("b", "first")
    h.push("c", "second")
    assert h.undo_label == "second"
    h.undo()
    assert h.undo_label == "first"
    assert h.redo_label == "second"
    h.undo()
    assert h.undo_label is None
    assert h.redo_label == "first"


def test_errors_when_empty() -> None:
    h = History("a")
    assert not h.can_undo
    assert not h.can_redo
    with pytest.raises(SessionError, match="Nothing to undo."):
        h.undo()
    with pytest.raises(SessionError, match="Nothing to redo."):
        h.redo()


def test_limit_must_be_positive() -> None:
    with pytest.raises(SessionError, match="at least 1"):
        History("a", limit=0)


def test_rewrite_maps_every_state_and_merges_repeats() -> None:
    h = History({"a": 0, "b": 0})
    h.push({"a": 1, "b": 0}, "a to 1")
    h.push({"a": 1, "b": 1}, "b to 1")
    h.push({"a": 2, "b": 1}, "a to 2")
    h.undo()
    h.rewrite(lambda s: {"a": s["a"]})
    assert h.current == {"a": 1}
    assert h.undo_label == "a to 1"
    assert h.redo_label == "a to 2"
    assert h.undo() == {"a": 0}
    assert not h.can_undo
    assert h.redo() == {"a": 1}
    assert h.redo() == {"a": 2}
    assert not h.can_redo


def test_rewrite_to_one_state_leaves_nothing_to_undo() -> None:
    h = History(1)
    h.push(2, "two")
    h.push(3, "three")
    h.rewrite(lambda _: 0)
    assert h.current == 0
    assert not h.can_undo
    assert not h.can_redo
