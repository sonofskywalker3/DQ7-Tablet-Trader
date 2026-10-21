import pytest
from conftest import ALL_SAVES, load_fixture

from dq7tt.checksum import apply_checksum, compute_checksum, stored_checksum
from dq7tt.constants import SAVE_SIZE


@pytest.mark.parametrize("path", ALL_SAVES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_stored_checksum_matches_on_every_fixture(path) -> None:
    b = path.read_bytes()
    assert compute_checksum(b) == stored_checksum(b)


def test_checksum_reads_bytes_as_signed() -> None:
    buf = bytearray(SAVE_SIZE)
    buf[0x20] = 0xFF
    assert compute_checksum(bytes(buf)) == 0xFFFFFFFF
    buf[0x21] = 0x02
    assert compute_checksum(bytes(buf)) == 1


def test_checksum_ignores_header_bytes() -> None:
    buf = bytearray(load_fixture("us_postgame", 0))
    before = compute_checksum(bytes(buf))
    for i in range(0x04, 0x10):
        buf[i] ^= 0xFF
    assert compute_checksum(bytes(buf)) == before


def test_apply_checksum_fixes_edited_file() -> None:
    buf = bytearray(load_fixture("us_superkiefer", 1))
    buf[0x3700] ^= 0xFF
    assert stored_checksum(bytes(buf)) != compute_checksum(bytes(buf))
    apply_checksum(buf)
    assert stored_checksum(bytes(buf)) == compute_checksum(bytes(buf))
