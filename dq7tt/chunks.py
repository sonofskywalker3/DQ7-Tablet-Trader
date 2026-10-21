"""Top-level chunk chain of a save, and the layout check built on it."""

import struct
from collections.abc import Iterator
from dataclasses import dataclass

from dq7tt.constants import (
    CHUNK_ALIGN,
    CHUNK_CHAIN_START,
    CHUNK_HEADER_FORMAT,
    CHUNK_HEADER_SIZE,
    CHUNK_TAG_SIZE,
    EXPECTED_CHUNK_TAGS,
    IMIN_OFFSET,
    IMIN_TAG,
    IMIN_VERSION,
    JAPANESE_SAVE_MESSAGE,
    SAVE_SIZE,
    SURE_OFFSET,
    SURE_SIZE,
    SURE_TAG,
    SURE_VERSION,
)
from dq7tt.errors import JapaneseSaveError, UnsupportedLayoutError


@dataclass(frozen=True)
class Chunk:
    """One top-level chunk: its tag, header version, file offset and size (from the tag)."""

    tag: str
    version: int
    offset: int
    size: int


def _is_tag(raw: bytes) -> bool:
    return len(raw) == CHUNK_TAG_SIZE and raw.isalpha() and raw.isupper() and raw.isascii()


def _align(value: int) -> int:
    return (value + CHUNK_ALIGN - 1) // CHUNK_ALIGN * CHUNK_ALIGN


def _walk(data: bytes) -> Iterator[Chunk]:
    """Yield chunks one by one; raise UnsupportedLayoutError at the first malformed spot."""
    if len(data) != SAVE_SIZE:
        raise UnsupportedLayoutError(
            f"Unexpected file size {len(data):#x}; expected {SAVE_SIZE:#x}."
        )
    pos = CHUNK_CHAIN_START
    while pos < len(data):
        if data[pos] == 0:  # zero gap between chunks
            pos += 1
            continue
        if pos + CHUNK_HEADER_SIZE > len(data):
            raise UnsupportedLayoutError(f"Truncated chunk header at {pos:#x}.")
        raw_tag, _flags, version, size = struct.unpack_from(CHUNK_HEADER_FORMAT, data, pos)
        if not _is_tag(raw_tag):
            raise UnsupportedLayoutError(f"No chunk header at {pos:#x}.")
        if size < CHUNK_HEADER_SIZE or pos + size > len(data):
            raise UnsupportedLayoutError(f"Bad chunk size {size:#x} at {pos:#x}.")
        yield Chunk(raw_tag.decode("ascii"), version, pos, size)
        pos = _align(pos + size)


def parse_chunks(data: bytes) -> list[Chunk]:
    """Return the top-level chunk chain, or raise UnsupportedLayoutError if it is malformed."""
    return list(_walk(data))


def check_layout(data: bytes) -> list[Chunk]:
    """Return the chunk chain if it is the known Western layout, else raise.

    A chain whose tags match up to SURE but whose SURE chunk differs in position, version or
    size raises JapaneseSaveError. That heuristic is UNVERIFIED: no Japanese save was
    available, it only reflects the expectation that the Japanese tablet section differs.
    Any other mismatch raises UnsupportedLayoutError.
    """
    chunks: list[Chunk] = []
    for chunk in _walk(data):
        index = len(chunks)
        if index >= len(EXPECTED_CHUNK_TAGS) or chunk.tag != EXPECTED_CHUNK_TAGS[index]:
            raise UnsupportedLayoutError(f"Unexpected chunk {chunk.tag!r} at {chunk.offset:#x}.")
        if chunk.tag == SURE_TAG and (
            (chunk.offset, chunk.version, chunk.size) != (SURE_OFFSET, SURE_VERSION, SURE_SIZE)
        ):
            raise JapaneseSaveError(JAPANESE_SAVE_MESSAGE)
        if chunk.tag == IMIN_TAG and (chunk.offset, chunk.version) != (IMIN_OFFSET, IMIN_VERSION):
            raise UnsupportedLayoutError(
                f"Unexpected IMIN chunk (offset {chunk.offset:#x}, version {chunk.version})."
            )
        chunks.append(chunk)
    if [c.tag for c in chunks] != list(EXPECTED_CHUNK_TAGS):
        raise UnsupportedLayoutError("The chunk chain is incomplete.")
    return chunks
