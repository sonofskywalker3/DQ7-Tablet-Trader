"""Smaller model fixes: replacing with two saves open, confirm wording, plain messages."""

from pathlib import Path

import pytest
from model_helpers import (
    US_SET,
    confirm,
    errors,
    fill,
    new_model,
    notices,
    pal_save,
    snapshot,
    us_save,
)

import dq7tt.session_core
import dq7tt_gui.model_files
from dq7tt.errors import CorruptSaveError, SessionError
from dq7tt.savefile import SlotRole
from dq7tt.session_ops import load_saves
from dq7tt.sources import SaveSource
from dq7tt_gui.viewmodels import NoticeKind, PaneSide

LEFT, RIGHT = PaneSide.LEFT, PaneSide.RIGHT
THIRD_PATH = "sd/3ds/Checkpoint/saves/0x18F00 DQ7/20261001-000000"
BROKEN = "This save is damaged."


def test_a_save_that_will_not_load_leaves_the_old_one_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = new_model(tmp_path)
    model.open_left(pal_save(tmp_path))
    model.open_right(us_save(tmp_path))
    model.pick_log(LEFT, SlotRole.LOG_3)
    third = fill(tmp_path / THIRD_PATH, US_SET)

    def picky(source: SaveSource) -> object:
        if source.save_dir == third:
            raise CorruptSaveError(BROKEN)
        return load_saves(source)

    monkeypatch.setattr(dq7tt_gui.model_files, "load_saves", picky)
    monkeypatch.setattr(dq7tt.session_core, "load_saves", picky)
    closed: list[int] = []
    real_close = model._session.close

    def close(sid: int, force: bool = False) -> None:
        closed.append(sid)
        real_close(sid, force)

    monkeypatch.setattr(model._session, "close", close)
    before = snapshot(model)
    assert errors(model.open_left(third)) == [BROKEN]
    assert closed == []  # the old save was never closed and reopened
    assert snapshot(model) == before


def test_removing_a_special_tablet_asks_in_the_future_tense(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.pick_log(LEFT, SlotRole.LOG_3)
    model.toggle_row(LEFT, 17)
    ask = confirm(model.remove_selected())
    assert ask.text == (
        "Woebegone Cave will be removed. It came from the story or a Haven resident "
        "and may be hard to get back."
    )
    assert notices(ask.on_ok()) == []


def test_a_move_to_the_bank_that_cannot_leave_the_log_says_so_plainly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.toggle_row(LEFT, 0)

    def refuse(*_args: object) -> None:
        raise SessionError("Errno 13 raw detail")

    monkeypatch.setattr(model._session, "remove_many", refuse)
    bank = next(d for d in model.destinations() if d.kind == "bank")
    (note,) = notices(model.move_selected(bank))
    assert note.kind is NoticeKind.WARNING
    assert note.text == (
        "Copied Mount Oddna to bank folder Unsorted, but could not take it out of the log. "
        "It is still in adventure log 1."
    )
