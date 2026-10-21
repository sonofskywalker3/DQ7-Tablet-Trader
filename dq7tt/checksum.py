"""Save checksum: signed-byte sum of everything after the header, stored as a u32 at 0."""

from dq7tt.constants import (
    BYTE_RANGE,
    BYTE_SIGN_BIT,
    CHECKSUM_BYTES,
    CHECKSUM_OFFSET,
    CHECKSUM_START,
    U32_MASK,
)


def compute_checksum(data: bytes) -> int:
    """Sum data[CHECKSUM_START:] with each byte read as int8, modulo 2**32."""
    unsigned = sum(data[CHECKSUM_START:])
    negatives = sum(1 for b in data[CHECKSUM_START:] if b & BYTE_SIGN_BIT)
    return (unsigned - negatives * BYTE_RANGE) & U32_MASK


def stored_checksum(data: bytes) -> int:
    """Read the little-endian u32 checksum stored in the file."""
    return int.from_bytes(data[CHECKSUM_OFFSET : CHECKSUM_OFFSET + CHECKSUM_BYTES], "little")


def apply_checksum(data: bytearray) -> None:
    """Recompute the checksum and write it into the buffer in place."""
    data[CHECKSUM_OFFSET : CHECKSUM_OFFSET + CHECKSUM_BYTES] = compute_checksum(
        bytes(data)
    ).to_bytes(CHECKSUM_BYTES, "little")
