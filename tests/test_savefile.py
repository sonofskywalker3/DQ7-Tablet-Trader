import pytest
from conftest import ALL_SAVES, load_fixture

from dq7tt.checksum import compute_checksum, stored_checksum
from dq7tt.constants import HERO_NAME_OFFSET, RECEIVED_COUNT_OFFSET
from dq7tt.errors import CorruptSaveError
from dq7tt.savefile import SaveFile, SlotRole, role_from_filename
from dq7tt.tablet_list import ReceivedList

EXPECTED_COUNTS = {
    "us_superkiefer": (6, 24, 24, 23),
    "us_postgame": (24, 24, 24, 23),
    "pal_superkiefer": (21, 24, 24, 9),
    "pal_postgame": (24, 24, 24, 12),
}
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600


def test_round_trip_is_byte_identical(save_bytes: bytes) -> None:
    save = SaveFile.from_bytes(save_bytes)
    assert save.to_bytes() == save_bytes
    assert save.with_received(save.received).to_bytes() == save_bytes


def test_all_fixtures_checksum_ok(save_bytes: bytes) -> None:
    assert SaveFile.from_bytes(save_bytes).checksum_ok


def test_labels() -> None:
    save = SaveFile.from_bytes(load_fixture("us_superkiefer", 1))
    assert save.hero_name == "Auster"
    low = 135 * SECONDS_PER_HOUR + 43 * SECONDS_PER_MINUTE
    assert low <= save.playtime_seconds < low + SECONDS_PER_MINUTE
    assert save.game_cleared is False
    assert SaveFile.from_bytes(load_fixture("us_postgame", 1)).game_cleared is True
    assert len(SaveFile.from_bytes(load_fixture("pal_superkiefer", 3)).received.live) == 9


@pytest.mark.parametrize("set_name", list(EXPECTED_COUNTS))
def test_counts_match_inventory(set_name: str) -> None:
    counts = tuple(
        len(SaveFile.from_bytes(load_fixture(set_name, i)).received.live) for i in range(4)
    )
    assert counts == EXPECTED_COUNTS[set_name]


def test_selfmade_count_readable(save_bytes: bytes) -> None:
    assert 0 <= SaveFile.from_bytes(save_bytes).selfmade_count <= 16


@pytest.mark.parametrize(
    ("name", "role"),
    [
        ("save000.bin", SlotRole.QUICK_SAVE),
        ("save001.bin", SlotRole.LOG_1),
        ("save002.bin", SlotRole.LOG_2),
        ("save003.bin", SlotRole.LOG_3),
        ("SAVE002.BIN", SlotRole.LOG_2),
        ("foo.bin", SlotRole.UNKNOWN),
    ],
)
def test_role_from_filename(name: str, role: SlotRole) -> None:
    assert role_from_filename(name) == role


def test_load_from_path_sets_role() -> None:
    save = SaveFile.load(ALL_SAVES[1])
    assert save.role == SlotRole.LOG_1
    assert save.to_bytes() == ALL_SAVES[1].read_bytes()


def test_bad_input_checksum_loads_and_is_fixed_on_write() -> None:
    raw = bytearray(load_fixture("us_superkiefer", 1))
    raw[0] ^= 0xFF
    save = SaveFile.from_bytes(bytes(raw))
    assert save.checksum_ok is False
    out = save.with_received(save.received).to_bytes()
    assert stored_checksum(out) == compute_checksum(out)
    assert SaveFile.from_bytes(out).checksum_ok


def test_count_over_cap_is_corrupt() -> None:
    raw = bytearray(load_fixture("us_superkiefer", 1))
    raw[RECEIVED_COUNT_OFFSET] = 25
    save = SaveFile.from_bytes(bytes(raw))
    with pytest.raises(CorruptSaveError):
        _ = save.received


def test_hero_name_bad_utf8() -> None:
    raw = bytearray(load_fixture("us_superkiefer", 1))
    raw[HERO_NAME_OFFSET : HERO_NAME_OFFSET + 4] = b"\xff\xfeAB"
    assert isinstance(SaveFile.from_bytes(bytes(raw)).hero_name, str)


def test_with_received_preserves_high_count_bytes() -> None:
    raw = bytearray(load_fixture("us_superkiefer", 1))
    raw[RECEIVED_COUNT_OFFSET + 1] = 0x7E
    save = SaveFile.from_bytes(bytes(raw))
    out = save.with_received(save.received).to_bytes()
    assert out[RECEIVED_COUNT_OFFSET + 1] == 0x7E


def test_received_list_survives_save_round_trip() -> None:
    save = SaveFile.from_bytes(load_fixture("us_superkiefer", 0))
    donor = ReceivedList.from_save_bytes(load_fixture("us_postgame", 0))
    new = next(r for r in donor.live if not save.received.contains(r))
    edited = save.received.insert(new)
    again = SaveFile.from_bytes(save.with_received(edited).to_bytes())
    assert again.received.live == edited.live
    assert again.received == edited
