from pathlib import Path

import pytest
from model_helpers import (
    errors,
    new_model,
    no_recycle_bin,  # noqa: F401 (an autouse fixture)
    notices,
    us_save,
)

from dq7tt.bank import BANK_EXTENSION, Bank
from dq7tt.errors import BankFileError, BankProblem
from dq7tt.savefile import SlotRole
from dq7tt_gui.model_text import (
    BAD_BANK_FILE,
    FOLDER_CHARS,
    FOLDER_FALLBACK,
    UNREADABLE_FILE,
    bank_problem,
)
from dq7tt_gui.viewmodels import Notice, NoticeKind, PaneSide

LEFT, RIGHT = PaneSide.LEFT, PaneSide.RIGHT
FAILING_CALL = 2


def failing_add(monkeypatch: pytest.MonkeyPatch, fail_on: int) -> None:
    """Make the `fail_on`-th Bank.add call refuse the file as damaged."""
    real = Bank.add
    calls = {"n": 0}

    def add(self: Bank, *args: object, **kwargs: object) -> Path:
        calls["n"] += 1
        if calls["n"] == fail_on:
            raise BankFileError("test.dq7tablet is not valid JSON", BankProblem.DAMAGED)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Bank, "add", add)


def bank_names(tmp_path: Path, folder: str = "") -> list[str]:
    root = tmp_path / "app" / "data" / "bank" / folder
    return sorted(p.stem for p in root.glob(f"*{BANK_EXTENSION}"))


def test_a_failure_mid_move_reports_and_keeps_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.pick_log(LEFT, SlotRole.LOG_2)
    names = [r.name for r in model.left().rows]
    for index in (0, 1, 2):
        model.toggle_row(LEFT, index)
    failing_add(monkeypatch, FAILING_CALL)
    bank = next(d for d in model.destinations() if d.kind == "bank")
    result = notices(model.move_selected(bank))
    assert result == [
        Notice(NoticeKind.INFO, "Moved 2 tablets to bank folder Unsorted."),
        Notice(NoticeKind.ERROR, f"{names[1]} was not copied to the bank. {BAD_BANK_FILE}"),
    ]
    assert bank_names(tmp_path) == sorted([names[0], names[2]])
    assert [r.name for r in model.left().rows] == [names[1], *names[3:]]
    assert model.toolbar().undo_label == "Remove 2 tablets from adventure log 2"


def test_a_failure_mid_copy_between_bank_folders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    for index in (0, 4, 5):
        model.toggle_row(LEFT, index)
    model.quick_copy()
    model.new_folder("Keep")
    model.pick_folder("")
    model.select_all(RIGHT)
    rows = [r.name for r in model.right().rows]
    failing_add(monkeypatch, FAILING_CALL)
    keep = next(d for d in model.destinations() if d.label == "bank folder Keep")
    result = notices(model.copy_selected(keep))
    assert result == [
        Notice(NoticeKind.INFO, "Copied 2 tablets to bank folder Keep."),
        Notice(NoticeKind.ERROR, f"{rows[1]} was not copied to the bank. {BAD_BANK_FILE}"),
    ]
    assert bank_names(tmp_path, "Keep") == sorted([rows[0], rows[2]])
    assert model.action_bar().selected_count == 0


def test_a_duplicate_never_reads_as_damaged(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    model.open_left(us_save(tmp_path))
    model.toggle_row(LEFT, 0)
    model.quick_copy()
    model.toggle_row(LEFT, 0)
    texts = errors(model.quick_copy())
    assert texts == ["Mount Oddna is already in bank folder Unsorted."]
    assert all("damaged" not in t for t in texts)


@pytest.mark.parametrize(
    ("name", "sentence"),
    [
        ("", "Type a name for the folder first."),
        (".hidden", "Folder names can't start with a dot."),
        ("a/b", FOLDER_CHARS),
        ("trailing.", "Folder names can't end with a space or a dot."),
        ("con", "con is a name Windows keeps for itself. Pick another name."),
    ],
)
def test_folder_name_sentences(tmp_path: Path, name: str, sentence: str) -> None:
    model = new_model(tmp_path)
    assert errors(model.new_folder(name)) == [sentence]


def test_bank_problem_sentences() -> None:
    def err(reason: BankProblem | None) -> BankFileError:
        return BankFileError("core text", reason)

    assert bank_problem(err(BankProblem.EXISTS), "Rares") == (
        "A bank folder called Rares already exists."
    )
    assert bank_problem(err(BankProblem.MISSING), "Old") == "There is no bank folder named Old."
    assert bank_problem(err(BankProblem.EXISTS)) == FOLDER_FALLBACK
    assert bank_problem(err(BankProblem.DAMAGED)) == BAD_BANK_FILE
    assert bank_problem(err(BankProblem.NOT_TABLET)) == BAD_BANK_FILE
    assert bank_problem(err(BankProblem.OUTSIDE)) == BAD_BANK_FILE
    assert bank_problem(err(BankProblem.UNREADABLE)) == UNREADABLE_FILE
    assert bank_problem(err(None)) == BAD_BANK_FILE
    assert bank_problem(err(None), "Odd") == FOLDER_FALLBACK
