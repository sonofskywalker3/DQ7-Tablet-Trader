from pathlib import Path

from model_helpers import (
    errors,
    kinds,
    new_model,
    no_recycle_bin,  # noqa: F401 (an autouse fixture)
    notices,
    pal_save,
    snapshot,
    us_save,
)

from dq7tt.savefile import SlotRole
from dq7tt_gui.model import AppModel
from dq7tt_gui.viewmodels import Notice, NoticeKind, PaneSide

LEFT, RIGHT = PaneSide.LEFT, PaneSide.RIGHT
NOT_IN_LIST = "That tablet is not in this list."


def row_names(model: AppModel, side: PaneSide) -> list[str]:
    view = model.left() if side is LEFT else model.right()
    return [r.name for r in view.rows]


def selection_is_valid(model: AppModel) -> bool:
    """Every selected row exists in its pane (or nothing is selected)."""
    for view in (model.left(), model.right()):
        picked = [r.index for r in view.rows if r.selected]
        if any(i >= len(view.rows) for i in picked):
            return False
    return model.action_bar().selected_count == sum(
        r.selected for view in (model.left(), model.right()) for r in view.rows
    )


def test_drop_after_the_last_row_reorders_to_the_end(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.pick_log(LEFT, SlotRole.LOG_3)
    names = row_names(model, LEFT)
    count = len(names)
    assert notices(model.drop(LEFT, [0], LEFT, count)) == []
    assert row_names(model, LEFT) == [*names[1:], names[0]]
    assert notices(model.reorder(LEFT, 0, -5)) == []
    assert row_names(model, LEFT)[0] == names[1]


def test_reorder_from_a_bad_position_is_refused_plainly(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    before = snapshot(model)
    for result in (
        model.reorder(LEFT, 24, 0),
        model.reorder(LEFT, -1, 0),
        model.drop(LEFT, [30], LEFT, 0),
    ):
        assert errors(result) == [NOT_IN_LIST]
        assert snapshot(model) == before


def test_moving_to_a_bank_folder_that_has_it_keeps_it_in_the_log(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.toggle_row(LEFT, 0)
    model.quick_copy()
    model.toggle_row(LEFT, 0)
    model.toggle_row(LEFT, 4)
    bank = next(d for d in model.destinations() if d.kind == "bank")
    result = model.move_selected(bank)
    assert notices(result)[0].text == "Moved To the Victor the Spoils! to bank folder Unsorted."
    assert errors(result) == [
        "Mount Oddna is already in bank folder Unsorted, so it stayed in adventure log 1."
    ]
    assert row_names(model, LEFT)[0] == "Mount Oddna"
    assert model.left().count_text == "23 of 24"


def test_a_refused_change_shows_the_refusal_not_a_confirm(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(pal_save(tmp_path))
    model.pick_log(LEFT, SlotRole.LOG_3)
    model.open_right(us_save(tmp_path))
    model.pick_log(RIGHT, SlotRole.QUICK_SAVE)
    assert model.right().count_text == "24 of 24"
    model.toggle_row(LEFT, 0)
    before = snapshot(model)
    result = model.quick_copy()
    assert kinds(result) == [NoticeKind.ERROR]
    assert "24 of 24" in errors(result)[0]
    assert snapshot(model) == before
    model.clear_selection()
    model.pick_log(LEFT, SlotRole.LOG_2)
    model.toggle_row(LEFT, 0)
    assert kinds(model.reset_selected()) == [NoticeKind.ERROR]
    # The quick save on the right was never confirmed: a reset with nothing to reset is
    # refused straight away instead of asking about the quick save first.
    model.toggle_row(RIGHT, 0)
    before = snapshot(model)
    assert model.reset_selected() == [Notice(NoticeKind.ERROR, "That tablet has not been cleared.")]
    assert snapshot(model) == before


def test_selections_stay_valid_after_list_changes(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.open_right(pal_save(tmp_path))
    model.toggle_row(LEFT, 0)
    model.remove_selected()
    model.show_bank()
    steps = (
        lambda: model.import_all_to_bank(LEFT),
        model.undo,
        model.redo,
        lambda: model.reorder(LEFT, 0, 3),
        lambda: model.import_all_to_bank(LEFT),
    )
    for step in steps:
        model.select_all(RIGHT if model.right().rows else LEFT)
        assert kinds(step()) in ([], [NoticeKind.INFO])
        assert selection_is_valid(model)
        assert model.action_bar().selected_count == 0
    model.select_all(LEFT)
    model.write(LEFT)
    model.close_left()
    assert selection_is_valid(model) and model.action_bar().selected_count == 0
    model.pick_log(RIGHT, SlotRole.LOG_1)
    model.toggle_row(RIGHT, 3)
    model.close_right()
    assert model.action_bar().selected_count == 0


def test_scan_results(tmp_path: Path) -> None:
    us_save(tmp_path)
    pal_save(tmp_path)
    model = new_model(tmp_path)
    found = model.scan_results([tmp_path / "sd"])
    assert {s.label for s in found} == {
        "Checkpoint backup 20261020-101500 (US)",
        "Checkpoint backup 20261019-090000 (US)",
    }
    assert model.scan_results([tmp_path / "missing"]) == []
