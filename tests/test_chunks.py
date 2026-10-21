import struct

import pytest
from conftest import load_fixture

from dq7tt.chunks import check_layout, parse_chunks
from dq7tt.constants import (
    EXPECTED_CHUNK_TAGS,
    IMIN_OFFSET,
    IMIN_VERSION,
    JAPANESE_SAVE_MESSAGE,
    SAVE_SIZE,
    SURE_OFFSET,
    SURE_SIZE,
    SURE_VERSION,
)
from dq7tt.errors import JapaneseSaveError, UnsupportedLayoutError

VERSION_FIELD = 6
SIZE_FIELD = 8
JP_SURE_SIZE = 0xD58
CHANGED_IMIN_VERSION = 5
SHORT_SIZE = 0x4FFF
OVERRUN_SIZE = 0xFFFFFF
LAST_TAG = "SILS"


def test_chunk_chain_on_every_fixture(save_bytes: bytes) -> None:
    chunks = check_layout(save_bytes)
    assert [c.tag for c in chunks] == list(EXPECTED_CHUNK_TAGS)
    assert chunks == parse_chunks(save_bytes)
    by_tag = {c.tag: c for c in chunks}
    assert (by_tag["SURE"].offset, by_tag["SURE"].version, by_tag["SURE"].size) == (
        SURE_OFFSET,
        SURE_VERSION,
        SURE_SIZE,
    )
    assert (by_tag["IMIN"].offset, by_tag["IMIN"].version) == (IMIN_OFFSET, IMIN_VERSION)


def test_wrong_size_rejected() -> None:
    with pytest.raises(UnsupportedLayoutError):
        check_layout(load_fixture("us_postgame", 0)[:SHORT_SIZE])


def test_random_bytes_rejected() -> None:
    with pytest.raises(UnsupportedLayoutError):
        check_layout(bytes(range(256)) * (SAVE_SIZE // 256))


def test_japanese_like_layout_rejected() -> None:
    data = bytearray(load_fixture("us_postgame", 0))
    struct.pack_into("<I", data, SURE_OFFSET + SIZE_FIELD, JP_SURE_SIZE)
    with pytest.raises(JapaneseSaveError) as exc:
        check_layout(bytes(data))
    assert str(exc.value) == JAPANESE_SAVE_MESSAGE

    data = bytearray(load_fixture("us_postgame", 0))
    struct.pack_into("<H", data, SURE_OFFSET + VERSION_FIELD, 2)
    with pytest.raises(JapaneseSaveError):
        check_layout(bytes(data))


def test_other_layout_change_rejected() -> None:
    data = bytearray(load_fixture("us_postgame", 0))
    struct.pack_into("<H", data, IMIN_OFFSET + VERSION_FIELD, CHANGED_IMIN_VERSION)
    with pytest.raises(UnsupportedLayoutError) as exc:
        check_layout(bytes(data))
    assert not isinstance(exc.value, JapaneseSaveError)


@pytest.mark.parametrize("tag", [LAST_TAG, "SURE"])
def test_chunk_size_past_end_of_file_rejected(tag: str) -> None:
    data = bytearray(load_fixture("us_postgame", 0))
    chunk = next(c for c in parse_chunks(bytes(data)) if c.tag == tag)
    struct.pack_into("<I", data, chunk.offset + SIZE_FIELD, OVERRUN_SIZE)
    assert len(data) == SAVE_SIZE
    with pytest.raises(UnsupportedLayoutError):
        check_layout(bytes(data))
