import dataclasses
from pathlib import Path

import pytest
from test_session import (
    CHECKPOINT_PATH,
    DB,
    ODDNA,
    OTHER_CHECKPOINT_PATH,
    SECOND_SET,
    all_bytes,
    edited,
    names,
    ticking_clock,
)
from test_sources import fill

from dq7tt.apppaths import AppPaths
from dq7tt.bank import Bank, BankList
from dq7tt.database import TabletDatabase
from dq7tt.errors import DuplicateTabletError, SessionError, TabletCapError
from dq7tt.savefile import SlotRole
from dq7tt.session import Session, Target

US_FULL_LOG3_FREE = 1


def two_sources(tmp_path: Path, db: TabletDatabase = DB) -> tuple[Session, int, int]:
    session = Session(AppPaths.under(tmp_path / "app"), db, clock=ticking_clock())
    us = session.open(fill(tmp_path / CHECKPOINT_PATH))
    pal = session.open(fill(tmp_path / OTHER_CHECKPOINT_PATH, SECOND_SET))
    return session, us, pal


def missing_slots(session: Session, src: Target, dst: Target, n: int) -> list[int]:
    """The first `n` positions of `src` whose tablets `dst` does not hold."""
    have = {r.identity for r in edited(session, dst.source_id, dst.role).received.live}
    live = edited(session, src.source_id, src.role).received.live
    return [i for i, r in enumerate(live) if r.identity not in have][:n]


def test_copy_many_is_one_step_in_order(tmp_path: Path) -> None:
    session, us, pal = two_sources(tmp_path)
    src, dst = Target(us, SlotRole.LOG_1), Target(pal, SlotRole.LOG_3)
    slots = missing_slots(session, src, dst, 3)
    before = all_bytes(session)
    wanted = [names(session, us, SlotRole.LOG_1)[i] for i in slots]
    session.copy_many(src, slots, dst, index=1)
    assert names(session, pal, SlotRole.LOG_3)[1:4] == wanted
    assert all_bytes(session)[(us, SlotRole.LOG_1)] == before[(us, SlotRole.LOG_1)]
    assert session.undo() == "Copy 3 tablets from adventure log 1 to adventure log 3"
    assert all_bytes(session) == before
    assert not session.can_undo


def test_copy_many_reset_clears(tmp_path: Path) -> None:
    session, us, pal = two_sources(tmp_path)
    src, dst = Target(us, SlotRole.QUICK_SAVE), Target(pal, SlotRole.LOG_3)
    slots = missing_slots(session, src, dst, 5)
    session.copy_many(src, slots, dst, reset_clears=True)
    assert all(r.clear_count == 0 for r in edited(session, pal, SlotRole.LOG_3).received.live[:5])


def test_copy_many_over_the_cap_changes_nothing(tmp_path: Path) -> None:
    session, us, pal = two_sources(tmp_path)
    src, dst = Target(pal, SlotRole.LOG_1), Target(us, SlotRole.LOG_3)
    slots = missing_slots(session, src, dst, US_FULL_LOG3_FREE + 1)
    before = all_bytes(session)
    with pytest.raises(TabletCapError):
        session.copy_many(src, slots, dst)
    assert all_bytes(session) == before
    assert not session.can_undo


def test_copy_many_with_a_duplicate_changes_nothing(tmp_path: Path) -> None:
    session, us, pal = two_sources(tmp_path)
    src, dst = Target(us, SlotRole.LOG_3), Target(pal, SlotRole.LOG_3)
    fresh = missing_slots(session, src, dst, 1)
    have = {r.identity for r in edited(session, pal, SlotRole.LOG_3).received.live}
    live = edited(session, us, SlotRole.LOG_3).received.live
    dup = next(i for i, r in enumerate(live) if r.identity in have)
    before = all_bytes(session)
    with pytest.raises(DuplicateTabletError):
        session.copy_many(src, [*fresh, dup], dst)
    assert all_bytes(session) == before
    assert not session.can_undo


def test_copy_many_needs_a_selection(tmp_path: Path) -> None:
    session, us, pal = two_sources(tmp_path)
    with pytest.raises(SessionError, match="Select"):
        session.copy_many(Target(us, SlotRole.LOG_1), [], Target(pal, SlotRole.LOG_3))
    assert not session.can_undo


def test_move_many_takes_them_out_of_the_source(tmp_path: Path) -> None:
    session, _, pal = two_sources(tmp_path)
    src, dst = Target(pal, SlotRole.LOG_1), Target(pal, SlotRole.LOG_3)
    slots = missing_slots(session, src, dst, 3)
    moved = [names(session, pal, SlotRole.LOG_1)[i] for i in slots]
    start = names(session, pal, SlotRole.LOG_1)
    before = all_bytes(session)
    session.move_many(src, slots, dst)
    assert names(session, pal, SlotRole.LOG_3)[:3] == moved
    assert names(session, pal, SlotRole.LOG_1) == [n for n in start if n not in moved]
    assert session.undo() == "Move 3 tablets from adventure log 1 to adventure log 3"
    assert all_bytes(session) == before
    assert not session.can_undo


def test_move_many_over_the_cap_changes_nothing(tmp_path: Path) -> None:
    session, us, pal = two_sources(tmp_path)
    src, dst = Target(pal, SlotRole.LOG_1), Target(us, SlotRole.LOG_3)
    slots = missing_slots(session, src, dst, US_FULL_LOG3_FREE + 1)
    before = all_bytes(session)
    with pytest.raises(TabletCapError):
        session.move_many(src, slots, dst)
    assert all_bytes(session) == before
    with pytest.raises(SessionError, match="reorder"):
        session.move_many(src, slots, src)
    assert not session.can_undo


def test_add_many_from_bank(tmp_path: Path) -> None:
    session, _, pal = two_sources(tmp_path)
    dst = Target(pal, SlotRole.LOG_3)
    bank = Bank(tmp_path / "bank")
    have = set(names(session, pal, SlotRole.LOG_3))
    picks = [t for t in DB.all() if t.verified and t.name_en not in have][:2]
    tablets = [bank.read(bank.add(t.record, "", DB, "test", "US", False)) for t in picks]
    before = all_bytes(session)
    session.add_many_from_bank(dst, tablets, index=0)
    assert names(session, pal, SlotRole.LOG_3)[:2] == [t.name_en for t in picks]
    assert session.undo() == "Add 2 tablets to adventure log 3"
    assert all_bytes(session) == before
    selfmade = dataclasses.replace(tablets[0], list_kind=BankList.SELFMADE)
    with pytest.raises(SessionError, match="Self-made"):
        session.add_many_from_bank(dst, [tablets[1], selfmade])
    assert all_bytes(session) == before
    assert not session.can_undo


def test_add_many_from_bank_over_the_cap_changes_nothing(tmp_path: Path) -> None:
    session, us, _ = two_sources(tmp_path)
    dst = Target(us, SlotRole.LOG_3)
    bank = Bank(tmp_path / "bank")
    have = set(names(session, us, SlotRole.LOG_3))
    picks = [t for t in DB.all() if t.verified and t.name_en not in have][:2]
    tablets = [bank.read(bank.add(t.record, "", DB, "test", "US", False)) for t in picks]
    before = all_bytes(session)
    with pytest.raises(TabletCapError):
        session.add_many_from_bank(dst, tablets)
    assert all_bytes(session) == before
    assert not session.can_undo


def test_copy_of_a_real_save_tablet_with_an_unverified_entry(tmp_path: Path) -> None:
    db = TabletDatabase(
        tuple(dataclasses.replace(t, verified=False) if t.name_en == ODDNA else t for t in DB.all())
    )
    session, us, pal = two_sources(tmp_path, db)
    src, dst = Target(us, SlotRole.LOG_1), Target(pal, SlotRole.LOG_3)
    assert names(session, us, SlotRole.LOG_1)[0] == ODDNA
    assert ODDNA not in names(session, pal, SlotRole.LOG_3)
    session.copy(src, 0, dst)
    assert names(session, pal, SlotRole.LOG_3)[0] == ODDNA
    session.undo()
    session.move_to(src, 0, dst)
    assert names(session, pal, SlotRole.LOG_3)[0] == ODDNA
    session.undo()
    session.copy_many(src, [0], dst)
    assert names(session, pal, SlotRole.LOG_3)[0] == ODDNA


def test_bank_all_marks_database_additions_not_real(tmp_path: Path) -> None:
    session = Session(AppPaths.under(tmp_path / "app"), DB, clock=ticking_clock())
    sid = session.open(fill(tmp_path / CHECKPOINT_PATH, "us_superkiefer"))
    target = Target(sid, SlotRole.LOG_2)
    session.remove(target, 0)
    session.add_from_database(target, "Divine Recollections")
    bank = Bank(tmp_path / "bank")
    written = session.bank_all(target, bank, "Mine")
    assert len(written) == len(session.tablets(target))
    by_name = {bank.read(p).name: bank.read(p).from_real_save for p in written}
    assert by_name.pop("Divine Recollections") is False
    assert all(by_name.values())
    assert session.bank_all(target, bank, "Mine") == []
    assert session.undo_label == "Add Divine Recollections to adventure log 2"
