from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from conftest import load_fixture
from test_sources import fill

from dq7tt.apppaths import AppPaths
from dq7tt.bank import Bank, BankList, BankTablet
from dq7tt.constants import SAVE_FILENAMES
from dq7tt.database import TabletDatabase
from dq7tt.errors import (
    DuplicateTabletError,
    InvalidSlotError,
    SessionError,
    TabletCapError,
    ValidationError,
)
from dq7tt.savefile import SaveFile, SlotRole
from dq7tt.session import Session, Target
from dq7tt.tablets import TabletKind, TabletRecord
from dq7tt.validate import Severity

START = datetime(2026, 10, 21, 13, 5, 9)
CHECKPOINT_PATH = "sd/3ds/Checkpoint/saves/0x18EF0 DRAGON QUEST VII/20261020-101500"
OTHER_CHECKPOINT_PATH = "sd/3ds/Checkpoint/saves/0x18EF0 DRAGON QUEST VII/20261019-090000"
SECOND_SET = "pal_superkiefer"
ODDNA = "Mount Oddna"
UNVERIFIED = "Blimpton"
QUICK_ODDNA_SLOT = 4
ODDNA_QUICK_CLEARS = 1
CHANGED_BYTE = 0x40
DB = TabletDatabase.load()


def ticking_clock() -> Callable[[], datetime]:
    ticks = iter(range(10_000))
    return lambda: START + timedelta(seconds=next(ticks))


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def new_session(tmp_path: Path) -> Session:
    return Session(AppPaths.under(tmp_path / "app"), DB, clock=ticking_clock())


def opened(tmp_path: Path, rel: str = CHECKPOINT_PATH) -> tuple[Session, int]:
    session = new_session(tmp_path)
    return session, session.open(fill(tmp_path / rel))


def edited(session: Session, sid: int, role: SlotRole) -> SaveFile:
    return session.sources()[sid].edited[role]


def names(session: Session, sid: int, role: SlotRole) -> list[str]:
    return [DB.lookup(r).name_en for r in edited(session, sid, role).received.live]


def all_bytes(session: Session) -> dict[tuple[int, SlotRole], bytes]:
    return {
        (sid, role): save.to_bytes()
        for sid, src in session.sources().items()
        for role, save in src.edited.items()
    }


def test_open_two_refuses_a_third(tmp_path: Path) -> None:
    session = new_session(tmp_path)
    first = session.open(fill(tmp_path / CHECKPOINT_PATH))
    second = session.open(fill(tmp_path / OTHER_CHECKPOINT_PATH, SECOND_SET))
    assert first != second
    assert set(session.sources()) == {first, second}
    with pytest.raises(SessionError, match="Close a save before opening a third."):
        session.open(fill(tmp_path / "third"))
    assert set(session.sources()) == {first, second}


def test_same_folder_twice_is_refused(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    folder = tmp_path / CHECKPOINT_PATH
    with pytest.raises(SessionError, match="already open"):
        session.open(folder.parent / ".." / folder.parent.name / folder.name)
    with pytest.raises(SessionError, match="already open"):
        session.open(folder / SAVE_FILENAMES[1])
    assert set(session.sources()) == {sid}


def test_open_loads_original_and_edited(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    src = session.sources()[sid]
    assert set(src.original) == set(SlotRole) - {SlotRole.UNKNOWN}
    assert src.edited == src.original
    assert src.original[SlotRole.LOG_3].to_bytes() == load_fixture("us_postgame", 3)
    assert not session.is_dirty(sid)
    assert not session.can_undo and not session.can_redo


def test_add_from_database_undo_redo_exact_bytes(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    before = all_bytes(session)
    target = Target(sid, SlotRole.LOG_3)
    session.add_from_database(target, ODDNA)
    after = all_bytes(session)
    assert names(session, sid, SlotRole.LOG_3)[0] == ODDNA
    assert session.is_dirty(sid)
    assert session.undo() == "Add Mount Oddna to adventure log 3"
    assert all_bytes(session) == before
    assert not session.is_dirty(sid)
    assert session.redo() == "Add Mount Oddna to adventure log 3"
    assert all_bytes(session) == after


def test_add_at_index(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    session.add_from_database(Target(sid, SlotRole.LOG_3), ODDNA, index=2)
    assert names(session, sid, SlotRole.LOG_3)[2] == ODDNA


def test_refused_add_on_full_log_changes_nothing(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    session.add_from_database(Target(sid, SlotRole.LOG_3), ODDNA)
    before = all_bytes(session)
    with pytest.raises(TabletCapError):
        session.add_from_database(Target(sid, SlotRole.LOG_2), "Feral Forest")
    session.undo()
    with pytest.raises(DuplicateTabletError):
        session.add_from_database(Target(sid, SlotRole.LOG_3), "Feral Forest")
    assert session.redo() == "Add Mount Oddna to adventure log 3"
    assert all_bytes(session) == before
    assert not session.can_redo
    assert session.undo() == "Add Mount Oddna to adventure log 3"
    assert not session.can_undo


def test_validation_refusal_changes_nothing(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    before = all_bytes(session)
    with pytest.raises(ValidationError) as caught:
        session.add_from_database(Target(sid, SlotRole.LOG_3), UNVERIFIED)
    assert all(p.severity is Severity.ERROR for p in caught.value.problems)
    assert any(p.code == "UNVERIFIED_NEW" for p in caught.value.problems)
    assert all_bytes(session) == before
    assert not session.can_undo


def test_remove_and_reorder(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    target = Target(sid, SlotRole.LOG_3)
    start = names(session, sid, SlotRole.LOG_3)
    session.move(target, 0, 2)
    assert names(session, sid, SlotRole.LOG_3)[:3] == [start[1], start[2], start[0]]
    assert session.undo() == "Reorder Feral Forest in adventure log 3"
    session.remove(target, 0)
    assert names(session, sid, SlotRole.LOG_3) == start[1:]
    assert session.undo() == "Remove Feral Forest from adventure log 3"
    assert names(session, sid, SlotRole.LOG_3) == start
    with pytest.raises(InvalidSlotError):
        session.remove(target, len(start))
    assert session.can_redo


def test_copy_between_sources_keeps_or_resets_clear_count(tmp_path: Path) -> None:
    session = new_session(tmp_path)
    us = session.open(fill(tmp_path / CHECKPOINT_PATH))
    pal = session.open(fill(tmp_path / OTHER_CHECKPOINT_PATH, SECOND_SET))
    src = Target(us, SlotRole.QUICK_SAVE)
    dst = Target(pal, SlotRole.LOG_3)
    record = edited(session, us, SlotRole.QUICK_SAVE).received.live[QUICK_ODDNA_SLOT]
    assert record.clear_count == ODDNA_QUICK_CLEARS
    us_before = edited(session, us, SlotRole.QUICK_SAVE)

    session.copy(src, QUICK_ODDNA_SLOT, dst)
    copied = edited(session, pal, SlotRole.LOG_3).received.live[0]
    assert copied.raw == record.raw
    assert edited(session, us, SlotRole.QUICK_SAVE) == us_before
    assert session.undo() == "Copy Mount Oddna from the quick save to adventure log 3"

    session.copy(src, QUICK_ODDNA_SLOT, dst, index=1, reset_clears=True)
    reset = edited(session, pal, SlotRole.LOG_3).received.live[1]
    assert reset.clear_count == 0
    assert reset.raw == record.with_clear_count(0).raw


def test_move_to_is_one_undo_step(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    before = all_bytes(session)
    session.move_to(Target(sid, SlotRole.LOG_1), 0, Target(sid, SlotRole.LOG_3))
    assert ODDNA not in names(session, sid, SlotRole.LOG_1)
    assert names(session, sid, SlotRole.LOG_3)[0] == ODDNA
    assert session.undo() == "Move Mount Oddna from adventure log 1 to adventure log 3"
    assert all_bytes(session) == before
    assert not session.can_undo


def test_reset_clears(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    target = Target(sid, SlotRole.QUICK_SAVE)
    session.reset_clears(target, QUICK_ODDNA_SLOT)
    assert (
        edited(session, sid, SlotRole.QUICK_SAVE).received.live[QUICK_ODDNA_SLOT].clear_count == 0
    )
    assert session.undo() == "Reset clear count of Mount Oddna in the quick save"


def _tamper(folder: Path) -> TabletRecord:
    """Change one byte of the first live record in save001, as if the game wrote a variant."""
    path = folder / SAVE_FILENAMES[1]
    save = SaveFile.load(path)
    lst = save.received
    raw = bytearray(lst.slots[0])
    raw[CHANGED_BYTE] ^= 1
    slots = (bytes(raw), *lst.slots[1:])
    path.write_bytes(save.with_received(type(lst)(slots=slots, count=lst.count)).to_bytes())
    return TabletRecord(bytes(raw))


def test_copy_of_real_save_record_not_in_database_is_allowed(tmp_path: Path) -> None:
    folder = fill(tmp_path / CHECKPOINT_PATH)
    record = _tamper(folder)
    assert DB.lookup(record) is None or DB.lookup(record).record.identity != record.identity
    session = new_session(tmp_path)
    sid = session.open(folder)
    session.copy(Target(sid, SlotRole.LOG_1), 0, Target(sid, SlotRole.LOG_3))
    assert edited(session, sid, SlotRole.LOG_3).received.live[0].raw == record.raw
    found = session.problems(sid)
    assert not [p for ps in found.values() for p in ps if p.severity is Severity.ERROR]


def _bank_tablet(record: TabletRecord, from_real_save: bool, kind: BankList) -> BankTablet:
    return BankTablet(
        path=Path("x.dq7tablet"),
        list_kind=kind,
        record_raw=record.raw,
        name=ODDNA,
        kind=TabletKind.DLC,
        clear_count=record.clear_count,
        source_note="test",
        region="US",
        from_real_save=from_real_save,
    )


def test_add_from_bank(tmp_path: Path) -> None:
    folder = fill(tmp_path / CHECKPOINT_PATH)
    variant = _tamper(fill(tmp_path / "scratch"))
    session = new_session(tmp_path)
    sid = session.open(folder)
    target = Target(sid, SlotRole.LOG_3)
    with pytest.raises(ValidationError):
        session.add_from_bank(target, _bank_tablet(variant, False, BankList.RECEIVED))
    assert not session.can_undo
    with pytest.raises(SessionError, match="Self-made tablets can be banked"):
        session.add_from_bank(target, _bank_tablet(variant, True, BankList.SELFMADE))
    session.add_from_bank(target, _bank_tablet(variant, True, BankList.RECEIVED))
    assert edited(session, sid, SlotRole.LOG_3).received.live[0].raw == variant.raw
    assert session.undo() == "Add Mount Oddna to adventure log 3"


def test_bank_from_does_not_change_state(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    bank = Bank(tmp_path / "bank")
    before = all_bytes(session)
    path = session.bank_from(Target(sid, SlotRole.QUICK_SAVE), QUICK_ODDNA_SLOT, bank, "")
    assert all_bytes(session) == before
    assert not session.can_undo
    banked = bank.read(path)
    assert banked.name == ODDNA
    assert banked.clear_count == ODDNA_QUICK_CLEARS
    assert banked.from_real_save


def test_move_to_same_log_is_refused(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    target = Target(sid, SlotRole.LOG_3)
    with pytest.raises(SessionError, match="reorder"):
        session.move_to(target, 0, target)
    assert not session.can_undo


def test_problems_are_grouped_by_role(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    found = session.problems(sid)
    assert set(found) == {SlotRole.QUICK_SAVE, SlotRole.LOG_1, SlotRole.LOG_2, SlotRole.LOG_3}
    session.remove(Target(sid, SlotRole.QUICK_SAVE), 0)
    assert "QUICK_SAVE" in {p.code for p in session.problems(sid)[SlotRole.QUICK_SAVE]}
    assert session.problems(sid)[SlotRole.LOG_1] == []


def test_reset_clears_on_uncleared_tablet_is_refused(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    with pytest.raises(SessionError, match="That tablet has not been cleared."):
        session.reset_clears(Target(sid, SlotRole.LOG_3), 0)
    assert not session.can_undo


def test_accessors_for_the_window(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    target = Target(sid, SlotRole.LOG_3)
    assert session.db is DB
    assert session.undo_label is None and session.redo_label is None
    assert session.dirty_roles(sid) == set()
    session.add_from_database(target, ODDNA)
    assert session.undo_label == "Add Mount Oddna to adventure log 3"
    assert session.dirty_roles(sid) == {SlotRole.LOG_3}
    rows = session.tablets(target)
    assert rows[0][0] == ODDNA
    assert rows[0][1] is TabletKind.DLC
    assert rows[0][2] == edited(session, sid, SlotRole.LOG_3).received.live[0]
    assert len(rows) == edited(session, sid, SlotRole.LOG_3).received.count
    session.undo()
    assert session.undo_label is None
    assert session.redo_label == "Add Mount Oddna to adventure log 3"
    assert session.last_output(sid) is None


def test_bank_from_marks_database_additions_not_real_after_write(tmp_path: Path) -> None:
    # us_superkiefer never received Divine Recollections, so only the database supplies it.
    folder = fill(tmp_path / CHECKPOINT_PATH, "us_superkiefer")
    session = new_session(tmp_path)
    sid = session.open(folder)
    target = Target(sid, SlotRole.LOG_2)
    session.remove(target, 0)
    session.add_from_database(target, "Divine Recollections")
    session.write(sid)
    bank = Bank(tmp_path / "bank")
    path = session.bank_from(target, 0, bank, "")
    assert not bank.read(path).from_real_save
