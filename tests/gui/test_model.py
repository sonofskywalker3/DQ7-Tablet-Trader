import re
import subprocess
import sys
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

from dq7tt.bank import BANK_EXTENSION
from dq7tt.savefile import SlotRole
from dq7tt.session import Target
from dq7tt.tablets import TabletKind
from dq7tt_gui.viewmodels import Notice, NoticeKind, PaneSide

ROOT = Path(__file__).resolve().parents[2]
FLET_IMPORT = re.compile(r"^\s*(import\s+flet\b|from\s+flet\b)", re.MULTILINE)
GUI_IMPORT = re.compile(r"^\s*(import\s+dq7tt_gui\b|from\s+dq7tt_gui\b)", re.MULTILINE)
LEFT, RIGHT = PaneSide.LEFT, PaneSide.RIGHT
ODDNA = "Mount Oddna"
US_QUICK_ODDNA = 4
US_LABEL = "Checkpoint backup 20261020-101500 (US)"
PAL_LABEL = "Checkpoint backup 20261019-090000 (US)"


def bank_files(tmp_path: Path, folder: str = "") -> list[str]:
    root = tmp_path / "app" / "data" / "bank" / folder
    return sorted(p.stem for p in root.glob(f"*{BANK_EXTENSION}"))


def row_names(view: object) -> list[str]:
    return [r.name for r in view.rows]


def test_model_never_imports_flet() -> None:
    model_files = [
        *(ROOT / "dq7tt_gui").rglob("model*.py"),
        *(ROOT / "dq7tt_gui").rglob("viewmodels.py"),
    ]
    assert len(model_files) >= 3
    for source in [*(ROOT / "dq7tt").rglob("*.py"), *model_files]:
        text = source.read_text(encoding="utf-8")
        assert not FLET_IMPORT.search(text), source.name
    for source in (ROOT / "dq7tt").rglob("*.py"):
        assert not GUI_IMPORT.search(source.read_text(encoding="utf-8")), source.name
    loaded = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, dq7tt_gui.model, dq7tt_gui.viewmodels; "
            "print(any(m == 'flet' or m.startswith('flet.') for m in sys.modules))",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert loaded.stdout.strip() == "False"


def test_empty_model(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    left = model.left()
    assert left.title == "No save open"
    assert left.empty_text == "Open a save, or use Find saves to look for one."
    assert left.rows == () and left.log_chips == () and left.count_text == ""
    right = model.right()
    assert right.title == "Bank"
    assert [(c.name, c.label, c.count, c.active) for c in right.folder_chips] == [
        ("", "Unsorted", 0, True)
    ]
    assert right.empty_text == "This bank folder is empty."
    bar = model.toolbar()
    assert (bar.undo_label, bar.redo_label, bar.can_write) == (None, None, False)
    assert bar.write_label == "Write changes"
    action = model.action_bar()
    assert action.selected_count == 0 and action.quick_copy_label is None
    assert not (action.can_move or action.can_reset or action.can_remove)
    assert not model.has_unwritten()


def test_log_destinations_say_who_how_long_how_full_and_when_full(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    assert notices(model.open_left(us_save(tmp_path))) == []
    model.toggle_row(LEFT, 0)
    chips = {c.label: c for c in model.left().log_chips}
    dests = {d.label: d for d in model.destinations()}
    assert dests["Log 3"].detail == "Auster, 135h, 23/24" and not dests["Log 3"].full
    assert dests["Log 2"].full and dests["Log 2"].detail.endswith("24/24, full")
    for label in ("Log 2", "Log 3", "Quick save"):
        chip = chips[label]
        assert dests[label].detail.startswith(f"{chip.detail}, {chip.fill}")
    assert all(not d.detail and not d.full for d in dests.values() if d.kind == "bank")


def test_pane_view_after_open(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    assert notices(model.open_left(us_save(tmp_path))) == []
    left = model.left()
    assert left.title == US_LABEL
    assert left.subtitle == "Adventure log 1"
    assert [c.label for c in left.log_chips] == ["Log 1", "Log 2", "Log 3", "Quick save"]
    assert [c.role for c in left.log_chips][-1] is SlotRole.QUICK_SAVE
    assert [c.muted for c in left.log_chips] == [False, False, False, True]
    assert [c.active for c in left.log_chips] == [True, False, False, False]
    assert left.log_chips[0].detail == "Auster, 319h"
    assert left.log_chips[2].detail == "Auster, 135h"
    assert [c.fill for c in left.log_chips][:3] == ["24/24", "24/24", "23/24"]
    assert left.count_text == "24 of 24"
    assert left.empty_text is None
    first = left.rows[0]
    assert (first.index, first.name, first.kind, first.clears) == (0, ODDNA, TabletKind.DLC, 0)
    assert (first.selected, first.key) == (False, "left:0")
    assert left.rows[1].kind is TabletKind.STORY
    assert model.pick_log(LEFT, SlotRole.LOG_3) == []
    assert model.left().count_text == "23 of 24"
    assert model.left().log_chips[2].active
    assert model.pick_log(LEFT, SlotRole.QUICK_SAVE) == []
    assert model.left().subtitle == "Quick save (suspended game)"
    assert model.left().rows[US_QUICK_ODDNA].clears == 1


def test_selection_and_action_bar_labels(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.toggle_row(LEFT, 0)
    model.toggle_row(LEFT, 2)
    bar = model.action_bar()
    assert bar.selected_count == 2 and bar.summary == "2 tablets selected"
    assert bar.quick_copy_label == "Copy to bank folder Unsorted"
    assert bar.can_move and bar.can_remove and not bar.can_reset
    assert [r.index for r in model.left().rows if r.selected] == [0, 2]
    model.toggle_row(LEFT, 0)
    assert model.action_bar().summary == "1 tablet selected"
    assert notices(model.open_right(pal_save(tmp_path))) == []
    assert model.right().title == PAL_LABEL
    assert model.action_bar().quick_copy_label == "Copy to Log 1"
    model.pick_log(RIGHT, SlotRole.LOG_2)
    assert model.action_bar().quick_copy_label == "Copy to Log 2"
    labels = [d.label for d in model.destinations()]
    assert labels == [
        "Log 2",
        "Log 3",
        "Quick save",
        "Log 1 in the other save",
        "Log 2 in the other save",
        "Log 3 in the other save",
        "Quick save in the other save",
        "bank folder Unsorted",
    ]
    model.toggle_row(RIGHT, 3)
    assert [r.index for r in model.left().rows if r.selected] == []
    assert [r.key for r in model.right().rows if r.selected] == ["right:3"]
    assert model.action_bar().quick_copy_label == "Copy to Log 1"
    model.select_all(LEFT)
    assert model.action_bar().selected_count == 24
    model.clear_selection()
    assert model.action_bar().selected_count == 0
    model.pick_log(LEFT, SlotRole.QUICK_SAVE)
    model.toggle_row(LEFT, US_QUICK_ODDNA)
    assert model.action_bar().can_reset


def test_copy_to_bank_creates_files(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.toggle_row(LEFT, 0)
    model.toggle_row(LEFT, 4)
    result = model.quick_copy()
    assert kinds(result) == [NoticeKind.INFO]
    assert notices(result)[0].text == "Copied 2 tablets to bank folder Unsorted."
    assert bank_files(tmp_path) == [ODDNA, "To the Victor the Spoils!"]
    right = model.right()
    assert row_names(right) == [ODDNA, "To the Victor the Spoils!"]
    assert right.count_text == "2 tablets"
    assert right.folder_chips[0].count == 2
    assert model.action_bar().selected_count == 0
    assert not model.has_unwritten()
    model.toggle_row(LEFT, 0)
    model.toggle_row(LEFT, 5)
    again = model.quick_copy()
    assert notices(again)[0].text == "Copied Whipping Up a Frenzy to bank folder Unsorted."
    assert errors(again) == ["Mount Oddna is already in bank folder Unsorted."]
    assert len(bank_files(tmp_path)) == 3


def test_new_folder_and_import_all(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    assert model.new_folder("Rares") == []
    assert [(c.label, c.active) for c in model.right().folder_chips] == [
        ("Unsorted", False),
        ("Rares", True),
    ]
    model.pick_log(LEFT, SlotRole.LOG_3)
    result = model.import_all_to_bank(LEFT)
    assert notices(result)[0].text == "Copied 23 tablets to bank folder Rares."
    assert len(bank_files(tmp_path, "Rares")) == 23
    again = model.import_all_to_bank(LEFT)
    assert notices(again)[0].text == "Every tablet of this log is already in bank folder Rares."
    assert errors(model.new_folder("Rares")) == ["A bank folder called Rares already exists."]
    assert errors(model.new_folder("a/b")) == ["Folder names can't contain / \\ : * ? \" < > |."]
    assert model.pick_folder("") == []
    assert model.right().folder_chips[0].active
    assert errors(model.pick_folder("Missing")) == ["There is no bank folder named Missing."]


def test_move_within_one_save(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(pal_save(tmp_path))
    model.toggle_row(LEFT, 0)
    dest = next(d for d in model.destinations() if d.label == "Log 3")
    assert dest.kind == "log"
    assert notices(model.move_selected(dest)) == []
    assert model.left().count_text == "23 of 24"
    model.pick_log(LEFT, SlotRole.LOG_3)
    assert model.left().rows[0].name == "Ocean's Overlord"
    assert model.left().count_text == "10 of 24"
    assert model.toolbar().undo_label == (
        "Move Ocean's Overlord from adventure log 1 to adventure log 3"
    )
    assert model.has_unwritten()


def test_copy_between_two_saves_keeps_clears(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.open_right(pal_save(tmp_path))
    model.pick_log(LEFT, SlotRole.QUICK_SAVE)
    model.pick_log(RIGHT, SlotRole.LOG_3)
    before = model.left()
    model.toggle_row(LEFT, US_QUICK_ODDNA)
    assert notices(model.quick_copy()) == []
    first = model.right().rows[0]
    assert (first.name, first.clears) == (ODDNA, 1)
    assert model.right().count_text == "10 of 24"
    assert model.left() == before
    assert model.toolbar().undo_label == "Copy Mount Oddna from the quick save to adventure log 3"


def test_failures_change_nothing(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(pal_save(tmp_path))
    model.pick_log(LEFT, SlotRole.LOG_3)
    model.open_right(us_save(tmp_path))
    model.toggle_row(LEFT, 0)
    model.toggle_row(LEFT, 1)
    before = snapshot(model)
    cap = model.quick_copy()
    assert kinds(cap) == [NoticeKind.ERROR]
    assert "24 of 24" in errors(cap)[0]
    assert snapshot(model) == before
    model.pick_log(RIGHT, SlotRole.LOG_3)
    model.clear_selection()
    model.toggle_row(LEFT, 0)
    before = snapshot(model)
    dup = model.quick_copy()
    assert errors(dup) == ["That tablet is already in this adventure log."]
    assert snapshot(model) == before
    for result in (
        model.toggle_row(LEFT, 99),
        model.pick_log(LEFT, SlotRole.UNKNOWN),
        model.open_left(tmp_path / "nowhere"),
        model.write(LEFT),
        model.undo(),
        model.redo(),
        model.reorder(LEFT, 50, 0),
        model.drop(LEFT, [70], RIGHT, 0),
        model.copy_selected(
            next(d for d in model.destinations() if d.label == "Log 3 in the other save")
        ),
        model.new_folder("bad/name"),
    ):
        assert kinds(result) == [NoticeKind.ERROR], result
        assert "outside" not in errors(result)[0]
        assert snapshot(model) == before
    model.show_bank()
    model.close_left()
    before = snapshot(model)
    for result in (
        model.pick_log(LEFT, SlotRole.LOG_1),
        model.toggle_row(LEFT, 0),
        model.write(LEFT),
        model.import_all_to_bank(LEFT),
        model.put_into_azahar(LEFT),
    ):
        assert errors(result) == ["Open a save first."]
        assert snapshot(model) == before


def test_bank_to_save_and_bank_folders(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.toggle_row(LEFT, 0)
    model.toggle_row(LEFT, 4)
    model.quick_copy()
    model.open_left(pal_save(tmp_path))
    model.pick_log(LEFT, SlotRole.LOG_3)
    model.select_all(RIGHT)
    assert model.action_bar().quick_copy_label == "Copy to Log 3"
    assert not model.action_bar().can_reset
    assert notices(model.quick_copy()) == []
    assert row_names(model.left())[:2] == [ODDNA, "To the Victor the Spoils!"]
    assert model.toolbar().undo_label == "Add 2 tablets to adventure log 3"
    model.new_folder("Keep")
    model.pick_folder("")
    model.toggle_row(RIGHT, 0)
    keep = next(d for d in model.destinations() if d.label == "bank folder Keep")
    assert "bank folder Unsorted" not in [d.label for d in model.destinations()]
    assert notices(model.copy_selected(keep))[0].text == "Copied Mount Oddna to bank folder Keep."
    model.toggle_row(RIGHT, 1)
    assert notices(model.move_selected(keep))[0].text == (
        "Moved To the Victor the Spoils! to bank folder Keep."
    )
    assert bank_files(tmp_path) == [ODDNA]
    assert bank_files(tmp_path, "Keep") == [ODDNA, "To the Victor the Spoils!"]


def test_move_to_bank_and_back(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(pal_save(tmp_path))
    model.pick_log(LEFT, SlotRole.LOG_3)
    model.toggle_row(LEFT, 0)
    bank = next(d for d in model.destinations() if d.kind == "bank")
    assert (
        notices(model.move_selected(bank))[0].text == "Moved Feral Forest to bank folder Unsorted."
    )
    assert model.left().count_text == "8 of 24"
    assert bank_files(tmp_path) == ["Feral Forest"]
    assert model.toolbar().undo_label == "Remove Feral Forest from adventure log 3"
    model.toggle_row(RIGHT, 0)
    bar = model.action_bar()
    assert (bar.quick_copy_label, bar.can_move) == ("Copy to Log 3", False)
    log3 = next(d for d in model.destinations() if d.label == "Log 3")
    assert log3.target == Target(log3.target.source_id, SlotRole.LOG_3)
    assert errors(model.move_selected(log3))  # leaving the bank is a copy, never a move
    assert notices(model.copy_selected(log3)) == []
    assert model.left().count_text == "9 of 24"
    assert bank_files(tmp_path) == ["Feral Forest"]
    model.undo()
    assert notices(model.drop(RIGHT, [0], LEFT, 99)) == []
    assert model.left().rows[-1].name == "Feral Forest"
    assert bank_files(tmp_path) == ["Feral Forest"]


def test_reset_selected(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.pick_log(LEFT, SlotRole.LOG_1)
    model.select_all(LEFT)
    result = model.reset_selected()
    assert notices(result)[0].text == (
        "Clear count reset. One-time rewards for the first clear do not come back."
    )
    assert all(r.clears == 0 for r in model.left().rows)
    assert model.toolbar().undo_label == "Reset clear count of Feline Forest in adventure log 1"
    model.toggle_row(LEFT, 0)
    assert errors(model.reset_selected()) == ["That tablet has not been cleared."]


def test_remove_several_is_one_undo_step(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.pick_log(LEFT, SlotRole.LOG_2)
    for index in (0, 1, 2):
        model.toggle_row(LEFT, index)
    assert notices(model.remove_selected()) == []
    assert model.left().count_text == "21 of 24"
    assert model.toolbar().undo_label == "Remove 3 tablets from adventure log 2"
    assert model.action_bar().selected_count == 0


def test_undo_redo_labels(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.toggle_row(LEFT, 0)
    model.remove_selected()
    label = "Remove Mount Oddna from adventure log 1"
    assert model.toolbar().undo_label == label
    model.toggle_row(LEFT, 0)
    assert model.undo() == [Notice(NoticeKind.INFO, f"Undone: {label}")]
    assert model.action_bar().selected_count == 0
    bar = model.toolbar()
    assert (bar.undo_label, bar.redo_label) == (None, label)
    assert model.left().rows[0].name == ODDNA
    assert notices(model.redo())[0].text == f"Redone: {label}"
    assert model.left().rows[0].name != ODDNA


def test_drop_semantics(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    names = row_names(model.left())
    assert notices(model.drop(LEFT, [0], LEFT, 2)) == []
    assert row_names(model.left())[:3] == [names[1], names[2], names[0]]
    assert model.toolbar().undo_label == "Reorder Mount Oddna in adventure log 1"
    assert notices(model.drop(LEFT, [0, 1], RIGHT, 0))[0].text == (
        "Copied 2 tablets to bank folder Unsorted."
    )
    assert model.right().count_text == "2 tablets"
    assert model.drop(RIGHT, [0], RIGHT, 1) == []
    model.open_right(pal_save(tmp_path))
    model.pick_log(RIGHT, SlotRole.LOG_3)
    assert notices(model.drop(LEFT, [4], RIGHT, 1)) == []
    assert row_names(model.right())[1] == names[4]
    assert model.right().count_text == "10 of 24"
    assert row_names(model.left()) == [names[1], names[2], names[0], *names[3:]]
    assert errors(model.drop(LEFT, [0, 1], LEFT, 3)) == ["Drag one tablet at a time to reorder."]
