from dataclasses import replace

import pytest
from conftest import ALL_SAVES, load_fixture

from dq7tt.checksum import apply_checksum
from dq7tt.constants import (
    CHECKSUM_BYTES,
    IMIN_OFFSET,
    REC_CLEAR_2,
    RECEIVED_COUNT_OFFSET,
    RECEIVED_OFFSET,
    RECEIVED_RECORD_SIZE,
    RECEIVED_SLOTS,
    SELFMADE_COUNT_OFFSET,
    SELFMADE_OFFSET,
)
from dq7tt.database import TabletDatabase, TabletInfo
from dq7tt.errors import ValidationError
from dq7tt.savefile import SaveFile, SlotRole
from dq7tt.tablets import TabletKind, TabletRecord
from dq7tt.validate import Problem, Severity, require_valid, validate


@pytest.fixture(scope="module")
def db() -> TabletDatabase:
    return TabletDatabase.load()


@pytest.fixture
def orig() -> SaveFile:
    return SaveFile.from_bytes(load_fixture("pal_superkiefer", 3), SlotRole.LOG_3)


def _fresh(db: TabletDatabase, save: SaveFile, kind: TabletKind | None = None) -> TabletInfo:
    live = {r.identity for r in save.received.live}
    for t in db.all():
        if t.record.identity not in live and (kind is None or t.kind == kind):
            return t
    raise AssertionError("no fresh tablet")


def _fix(data: bytes) -> bytes:
    buf = bytearray(data)
    apply_checksum(buf)
    return bytes(buf)


def _codes(problems: list[Problem], severity: Severity | None = None) -> set[str]:
    return {p.code for p in problems if severity is None or p.severity == severity}


def test_clean_edit_has_no_errors(orig: SaveFile, db: TabletDatabase) -> None:
    info = _fresh(db, orig, TabletKind.DLC)
    assert info.verified
    edited = orig.with_received(orig.received.insert(info.record))
    assert _codes(validate(edited, orig, db), Severity.ERROR) == set()


@pytest.mark.parametrize("path", ALL_SAVES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_unedited_fixtures_pass(path, db: TabletDatabase) -> None:
    s = SaveFile.load(path)
    assert _codes(validate(s, s, db), Severity.ERROR) == set()


def test_layout(orig: SaveFile, db: TabletDatabase) -> None:
    bad = replace(orig, data=b"\x00" * len(orig.data))
    ps = validate(bad, orig, db)
    assert "LAYOUT" in _codes(ps, Severity.ERROR)


def test_checksum(orig: SaveFile, db: TabletDatabase) -> None:
    buf = bytearray(orig.data)
    buf[0] ^= 0xFF
    ps = validate(replace(orig, data=bytes(buf)), orig, db)
    assert "CHECKSUM" in _codes(ps, Severity.ERROR)


def test_count_range_reported_not_raised(orig: SaveFile, db: TabletDatabase) -> None:
    buf = bytearray(orig.data)
    buf[RECEIVED_COUNT_OFFSET] = 25
    ps = validate(replace(orig, data=_fix(bytes(buf))), orig, db)
    assert "COUNT_RANGE" in _codes(ps, Severity.ERROR)


def test_duplicate(orig: SaveFile, db: TabletDatabase) -> None:
    lst = orig.received
    slots = list(lst.slots)
    slots[1] = slots[0]
    edited = replace(orig, data=_fix(orig.with_received(replace(lst, slots=tuple(slots))).data))
    assert "DUPLICATE" in _codes(validate(edited, orig, db), Severity.ERROR)


def _set_clear_2(save: SaveFile, index: int, value: int) -> SaveFile:
    buf = bytearray(save.data)
    buf[RECEIVED_OFFSET + index * RECEIVED_RECORD_SIZE + REC_CLEAR_2] = value
    return replace(save, data=_fix(bytes(buf)))


def test_clear_mismatch_existing_record(orig: SaveFile, db: TabletDatabase) -> None:
    assert orig.received.live[0].clear_counts_agree
    edited = _set_clear_2(orig, 0, (orig.received.live[0].raw[REC_CLEAR_2] + 1) & 0xFF)
    assert "CLEAR_MISMATCH" in _codes(validate(edited, orig, db), Severity.ERROR)


def test_clear_mismatch_new_record(orig: SaveFile, db: TabletDatabase) -> None:
    info = _fresh(db, orig, TabletKind.DLC)
    edited = orig.with_received(orig.received.insert(info.record))
    edited = _set_clear_2(edited, 0, (info.record.raw[REC_CLEAR_2] + 1) & 0xFF)
    assert "CLEAR_MISMATCH" in _codes(validate(edited, orig, db), Severity.ERROR)


def test_clear_mismatch_preexisting_is_tolerated(orig: SaveFile, db: TabletDatabase) -> None:
    broken = _set_clear_2(orig, 0, (orig.received.live[0].raw[REC_CLEAR_2] + 1) & 0xFF)
    assert "CLEAR_MISMATCH" not in _codes(validate(broken, broken, db))


def test_unknown_new(orig: SaveFile, db: TabletDatabase) -> None:
    raw = bytearray(_fresh(db, orig, TabletKind.DLC).record.raw)
    raw[0x20] ^= 0x5A
    raw[0x21] ^= 0xA5
    edited = orig.with_received(orig.received.insert(TabletRecord(bytes(raw))))
    assert "UNKNOWN_NEW" in _codes(validate(edited, orig, db), Severity.ERROR)


def test_unknown_but_already_live_is_fine(orig: SaveFile, db: TabletDatabase) -> None:
    raw = bytearray(_fresh(db, orig, TabletKind.DLC).record.raw)
    raw[0x20] ^= 0x5A
    raw[0x21] ^= 0xA5
    base = orig.with_received(orig.received.insert(TabletRecord(bytes(raw))))
    assert _codes(validate(base, base, db), Severity.ERROR) == set()


def test_unverified_new(orig: SaveFile, db: TabletDatabase) -> None:
    live = {r.identity for r in orig.received.live}
    info = next(t for t in db.all() if not t.verified and t.record.identity not in live)
    edited = orig.with_received(orig.received.insert(info.record))
    assert "UNVERIFIED_NEW" in _codes(validate(edited, orig, db), Severity.ERROR)


def test_unverified_already_live_is_fine(orig: SaveFile, db: TabletDatabase) -> None:
    live = {r.identity for r in orig.received.live}
    info = next(t for t in db.all() if not t.verified and t.record.identity not in live)
    base = orig.with_received(orig.received.insert(info.record))
    assert _codes(validate(base, base, db), Severity.ERROR) == set()


def test_selfmade_region_changed(orig: SaveFile, db: TabletDatabase) -> None:
    buf = bytearray(orig.data)
    buf[SELFMADE_OFFSET + 3] ^= 0x01
    ps = validate(replace(orig, data=_fix(bytes(buf))), orig, db)
    assert "SELFMADE_CHANGED" in _codes(ps, Severity.ERROR)


def test_selfmade_count_changed(orig: SaveFile, db: TabletDatabase) -> None:
    buf = bytearray(orig.data)
    buf[SELFMADE_COUNT_OFFSET] = 1
    ps = validate(replace(orig, data=_fix(bytes(buf))), orig, db)
    assert "SELFMADE_CHANGED" in _codes(ps, Severity.ERROR)


def test_quick_save_warning(db: TabletDatabase) -> None:
    quick = SaveFile.from_bytes(load_fixture("pal_superkiefer", 0), SlotRole.QUICK_SAVE)
    info = _fresh(db, quick, TabletKind.DLC)
    edited = quick.with_received(quick.received.remove(0).insert(info.record))
    ps = validate(edited, quick, db)
    assert "QUICK_SAVE" in _codes(ps, Severity.WARNING)
    assert "QUICK_SAVE" not in _codes(validate(quick, quick, db))


def test_story_added_warning(orig: SaveFile, db: TabletDatabase) -> None:
    info = _fresh(db, orig, TabletKind.STORY)
    edited = orig.with_received(orig.received.insert(info.record))
    ps = validate(edited, orig, db)
    story = [p for p in ps if p.code == "STORY_ADDED"]
    assert story and story[0].severity == Severity.WARNING
    assert info.name_en in story[0].message


def test_input_checksum_warning(orig: SaveFile, db: TabletDatabase) -> None:
    buf = bytearray(orig.data)
    buf[0] ^= 0xFF
    bad = replace(orig, data=bytes(buf))
    ps = validate(orig, bad, db)
    assert "INPUT_CHECKSUM" in _codes(ps, Severity.WARNING)


def test_require_valid(orig: SaveFile, db: TabletDatabase) -> None:
    require_valid(orig, orig, db)
    buf = bytearray(orig.data)
    buf[0] ^= 0xFF
    with pytest.raises(ValidationError) as exc:
        require_valid(replace(orig, data=bytes(buf)), orig, db)
    assert any(p.code == "CHECKSUM" for p in exc.value.problems)


def test_outside_changed(orig: SaveFile, db: TabletDatabase) -> None:
    buf = bytearray(orig.data)
    buf[IMIN_OFFSET + 0x14] ^= 0x01
    ps = validate(replace(orig, data=_fix(bytes(buf))), orig, db)
    assert "OUTSIDE_CHANGED" in _codes(ps, Severity.ERROR)


def test_normal_insert_changes_nothing_outside(orig: SaveFile, db: TabletDatabase) -> None:
    info = _fresh(db, orig, TabletKind.DLC)
    edited = orig.with_received(orig.received.insert(info.record))
    assert "OUTSIDE_CHANGED" not in _codes(validate(edited, orig, db))


def test_with_received_touches_only_list_regions(orig: SaveFile, db: TabletDatabase) -> None:
    info = _fresh(db, orig, TabletKind.DLC)
    edited = orig.with_received(orig.received.insert(info.record))
    allowed = (
        set(range(CHECKSUM_BYTES))
        | set(range(RECEIVED_OFFSET, RECEIVED_OFFSET + RECEIVED_SLOTS * RECEIVED_RECORD_SIZE))
        | {RECEIVED_COUNT_OFFSET}
    )
    changed = {i for i, (a, b) in enumerate(zip(orig.data, edited.data, strict=True)) if a != b}
    assert changed
    assert changed <= allowed


def test_truncated_edited_reports_layout_only(orig: SaveFile, db: TabletDatabase) -> None:
    for size in (0, 1, RECEIVED_COUNT_OFFSET, len(orig.data) - 1):
        ps = validate(replace(orig, data=orig.data[:size]), orig, db)
        assert _codes(ps) == {"LAYOUT"}


def test_original_with_bad_count_does_not_raise(orig: SaveFile, db: TabletDatabase) -> None:
    buf = bytearray(orig.data)
    buf[RECEIVED_COUNT_OFFSET] = 25
    bad_original = replace(orig, data=_fix(bytes(buf)))
    ps = validate(orig, bad_original, db)
    assert isinstance(ps, list)
    quick = replace(orig, role=SlotRole.QUICK_SAVE)
    validate(quick, replace(bad_original, role=SlotRole.QUICK_SAVE), db)


def test_hole_in_list(orig: SaveFile, db: TabletDatabase) -> None:
    info = _fresh(db, orig, TabletKind.DLC)
    lst = orig.received.insert(info.record)
    slots = list(lst.slots)
    slots[1] = bytes(RECEIVED_RECORD_SIZE)
    edited = orig.with_received(replace(lst, slots=tuple(slots)))
    assert "UNKNOWN_NEW" in _codes(validate(edited, orig, db), Severity.ERROR)
