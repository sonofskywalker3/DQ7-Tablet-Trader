"""Received-tablet records: a thin, immutable view over the raw 0x54 bytes."""

import struct
from dataclasses import dataclass
from enum import StrEnum

from dq7tt.constants import (
    MAP_ID_FORMAT,
    MAX_CLEAR_COUNT,
    REC_CLEAR_1,
    REC_CLEAR_2,
    REC_MAP_ID,
    REC_SERIAL,
    REC_STREETPASS_FIELDS,
    RECEIVED_RECORD_SIZE,
)
from dq7tt.errors import CorruptSaveError


class TabletKind(StrEnum):
    DLC = "dlc"
    STORY = "story"
    RESIDENT = "resident"
    STREETPASS = "streetpass"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TabletRecord:
    raw: bytes

    def __post_init__(self) -> None:
        if len(self.raw) != RECEIVED_RECORD_SIZE:
            raise CorruptSaveError(
                f"tablet record is {len(self.raw)} bytes, expected {RECEIVED_RECORD_SIZE}"
            )

    @property
    def map_id(self) -> int:
        return int(struct.unpack_from(MAP_ID_FORMAT, self.raw, REC_MAP_ID)[0])

    @property
    def serial(self) -> int:
        return self.raw[REC_SERIAL]

    @property
    def clear_count(self) -> int:
        return self.raw[REC_CLEAR_1]

    @property
    def clear_counts_agree(self) -> bool:
        return self.raw[REC_CLEAR_1] == self.raw[REC_CLEAR_2]

    @property
    def identity(self) -> bytes:
        data = bytearray(self.raw)
        data[REC_CLEAR_1] = 0
        data[REC_CLEAR_2] = 0
        return bytes(data)

    @property
    def looks_streetpass(self) -> bool:
        return any(self.raw[REC_STREETPASS_FIELDS])

    def with_clear_count(self, n: int) -> "TabletRecord":
        if not 0 <= n <= MAX_CLEAR_COUNT:
            raise ValueError(f"clear count {n} outside 0..{MAX_CLEAR_COUNT}")
        data = bytearray(self.raw)
        data[REC_CLEAR_1] = n
        data[REC_CLEAR_2] = n
        return TabletRecord(bytes(data))
