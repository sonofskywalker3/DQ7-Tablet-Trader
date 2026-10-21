import pytest
from conftest import load_fixture

from dq7tt.constants import (
    REC_SERIAL,
    RECEIVED_COUNT_OFFSET,
    RECEIVED_OFFSET,
    RECEIVED_RECORD_SIZE,
)
from dq7tt.errors import CorruptSaveError
from dq7tt.tablets import TabletKind, TabletRecord

WRONG_LENGTH = 0x53
MAGIC_MAP_ID = 0x126
MAX_DLC_SERIAL = 0x4A


def record(set_name: str, save: int, slot: int) -> TabletRecord:
    data = load_fixture(set_name, save)
    start = RECEIVED_OFFSET + slot * RECEIVED_RECORD_SIZE
    return TabletRecord(data[start : start + RECEIVED_RECORD_SIZE])


def test_identity_ignores_clear_count() -> None:
    a = record("us_postgame", 0, 4)
    b = record("us_postgame", 1, 0)
    assert a.identity == b.identity
    assert a.raw != b.raw


def test_clear_count_read_and_set() -> None:
    a = record("us_postgame", 0, 4)
    b = record("us_postgame", 1, 0)
    assert a.clear_count == 1
    assert a.clear_counts_agree
    assert a.with_clear_count(0).raw == b.raw


def test_clear_count_range() -> None:
    a = record("us_postgame", 0, 4)
    for bad in (-1, 256):
        with pytest.raises(ValueError):
            a.with_clear_count(bad)
    assert a.with_clear_count(255).clear_count == 255


def test_wrong_length_rejected() -> None:
    with pytest.raises(CorruptSaveError):
        TabletRecord(b"\0" * WRONG_LENGTH)


def test_serial_and_map_id() -> None:
    a = record("us_superkiefer", 1, 6)
    b = record("us_superkiefer", 1, 17)
    assert a.map_id == MAGIC_MAP_ID
    assert b.map_id == MAGIC_MAP_ID
    assert a.serial != b.serial


def test_streetpass_and_kind() -> None:
    assert not TabletRecord(b"\0" * RECEIVED_RECORD_SIZE).looks_streetpass
    assert TabletRecord(b"\1" + b"\0" * (RECEIVED_RECORD_SIZE - 1)).looks_streetpass
    assert {k.name for k in TabletKind} == {"DLC", "STORY", "RESIDENT", "STREETPASS", "UNKNOWN"}


def test_serial_is_one_byte() -> None:
    raw = bytearray(RECEIVED_RECORD_SIZE)
    raw[REC_SERIAL] = 0x2A
    raw[REC_SERIAL + 1 : REC_SERIAL + 4] = b"\xff\xff\xff"
    assert TabletRecord(bytes(raw)).serial == 0x2A


def test_live_serials_in_range(save_bytes: bytes) -> None:
    count = save_bytes[RECEIVED_COUNT_OFFSET]
    for i in range(count):
        start = RECEIVED_OFFSET + i * RECEIVED_RECORD_SIZE
        rec = TabletRecord(save_bytes[start : start + RECEIVED_RECORD_SIZE])
        assert rec.serial <= MAX_DLC_SERIAL
