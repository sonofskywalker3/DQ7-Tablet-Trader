"""Pane actions: Put into Azahar after a write, Bank all, and moves between bank folders."""

from pathlib import Path

from model_helpers import (
    AZAHAR_PATH,
    US_SET,
    confirm,
    errors,
    fill,
    new_model,
    no_recycle_bin,  # noqa: F401 (an autouse fixture)
    notices,
    pal_save,
    snapshot,
    us_save,
)

from dq7tt.savefile import SlotRole
from dq7tt_gui.model import AppModel
from dq7tt_gui.viewmodels import PaneSide

LEFT, RIGHT = PaneSide.LEFT, PaneSide.RIGHT
AZAHAR_TEXT = (
    "Put this into Azahar now? Close Azahar first. The current Azahar save is backed up "
    "before it is replaced."
)
BANK_MOVE_TO_LOG = (
    "Tablets in the bank are copied into an adventure log, never moved. Use Copy to... instead."
)


def remove_first(model: AppModel, side: PaneSide = LEFT) -> None:
    model.toggle_row(side, 0)
    model.remove_selected(confirmed=True)


def bank_names(model: AppModel) -> list[str]:
    return [r.name for r in model.right().rows]


# Put into Azahar stays on offer after "Not now"


def test_put_into_azahar_is_offered_on_a_written_clean_azahar_save(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(fill(tmp_path / AZAHAR_PATH, US_SET))
    assert not model.left().can_put_into_azahar
    model.pick_log(LEFT, SlotRole.LOG_3)
    remove_first(model)
    assert not model.left().can_put_into_azahar
    confirm(model.write(LEFT))  # the user picks "Not now": nothing else happens
    assert model.left().can_put_into_azahar
    offer = confirm(model.put_into_azahar(LEFT))
    assert (offer.text, offer.ok_label) == (AZAHAR_TEXT, "Put into Azahar")
    remove_first(model)
    assert not model.left().can_put_into_azahar
    model.undo()
    assert model.left().can_put_into_azahar


def test_put_into_azahar_is_not_offered_for_other_saves(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    remove_first(model)
    notices(model.write(LEFT))
    assert not model.left().can_put_into_azahar
    assert not model.right().can_put_into_azahar


# Bank all tablets in this log


def test_bank_all_is_offered_for_a_save_log_with_tablets(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    assert not model.left().can_bank_all
    model.open_left(pal_save(tmp_path))
    model.pick_log(LEFT, SlotRole.LOG_3)
    assert model.left().can_bank_all
    assert not model.right().can_bank_all  # the bank itself
    model.select_all(LEFT)
    model.remove_selected(confirmed=True)
    assert not model.left().can_bank_all  # an empty log
    model.undo()
    result = notices(model.import_all_to_bank(LEFT))
    assert result[0].text == "Copied 9 tablets to bank folder Unsorted."
    assert len(model.right().rows) == 9


# Moving between bank folders


def bank_with_two_folders(tmp_path: Path) -> AppModel:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.toggle_row(LEFT, 0)
    model.toggle_row(LEFT, 4)
    model.quick_copy()
    assert model.new_folder("Keep") == []
    assert model.pick_folder("") == []
    return model


def test_bank_selection_offers_move_only_with_another_folder(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.toggle_row(LEFT, 0)
    model.quick_copy()
    model.toggle_row(RIGHT, 0)
    assert not model.action_bar().can_move
    model.clear_selection()
    model.new_folder("Keep")
    model.pick_folder("")
    model.toggle_row(RIGHT, 0)
    assert model.action_bar().can_move


def test_bank_move_destinations_are_bank_folders_only(tmp_path: Path) -> None:
    model = bank_with_two_folders(tmp_path)
    model.toggle_row(RIGHT, 0)
    assert {d.kind for d in model.destinations()} == {"log", "bank"}
    moves = model.destinations(move=True)
    assert [d.label for d in moves] == ["bank folder Keep"]
    name = bank_names(model)[0]
    assert notices(model.move_selected(moves[0]))[0].text == f"Moved {name} to bank folder Keep."
    assert name not in bank_names(model)
    model.pick_folder("Keep")
    assert bank_names(model) == [name]


def test_a_save_selection_still_moves_anywhere(tmp_path: Path) -> None:
    model = bank_with_two_folders(tmp_path)
    model.open_right(pal_save(tmp_path))
    model.toggle_row(LEFT, 0)
    assert model.destinations(move=True) == model.destinations()
    assert model.action_bar().can_move


def test_moving_from_the_bank_into_a_log_is_refused_plainly(tmp_path: Path) -> None:
    model = bank_with_two_folders(tmp_path)
    model.toggle_row(RIGHT, 0)
    log = next(d for d in model.destinations() if d.kind == "log")
    before = snapshot(model)
    assert errors(model.move_selected(log)) == [BANK_MOVE_TO_LOG]
    assert snapshot(model) == before
    assert len(model.right().rows) == 2


def test_put_into_azahar_is_not_offered_again_until_the_next_write(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(fill(tmp_path / AZAHAR_PATH, US_SET))
    model.pick_log(LEFT, SlotRole.LOG_3)
    remove_first(model)
    confirm(model.write(LEFT))  # "Not now"
    notices(model.put_into_azahar(LEFT, confirmed=True))
    assert not model.left().can_put_into_azahar
    remove_first(model)
    model.undo()  # back to what is already in Azahar
    assert not model.left().can_put_into_azahar
    remove_first(model)
    confirm(model.write(LEFT))
    assert model.left().can_put_into_azahar
