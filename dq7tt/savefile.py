"""One saveNNN.bin: labels, the received tablet list, and writing an edited list back."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from dq7tt.checksum import apply_checksum, compute_checksum, stored_checksum
from dq7tt.chunks import check_layout
from dq7tt.constants import (
    GAME_CLEARED_OFFSET,
    GAME_CLEARED_VALUE,
    HERO_NAME_OFFSET,
    HERO_NAME_SIZE,
    PLAYTIME_FPS,
    PLAYTIME_OFFSET,
    RECEIVED_COUNT_OFFSET,
    RECEIVED_OFFSET,
    RECEIVED_RECORD_SIZE,
    SAVE_FILENAMES,
    SELFMADE_COUNT_OFFSET,
    U32_BYTES,
)
from dq7tt.tablet_list import ReceivedList


class SlotRole(StrEnum):
    QUICK_SAVE = "quick save"
    LOG_1 = "adventure log 1"
    LOG_2 = "adventure log 2"
    LOG_3 = "adventure log 3"
    UNKNOWN = "unknown"


# The one filename <-> role mapping; the reverse is derived from it.
ROLE_FILENAMES: dict[SlotRole, str] = dict(
    zip(
        (SlotRole.QUICK_SAVE, SlotRole.LOG_1, SlotRole.LOG_2, SlotRole.LOG_3),
        SAVE_FILENAMES,
        strict=True,
    )
)
_ROLES_BY_FILENAME = {name: role for role, name in ROLE_FILENAMES.items()}


def role_from_filename(name: str) -> SlotRole:
    return _ROLES_BY_FILENAME.get(name.lower(), SlotRole.UNKNOWN)


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + U32_BYTES], "little")


@dataclass(frozen=True)
class SaveFile:
    data: bytes
    role: SlotRole = SlotRole.UNKNOWN

    @classmethod
    def from_bytes(cls, data: bytes, role: SlotRole = SlotRole.UNKNOWN) -> "SaveFile":
        check_layout(data)
        return cls(data=bytes(data), role=role)

    @classmethod
    def load(cls, path: Path) -> "SaveFile":
        return cls.from_bytes(path.read_bytes(), role_from_filename(path.name))

    @property
    def checksum_ok(self) -> bool:
        return stored_checksum(self.data) == compute_checksum(self.data)

    @property
    def hero_name(self) -> str:
        raw = self.data[HERO_NAME_OFFSET : HERO_NAME_OFFSET + HERO_NAME_SIZE]
        return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")

    @property
    def playtime_seconds(self) -> int:
        return _u32(self.data, PLAYTIME_OFFSET) // PLAYTIME_FPS

    @property
    def game_cleared(self) -> bool:
        return _u32(self.data, GAME_CLEARED_OFFSET) == GAME_CLEARED_VALUE

    @property
    def received(self) -> ReceivedList:
        return ReceivedList.from_save_bytes(self.data)

    @property
    def selfmade_count(self) -> int:
        return self.data[SELFMADE_COUNT_OFFSET]

    def with_received(self, lst: ReceivedList) -> "SaveFile":
        """Write all slots and the count byte, then refresh the checksum."""
        buf = bytearray(self.data)
        for i, slot in enumerate(lst.slots):
            start = RECEIVED_OFFSET + i * RECEIVED_RECORD_SIZE
            buf[start : start + RECEIVED_RECORD_SIZE] = slot
        buf[RECEIVED_COUNT_OFFSET] = lst.count
        apply_checksum(buf)
        return SaveFile(data=bytes(buf), role=self.role)

    def to_bytes(self) -> bytes:
        return self.data
