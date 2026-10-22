import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import send2trash

from dq7tt.bank import BANK_EXTENSION, Bank, BankList, safe_file_stem
from dq7tt.database import TabletDatabase
from dq7tt.errors import BankFileError, BankProblem, DuplicateTabletError, SaveIOError
from dq7tt.savefile import SaveFile
from dq7tt.tablets import TabletKind, TabletRecord
from tests.conftest import FIXTURES

SELFMADE_BYTES = 0x34
CHANGE_OFFSET = 0x50


@pytest.fixture(scope="module")
def db() -> TabletDatabase:
    return TabletDatabase.load()


@pytest.fixture
def bank(tmp_path: Path) -> Bank:
    return Bank(tmp_path / "bank")


def pal_save() -> SaveFile:
    return SaveFile.load(FIXTURES / "pal_superkiefer" / "save003.bin")


def first_record() -> TabletRecord:
    return pal_save().received.live[0]


def variant(record: TabletRecord, offset: int = CHANGE_OFFSET) -> TabletRecord:
    """A record with one byte flipped, so it has the same name but another identity."""
    data = bytearray(record.raw)
    data[offset] ^= 0xFF
    return TabletRecord(bytes(data))


class SameNameDb:
    """Names every record alike, to force file name collisions."""

    def lookup(self, record: TabletRecord) -> SimpleNamespace:
        return SimpleNamespace(name_en="Same", kind=TabletKind.DLC)


def add_one(bank: Bank, db: TabletDatabase, folder: str = "") -> Path:
    return bank.add(first_record(), folder, db, "note", "PAL", True)


def payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_payload(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_add_read_round_trip(bank: Bank, db: TabletDatabase) -> None:
    record = first_record()
    path = bank.add(record, "", db, "from my save", "PAL", True)
    assert path.suffix == BANK_EXTENSION
    tablet = bank.read(path)
    assert tablet.path == path
    assert tablet.list_kind is BankList.RECEIVED
    assert tablet.record_raw == record.raw
    assert tablet.source_note == "from my save"
    assert tablet.region == "PAL"
    assert tablet.from_real_save is True
    assert tablet.clear_count == record.clear_count
    assert path.stem == tablet.name


def test_file_format_is_exact(bank: Bank, db: TabletDatabase) -> None:
    record = first_record()
    data = payload(bank.add(record, "", db, "n", "US", False))
    assert list(data) == [
        "format",
        "list",
        "layout",
        "record_hex",
        "name",
        "kind",
        "clear_count",
        "source",
        "region",
        "from_real_save",
    ]
    assert data["format"] == 1
    assert data["list"] == "received"
    assert data["layout"] == "western"
    assert data["record_hex"] == record.raw.hex()
    assert data["kind"] in {k.value for k in TabletKind}
    assert data["source"] == "n"
    assert data["from_real_save"] is False


def test_collision_suffix(bank: Bank, db: TabletDatabase) -> None:
    record = first_record()
    same = SameNameDb()
    a = bank.add(record, "", same, "n", "PAL", True)  # type: ignore[arg-type]
    b = bank.add(variant(record), "", same, "n", "PAL", True)  # type: ignore[arg-type]
    c = bank.add(variant(record, CHANGE_OFFSET + 1), "", same, "n", "PAL", True)  # type: ignore[arg-type]
    assert b.stem == f"{a.stem} (2)"
    assert c.stem == f"{a.stem} (3)"


def test_duplicate_refused_even_if_cleared(bank: Bank, db: TabletDatabase) -> None:
    record = first_record()
    bank.add(record, "", db, "n", "PAL", True)
    with pytest.raises(DuplicateTabletError):
        bank.add(record.with_clear_count(3), "", db, "n", "PAL", True)
    assert len(bank.list("")) == 1


def test_same_tablet_in_other_folder_is_fine(bank: Bank, db: TabletDatabase) -> None:
    bank.create_folder("a")
    bank.create_folder("b")
    add_one(bank, db, "a")
    add_one(bank, db, "b")
    assert len(bank.list("a")) == len(bank.list("b")) == 1


def test_add_leaves_no_temp_files(bank: Bank, db: TabletDatabase) -> None:
    path = add_one(bank, db)
    assert [p.name for p in bank.root.iterdir()] == [path.name]


def test_safe_file_stem() -> None:
    assert safe_file_stem('Bad<>:"/\\|?*name. ') == "Bad_________name"
    assert safe_file_stem("CON") != "CON"
    assert safe_file_stem("con.txt").lower() != "con.txt"
    assert safe_file_stem("a\x01b") == "a_b"
    assert safe_file_stem("...") != ""
    assert safe_file_stem("") != ""
    assert safe_file_stem("Plain name") == "Plain name"


def test_import_save_adds_nine_then_zero(bank: Bank, db: TabletDatabase) -> None:
    save = pal_save()
    assert len(save.received.live) == 9
    paths = bank.import_save(save, "", db, "save003", "PAL")
    assert len(paths) == 9
    assert all(bank.read(p).from_real_save for p in paths)
    assert bank.import_save(save, "", db, "save003", "PAL") == []
    assert len(bank.list("")) == 9


def test_list_is_sorted_by_name(bank: Bank, db: TabletDatabase) -> None:
    bank.import_save(pal_save(), "", db, "s", "PAL")
    names = [t.name for t in bank.list("")]
    assert names == sorted(names, key=str.lower)


def test_move_between_folders(bank: Bank, db: TabletDatabase) -> None:
    bank.create_folder("dest")
    path = add_one(bank, db)
    moved = bank.move([path], "dest")
    assert not path.exists()
    assert moved == [bank.root / "dest" / path.name]
    assert bank.read(moved[0]).record_raw == first_record().raw


def test_move_refuses_duplicate(bank: Bank, db: TabletDatabase) -> None:
    bank.create_folder("dest")
    path = add_one(bank, db)
    add_one(bank, db, "dest")
    with pytest.raises(DuplicateTabletError):
        bank.move([path], "dest")
    assert path.exists()


def test_move_same_name_different_tablet_gets_suffix(bank: Bank, db: TabletDatabase) -> None:
    bank.create_folder("dest")
    same = SameNameDb()
    path = bank.add(first_record(), "", same, "n", "PAL", True)  # type: ignore[arg-type]
    other = bank.add(variant(first_record()), "dest", same, "n", "PAL", True)  # type: ignore[arg-type]
    moved = bank.move([path], "dest")
    assert moved[0].name == f"{path.stem} (2){BANK_EXTENSION}"
    assert other.exists()


def test_move_from_outside_root_refused(bank: Bank, tmp_path: Path) -> None:
    outside = tmp_path / f"x{BANK_EXTENSION}"
    outside.write_text("{}")
    with pytest.raises(BankFileError):
        bank.move([outside], "")
    assert outside.exists()


def test_delete_uses_trash(bank: Bank, db: TabletDatabase, monkeypatch: pytest.MonkeyPatch) -> None:
    trashed: list[str] = []
    monkeypatch.setattr(send2trash, "send2trash", lambda p: trashed.append(str(p)))
    path = add_one(bank, db)
    bank.delete([path])
    assert trashed == [str(path)]


def test_delete_failure_is_save_io_error(
    bank: Bank, db: TabletDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_p: object) -> None:
        raise OSError("nope")

    monkeypatch.setattr(send2trash, "send2trash", boom)
    path = add_one(bank, db)
    with pytest.raises(SaveIOError):
        bank.delete([path])


def test_delete_outside_root_refused(
    bank: Bank, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trashed: list[str] = []
    monkeypatch.setattr(send2trash, "send2trash", lambda p: trashed.append(str(p)))
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    with pytest.raises(BankFileError):
        bank.delete([outside])
    assert trashed == []
    assert outside.exists()


def corrupt_variants(good: dict) -> dict[str, str]:
    return {
        "bad_json": "{not json",
        "not_object": "[1, 2]",
        "wrong_length": json.dumps(dict(good, record_hex=good["record_hex"][:-2])),
        "format2": json.dumps(dict(good, format=2)),
        "layout_jp": json.dumps(dict(good, layout="jp")),
        "selfmade_wrong_len": json.dumps(dict(good, list="selfmade")),
        "bad_hex": json.dumps(dict(good, record_hex="zz" * 0x54)),
        "bad_list": json.dumps(dict(good, list="other")),
        "missing_name": json.dumps({k: v for k, v in good.items() if k != "name"}),
        "bad_clear_count": json.dumps(dict(good, clear_count="x")),
    }


def test_corrupt_files_skipped_in_list_and_refused_by_read(
    bank: Bank, db: TabletDatabase, caplog: pytest.LogCaptureFixture
) -> None:
    good = add_one(bank, db)
    bad_paths = []
    for name, text in corrupt_variants(payload(good)).items():
        p = bank.root / f"{name}{BANK_EXTENSION}"
        p.write_text(text, encoding="utf-8")
        bad_paths.append(p)
    with caplog.at_level("WARNING"):
        listed = bank.list("")
    assert [t.path for t in listed] == [good]
    assert len([r for r in caplog.records if r.levelname == "WARNING"]) == len(bad_paths)
    for p in bad_paths:
        with pytest.raises(BankFileError):
            bank.read(p)


def test_read_missing_file_is_bank_file_error(bank: Bank) -> None:
    with pytest.raises(BankFileError):
        bank.read(bank.root / f"nope{BANK_EXTENSION}")


def test_selfmade_file_reads_with_unknown_kind(bank: Bank) -> None:
    raw = bytes(SELFMADE_BYTES)
    data = {
        "format": 1,
        "list": "selfmade",
        "layout": "western",
        "record_hex": raw.hex(),
        "name": "Mine",
        "kind": "unknown",
        "clear_count": 0,
        "source": "",
        "region": "US",
        "from_real_save": False,
    }
    bank.root.mkdir(parents=True)
    path = bank.root / f"Mine{BANK_EXTENSION}"
    write_payload(path, data)
    tablet = bank.read(path)
    assert tablet.list_kind is BankList.SELFMADE
    assert tablet.kind is TabletKind.UNKNOWN
    assert tablet.record_raw == raw


@pytest.mark.parametrize("name", ["", "..", ".", "a/b", "a\\b", ".hidden", "x:y", "a*b", " "])
def test_bad_folder_names_refused(bank: Bank, name: str) -> None:
    with pytest.raises(BankFileError):
        bank.create_folder(name)


def test_bad_folder_refused_everywhere(bank: Bank, db: TabletDatabase) -> None:
    with pytest.raises(BankFileError):
        bank.add(first_record(), "../x", db, "n", "PAL", True)
    with pytest.raises(BankFileError):
        bank.list("../x")
    with pytest.raises(BankFileError):
        bank.move([], "..")


def test_folders_and_root(bank: Bank, db: TabletDatabase) -> None:
    assert bank.folders() == []
    bank.create_folder("Alpha")
    bank.create_folder("Beta")
    assert bank.folders() == ["Alpha", "Beta"]
    add_one(bank, db)
    assert bank.folders() == ["", "Alpha", "Beta"]


def test_create_existing_folder_is_refused(bank: Bank) -> None:
    bank.create_folder("Alpha")
    with pytest.raises(BankFileError):
        bank.create_folder("Alpha")


def test_rename_folder(bank: Bank, db: TabletDatabase) -> None:
    bank.create_folder("old")
    add_one(bank, db, "old")
    bank.rename_folder("old", "new")
    assert bank.folders() == ["new"]
    assert len(bank.list("new")) == 1


def test_rename_folder_refusals(bank: Bank) -> None:
    bank.create_folder("a")
    bank.create_folder("b")
    with pytest.raises(BankFileError):
        bank.rename_folder("a", "b")
    with pytest.raises(BankFileError):
        bank.rename_folder("missing", "c")
    with pytest.raises(BankFileError):
        bank.rename_folder("a", "../c")
    assert bank.folders() == ["a", "b"]


def test_list_missing_folder_is_empty(bank: Bank) -> None:
    assert bank.list("nope") == []


def test_move_into_same_folder_is_noop(bank: Bank, db: TabletDatabase) -> None:
    path = add_one(bank, db)
    assert bank.move([path], "") == [path]
    bank.create_folder("f")
    inner = add_one(bank, db, "f")
    assert bank.move([inner], "f") == [inner]
    assert inner.exists()


def test_relative_root(tmp_path: Path, db: TabletDatabase, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    rel = Bank(Path("relbank"))
    assert rel.root.is_absolute()
    rel.create_folder("f")
    path = add_one(rel, db, "f")
    assert path.is_absolute()
    assert [t.path for t in rel.list("f")] == [path]
    assert rel.move([path], "f") == [path]


def test_move_batch_with_identical_tablets_refused(bank: Bank, db: TabletDatabase) -> None:
    bank.create_folder("a")
    bank.create_folder("b")
    bank.create_folder("dest")
    one = add_one(bank, db, "a")
    two = add_one(bank, db, "b")
    with pytest.raises(DuplicateTabletError):
        bank.move([one, two], "dest")
    assert one.exists() and two.exists()
    assert bank.list("dest") == []


def test_delete_refuses_root_folder_and_other_files(
    bank: Bank, db: TabletDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    trashed: list[str] = []
    monkeypatch.setattr(send2trash, "send2trash", lambda p: trashed.append(str(p)))
    bank.create_folder("f")
    good = add_one(bank, db)
    note = bank.root / "notes.txt"
    note.write_text("x")
    for bad in (bank.root, bank.root / "f", note):
        with pytest.raises(BankFileError):
            bank.delete([bad])
    with pytest.raises(BankFileError):
        bank.delete([good, note])
    assert trashed == []


def test_case_only_folder_rename(bank: Bank, db: TabletDatabase) -> None:
    bank.create_folder("abc")
    add_one(bank, db, "abc")
    bank.rename_folder("abc", "ABC")
    assert bank.folders() == ["ABC"]
    assert len(bank.list("ABC")) == 1


def test_format_must_be_int_one_and_hex_without_whitespace(bank: Bank, db: TabletDatabase) -> None:
    good = add_one(bank, db)
    data = payload(good)
    spaced = data["record_hex"][:4] + " " + data["record_hex"][4:]
    for name, changed in (
        ("float", dict(data, format=1.0)),
        ("space", dict(data, record_hex=spaced)),
    ):
        p = bank.root / f"{name}{BANK_EXTENSION}"
        write_payload(p, changed)
        with pytest.raises(BankFileError):
            bank.read(p)


def test_publish_never_overwrites_late_target(bank: Bank) -> None:
    bank.root.mkdir(parents=True)
    temp = bank.root / "t.tmp"
    temp.write_text("new")
    existing = bank.root / f"X{BANK_EXTENSION}"
    existing.write_text("old")
    target = bank._publish(temp, bank.root, "X")
    assert existing.read_text() == "old"
    assert target.name == f"X (2){BANK_EXTENSION}"
    assert target.read_text() == "new"


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("", BankProblem.EMPTY),
        (".hidden", BankProblem.HIDDEN),
        ("a/b", BankProblem.BAD_CHARACTERS),
        ("trailing.", BankProblem.TRAILING),
        ("con", BankProblem.RESERVED),
    ],
)
def test_folder_name_refusals_carry_a_reason(bank: Bank, name: str, reason: BankProblem) -> None:
    with pytest.raises(BankFileError) as caught:
        bank.create_folder(name)
    assert caught.value.reason is reason
    assert str(caught.value).startswith(f"folder name {name!r} ")


def test_folder_and_file_refusals_carry_a_reason(
    bank: Bank, db: TabletDatabase, tmp_path: Path
) -> None:
    bank.create_folder("Rares")
    with pytest.raises(BankFileError) as caught:
        bank.create_folder("Rares")
    assert caught.value.reason is BankProblem.EXISTS
    assert str(caught.value) == "folder 'Rares' already exists"
    with pytest.raises(BankFileError) as caught:
        bank.rename_folder("Missing", "Other")
    assert caught.value.reason is BankProblem.MISSING
    broken = bank.root / f"Broken{BANK_EXTENSION}"
    broken.write_text("not json", encoding="utf-8")
    with pytest.raises(BankFileError) as caught:
        bank.read(broken)
    assert caught.value.reason is BankProblem.DAMAGED
    with pytest.raises(BankFileError) as caught:
        bank.read(bank.root / f"Gone{BANK_EXTENSION}")
    assert caught.value.reason is BankProblem.UNREADABLE
    outside = tmp_path / f"Outside{BANK_EXTENSION}"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(BankFileError) as caught:
        bank.delete([outside])
    assert caught.value.reason is BankProblem.OUTSIDE
    with pytest.raises(BankFileError) as caught:
        bank.delete([bank.root / "Rares"])
    assert caught.value.reason is BankProblem.NOT_TABLET


def test_duplicates_name_the_tablet(bank: Bank, db: TabletDatabase) -> None:
    record = first_record()
    bank.add(record, "", db, "test", "US", True)
    with pytest.raises(DuplicateTabletError) as caught:
        bank.add(record, "", db, "test", "US", True)
    name = db.lookup(record).name_en
    assert caught.value.name == name
    assert str(caught.value) == f"{name} is already in the bank"
    assert not issubclass(DuplicateTabletError, BankFileError)
