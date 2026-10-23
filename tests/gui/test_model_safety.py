from pathlib import Path

from conftest import load_fixture
from model_helpers import (
    AZAHAR_PATH,
    JKSM_PATH,
    PAL_SET,
    US_SET,
    confirm,
    errors,
    fill,
    kinds,
    new_model,
    no_recycle_bin,  # noqa: F401 (an autouse fixture)
    notices,
    pal_save,
    snapshot,
    us_save,
)

from dq7tt.constants import SAVE_FILENAMES
from dq7tt.savefile import SaveFile, SlotRole
from dq7tt_gui.viewmodels import Notice, NoticeKind, PaneSide, RightMode

LEFT, RIGHT = PaneSide.LEFT, PaneSide.RIGHT
DISCARD_TEXT = "You have changes that are not written yet. Discard them?"
QUICK_TEXT = (
    "This is the quick save (a suspended game). Resuming it may overwrite or ignore changes "
    "made here. Edit it anyway?"
)
AZAHAR_TEXT = (
    "Put this into Azahar now? Close Azahar first. The current Azahar save is backed up "
    "before it is replaced."
)
WOEBEGONE = 17
YOUTH = 1
LOG3_COUNT = 9


def removed_text(name: str) -> str:
    return (
        f"{name} will be removed. It came from the story or a Haven resident "
        "and may be hard to get back."
    )


def story_text(name: str) -> str:
    return (
        f"{name} is a story tablet. The story changes it causes live elsewhere "
        "in the save and are not copied."
    )


def edited_model(tmp_path: Path) -> object:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.toggle_row(LEFT, 0)
    model.remove_selected()
    assert model.has_unwritten()
    return model


# Review Focus 2: unwritten edits are only lost through "Discard".


def test_close_with_unwritten_edits_asks_first(tmp_path: Path) -> None:
    model = edited_model(tmp_path)
    before = snapshot(model)
    ask = confirm(model.close_left())
    assert (ask.text, ask.ok_label, ask.cancel_label) == (DISCARD_TEXT, "Discard", "Cancel")
    assert snapshot(model) == before
    assert notices(ask.on_ok()) == []
    assert model.left().title == "No save open"
    assert not model.has_unwritten()
    assert model.toolbar().undo_label is None


def test_open_over_unwritten_edits_asks_first(tmp_path: Path) -> None:
    model = edited_model(tmp_path)
    before = snapshot(model)
    other = pal_save(tmp_path)
    ask = confirm(model.open_left(other))
    assert ask.text == DISCARD_TEXT and ask.ok_label == "Discard"
    assert snapshot(model) == before
    assert notices(model.open_left(other, confirmed=True)) == []
    assert model.left().title == "Checkpoint backup 20261019-090000 (US)"
    assert not model.has_unwritten()


def test_close_right_and_open_right_ask_first(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(pal_save(tmp_path))
    model.open_right(us_save(tmp_path))
    model.toggle_row(RIGHT, 0)
    model.remove_selected()
    assert model.dirty_sides() == [RIGHT]
    before = snapshot(model)
    assert confirm(model.close_right()).text == DISCARD_TEXT
    assert confirm(model.open_right(tmp_path / "anything")).text == DISCARD_TEXT
    model.show_bank()
    assert model.right().title == "Bank"
    assert model.has_unwritten()
    assert confirm(model.close_right()).text == DISCARD_TEXT
    model.pick_log(RIGHT, SlotRole.LOG_1)
    assert snapshot(model) == before
    assert notices(confirm(model.close_right()).on_ok()) == []
    assert model.right().title == "Bank" and not model.has_unwritten()


def test_replacing_a_save_when_both_are_open(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(pal_save(tmp_path))
    model.open_right(us_save(tmp_path))
    model.pick_log(LEFT, SlotRole.LOG_3)
    before = snapshot(model)
    third = fill(tmp_path / "sd/3ds/Checkpoint/saves/0x18F00 DQ7/20261001-000000", US_SET)
    assert errors(model.open_left(tmp_path / "nowhere"))
    assert errors(model.open_left(tmp_path / "sd" / "3ds" / "Checkpoint" / "saves"))
    assert snapshot(model) == before
    assert notices(model.open_left(third)) == []
    assert model.left().title == "Checkpoint backup 20261001-000000 (EU)"
    assert model.right() == before[1]


def test_opening_the_other_sides_save_is_refused(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(pal_save(tmp_path))
    us = us_save(tmp_path)
    model.open_right(us)
    before = snapshot(model)
    assert errors(model.open_left(us)) == [
        "Checkpoint backup 20261020-101500 (US) is already open."
    ]
    assert snapshot(model) == before


# Review Focus 3: the quick save is collapsed and its first edit asks.


def test_quick_save_needs_one_confirm_per_session(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    assert model.left().log_chips[-1].muted
    assert not model.left().log_chips[-1].active
    model.pick_log(LEFT, SlotRole.QUICK_SAVE)
    model.toggle_row(LEFT, 0)
    before = snapshot(model)
    ask = confirm(model.remove_selected())
    assert ask.text == QUICK_TEXT
    assert (ask.title, ask.ok_label) == ("Edit the quick save?", "Edit anyway")
    assert snapshot(model) == before
    result = ask.on_ok()
    assert result == []  # the yes covered the quick save warning
    assert model.left().count_text == "23 of 24"
    model.toggle_row(LEFT, 0)
    assert notices(model.remove_selected()) == []
    assert model.left().count_text == "22 of 24"


def test_every_edit_kind_of_the_quick_save_asks(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.open_right(pal_save(tmp_path))
    model.pick_log(LEFT, SlotRole.QUICK_SAVE)
    model.pick_log(RIGHT, SlotRole.QUICK_SAVE)
    for action in (
        lambda: model.reorder(LEFT, 0, 1),
        lambda: model.drop(LEFT, [0], LEFT, 2),
        lambda: model.drop(LEFT, [0], RIGHT, 0),
    ):
        before = snapshot(model)
        assert confirm(action()).text == QUICK_TEXT
        assert snapshot(model) == before
    model.toggle_row(LEFT, 4)
    for action in (model.reset_selected, model.quick_copy):
        before = snapshot(model)
        assert confirm(action()).text == QUICK_TEXT
        assert snapshot(model) == before
    model.pick_log(LEFT, SlotRole.LOG_3)
    model.toggle_row(LEFT, 0)
    assert confirm(model.quick_copy()).text == QUICK_TEXT
    model.pick_log(RIGHT, SlotRole.LOG_3)
    model.clear_selection()
    model.toggle_row(LEFT, 1)
    assert notices(model.quick_copy()) == []


def test_a_file_with_only_the_quick_save_opens_on_it(tmp_path: Path) -> None:
    folder = tmp_path / "loose"
    folder.mkdir()
    (folder / SAVE_FILENAMES[0]).write_bytes(load_fixture(US_SET, 0))
    model = new_model(tmp_path)
    model.open_left(folder / SAVE_FILENAMES[0])
    assert [c.label for c in model.left().log_chips] == ["Quick save"]
    assert model.left().log_chips[0].active
    assert model.left().title == "File: save000.bin"


# Review Focus 4: special tablets.


def test_removing_a_resident_tablet_asks_with_the_core_text(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.pick_log(LEFT, SlotRole.LOG_3)
    model.toggle_row(LEFT, WOEBEGONE)
    before = snapshot(model)
    ask = confirm(model.remove_selected())
    assert ask.text == removed_text("Woebegone Cave")
    assert (ask.title, ask.ok_label) == ("Remove a special tablet?", "Remove")
    assert snapshot(model) == before
    assert notices(ask.on_ok()) == []
    assert model.left().count_text == "22 of 24"


def test_removing_story_tablets_lists_each(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    for index in (0, 1, 2):
        model.toggle_row(LEFT, index)
    ask = confirm(model.remove_selected())
    assert ask.text == "\n\n".join(
        [removed_text("The Youth of a Hero"), removed_text("Divine Recollections")]
    )
    assert notices(model.remove_selected(confirmed=True)) == []
    assert model.left().count_text == "21 of 24"


def test_moving_a_story_tablet_out_asks(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.toggle_row(LEFT, YOUTH)
    bank = next(d for d in model.destinations() if d.kind == "bank")
    ask = confirm(model.move_selected(bank))
    assert ask.text == removed_text("The Youth of a Hero")
    assert ask.ok_label == "Move"
    assert notices(ask.on_ok())[0].text == "Moved The Youth of a Hero to bank folder Unsorted."


def test_adding_a_story_tablet_asks(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.open_right(pal_save(tmp_path))
    model.pick_log(RIGHT, SlotRole.LOG_3)
    model.toggle_row(LEFT, YOUTH)
    before = snapshot(model)
    ask = confirm(model.quick_copy())
    assert ask.text == story_text("The Youth of a Hero")
    assert (ask.title, ask.ok_label) == ("Add a story tablet?", "Copy")
    assert snapshot(model) == before
    assert notices(ask.on_ok()) == []
    assert model.right().rows[0].name == "The Youth of a Hero"


def test_adding_a_story_tablet_from_the_bank_asks(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.toggle_row(LEFT, YOUTH)
    model.quick_copy()
    model.open_left(pal_save(tmp_path))
    model.pick_log(LEFT, SlotRole.LOG_3)
    model.toggle_row(RIGHT, 0)
    ask = confirm(model.quick_copy())
    assert ask.text == story_text("The Youth of a Hero")
    assert notices(ask.on_ok()) == []
    assert model.left().count_text == f"{LOG3_COUNT + 1} of 24"


def test_quick_and_special_reasons_share_one_confirm(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.pick_log(LEFT, SlotRole.QUICK_SAVE)
    model.toggle_row(LEFT, 18)
    ask = confirm(model.remove_selected())
    assert ask.text == "\n\n".join([QUICK_TEXT, removed_text("Woebegone Cave")])
    assert ask.title == "Edit the quick save?"
    assert ask.on_ok() == []


# Review Focus 5: where the output went.


def written_note(out: Path, tmp_path: Path) -> str:
    backups = tmp_path / "app" / "data" / "backups"
    return f"Wrote the edited save to {out}. Your original is untouched; a backup is in {backups}."


def only_new_folder(parent: Path, before: set[Path]) -> Path:
    (new,) = set(parent.iterdir()) - before
    return new


def test_write_checkpoint_says_where_it_went(tmp_path: Path) -> None:
    model = edited_model(tmp_path)
    parent = tmp_path / "sd/3ds/Checkpoint/saves/0x18EF0 DRAGON QUEST VII"
    existing = set(parent.iterdir())
    result = notices(model.write(LEFT))
    out = only_new_folder(parent, existing)
    assert result == [
        Notice(NoticeKind.INFO, written_note(out, tmp_path)),
        Notice(NoticeKind.INFO, "It appears as a new backup in Checkpoint's restore list."),
    ]
    assert not model.has_unwritten()
    assert model.toolbar().can_write is False
    assert errors(model.write(LEFT)) == ["There are no changes to write."]


def test_write_jksm_and_plain_folder(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    jksm = fill(tmp_path / JKSM_PATH, US_SET)
    model.open_left(jksm)
    plain = fill(tmp_path / "plain" / "saves", PAL_SET)
    model.open_right(plain)
    for side in (LEFT, RIGHT):
        model.toggle_row(side, 0)
        model.remove_selected()
    assert model.toolbar().write_label == "Write changes to both saves"
    assert model.toolbar().short_label == "Write both"
    assert model.dirty_sides() == [LEFT, RIGHT]
    existing = set(jksm.parent.iterdir())
    result = notices(model.write(LEFT))
    out = only_new_folder(jksm.parent, existing)
    assert result[1] == Notice(
        NoticeKind.INFO, "It appears as a new backup in JKSM's restore list."
    )
    assert result[0].text == written_note(out, tmp_path)
    existing = set(plain.parent.iterdir())
    result = notices(model.write(RIGHT))
    out = only_new_folder(plain.parent, existing)
    assert result == [Notice(NoticeKind.INFO, written_note(out, tmp_path))]


def test_write_azahar_offers_put_into_azahar(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    azahar = fill(tmp_path / AZAHAR_PATH, US_SET)
    model.open_left(azahar)
    model.pick_log(LEFT, SlotRole.LOG_3)
    model.toggle_row(LEFT, 0)
    model.remove_selected()
    old = (azahar / SAVE_FILENAMES[3]).read_bytes()
    offer = confirm(model.write(LEFT))
    assert offer.text == AZAHAR_TEXT
    assert (offer.ok_label, offer.cancel_label) == ("Put into Azahar", "Not now")
    edited_dir = next((tmp_path / "app" / "edited").iterdir())
    assert offer.notices == (Notice(NoticeKind.INFO, written_note(edited_dir, tmp_path)),)
    assert (azahar / SAVE_FILENAMES[3]).read_bytes() == old
    result = notices(offer.on_ok())
    assert kinds(result) == [NoticeKind.INFO]
    backups = list((tmp_path / "app" / "data" / "backups").glob("*Azahar*"))
    assert len(backups) == 2
    assert result[0].text.startswith("The edited save is now in Azahar. The save it replaced")
    put = SaveFile.load(azahar / SAVE_FILENAMES[3])
    assert put.received.count == 22
    assert model.left().count_text == "22 of 24"
    again = confirm(model.put_into_azahar(LEFT))
    assert again.text == AZAHAR_TEXT


def test_put_into_azahar_needs_an_azahar_save(tmp_path: Path) -> None:
    model = edited_model(tmp_path)
    model.write(LEFT)
    before = snapshot(model)
    assert errors(model.put_into_azahar(LEFT, confirmed=True)) == ["No open save came from Azahar."]
    assert snapshot(model) == before


def test_right_mode_switches(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_right(us_save(tmp_path))
    assert model.right_mode() is RightMode.SAVE
    model.show_bank()
    assert model.right_mode() is RightMode.BANK
    assert [c.active for c in model.right().log_chips] == [False] * 4
    model.pick_log(RIGHT, SlotRole.LOG_2)
    assert model.right_mode() is RightMode.SAVE
    assert model.right().subtitle == "Adventure log 2"
