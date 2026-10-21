import pytest
from conftest import load_fixture

from dq7tt.errors import CorruptSaveError, DuplicateTabletError, TabletCapError
from dq7tt.tablet_list import ReceivedList
from dq7tt.tablets import TabletRecord

EXPECTED_COUNTS = {
    "us_superkiefer": (6, 24, 24, 23),
    "us_postgame": (24, 24, 24, 23),
    "pal_superkiefer": (21, 24, 24, 9),
    "pal_postgame": (24, 24, 24, 12),
}
COUNT_OFFSET = 0x3E04


def lst(set_name: str, slot: int) -> ReceivedList:
    return ReceivedList.from_save_bytes(load_fixture(set_name, slot))


def foreign(target: ReceivedList, set_name: str = "us_postgame", slot: int = 0) -> TabletRecord:
    """A live record from another fixture that `target` does not contain."""
    for rec in lst(set_name, slot).live:
        if not target.contains(rec):
            return rec
    raise AssertionError("no foreign record available")


@pytest.mark.parametrize("set_name", list(EXPECTED_COUNTS))
def test_inventory_counts(set_name: str) -> None:
    for slot, expected in enumerate(EXPECTED_COUNTS[set_name]):
        received = lst(set_name, slot)
        assert received.count == expected
        assert len(received.slots) == 24
        assert all(len(s) == 0x54 for s in received.slots)
        assert received.free == 24 - expected


def test_corrupt_count_rejected() -> None:
    data = bytearray(load_fixture("us_superkiefer", 0))
    data[COUNT_OFFSET] = 25
    with pytest.raises(CorruptSaveError):
        ReceivedList.from_save_bytes(bytes(data))


def test_live_respects_count() -> None:
    received = lst("us_superkiefer", 0)
    assert len(received.live) == 6
    assert received.count == 6
    stale = {TabletRecord(s).identity for s in received.slots[6:]}
    live = {r.identity for r in received.live}
    assert stale
    assert len(stale & live) <= 1


def test_insert_at_top_shifts_down() -> None:
    received = lst("pal_superkiefer", 3)
    rec = foreign(received)
    result = received.insert(rec)
    assert result.live[0] == rec
    assert result.live[1:] == received.live
    assert result.count == 10
    assert result.slots[9] == received.slots[8]
    assert result.slots[10:] == received.slots[10:]
    assert len(result.slots) == 24


def test_insert_at_middle_and_end() -> None:
    received = lst("pal_superkiefer", 3)
    rec = foreign(received)
    mid = received.insert(rec, 4)
    assert mid.live[4] == rec
    assert mid.live[:4] == received.live[:4]
    assert mid.live[5:] == received.live[4:]
    end = received.insert(rec, received.count)
    assert end.live[-1] == rec
    with pytest.raises(IndexError):
        received.insert(rec, received.count + 1)
    with pytest.raises(IndexError):
        received.insert(rec, -1)


def test_remove_mirrors_game() -> None:
    received = lst("us_postgame", 0)
    assert received.count == 24
    result = received.remove(2)
    assert result.live == received.live[:2] + received.live[3:]
    assert result.count == 23
    assert result.slots[23] == received.slots[23]
    assert result.slots[22] == received.slots[23]
    with pytest.raises(IndexError):
        received.remove(24)
    with pytest.raises(IndexError):
        lst("us_superkiefer", 0).remove(6)


def test_stale_never_revived() -> None:
    received = lst("us_superkiefer", 0)
    original = received.slots
    assert received.count == 6

    removed = received.remove(0)
    assert removed.count == 5
    assert removed.live == received.live[1:]
    assert removed.slots == original[1:6] + original[5:]

    new = foreign(removed)
    inserted = removed.insert(new)
    assert inserted.count == 6
    assert inserted.live == (new, *received.live[1:])
    assert inserted.slots == (new.raw, *original[1:])

    moved = inserted.move(0, 3)
    assert moved.count == 6
    assert moved.live == (*received.live[1:4], new, *received.live[4:6])
    assert moved.slots == (*original[1:4], new.raw, *original[4:])


def test_cap_refused() -> None:
    full = lst("us_postgame", 0)
    with pytest.raises(TabletCapError, match="24 of 24"):
        full.insert(foreign(full, "pal_postgame", 3))
    assert full == lst("us_postgame", 0)

    target = lst("pal_postgame", 3)
    others = [r for r in lst("us_postgame", 0).live if not target.contains(r)]
    assert len(others) >= 13
    assert target.insert_many(others[:3]).count == 15
    before = target
    with pytest.raises(TabletCapError):
        target.insert_many(others[:13])
    assert target == before


def test_insert_many_order_and_atomic_duplicates() -> None:
    target = lst("pal_postgame", 3)
    others = [r for r in lst("us_postgame", 0).live if not target.contains(r)][:3]
    result = target.insert_many(others, 2)
    assert result.live[2:5] == tuple(others)
    assert result.live[5:] == target.live[2:]
    with pytest.raises(DuplicateTabletError):
        target.insert_many([others[0], others[0]])
    with pytest.raises(DuplicateTabletError):
        target.insert_many([others[0], target.live[0]])


def test_duplicate_refused() -> None:
    received = lst("pal_superkiefer", 3)
    rec = received.live[0]
    changed = rec.with_clear_count(rec.clear_count + 1)
    assert received.contains(changed)
    with pytest.raises(DuplicateTabletError):
        received.insert(changed)


def test_move_reorders() -> None:
    received = lst("pal_superkiefer", 3)
    moved = received.move(0, 5)
    assert moved.live[5] == received.live[0]
    assert moved.count == received.count
    assert moved.move(5, 0).live == received.live
    with pytest.raises(IndexError):
        received.move(0, received.count)
    with pytest.raises(IndexError):
        received.move(received.count, 0)
    assert received.move(2, 2).live == received.live


def test_move_in_full_list() -> None:
    full = lst("us_postgame", 0)
    moved = full.move(0, 23)
    assert moved.count == 24
    assert moved.live[23] == full.live[0]
    assert moved.live[:23] == full.live[1:]
