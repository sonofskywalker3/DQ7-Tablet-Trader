"""The received-tablet list: 24 raw slots plus a count, edited the way the game edits it."""

from collections.abc import Sequence
from dataclasses import dataclass

from dq7tt.constants import (
    RECEIVED_COUNT_OFFSET,
    RECEIVED_OFFSET,
    RECEIVED_RECORD_SIZE,
    RECEIVED_SLOTS,
)
from dq7tt.errors import CorruptSaveError, DuplicateTabletError, TabletCapError
from dq7tt.tablets import TabletRecord


@dataclass(frozen=True)
class ReceivedList:
    """Exactly RECEIVED_SLOTS raw records, of which the first `count` are live.

    Slots past the count are stale leftovers; they are kept byte for byte, as the game does.
    """

    slots: tuple[bytes, ...]
    count: int

    def __post_init__(self) -> None:
        if len(self.slots) != RECEIVED_SLOTS or any(
            len(s) != RECEIVED_RECORD_SIZE for s in self.slots
        ):
            raise CorruptSaveError(
                f"received list needs {RECEIVED_SLOTS} slots of {RECEIVED_RECORD_SIZE} bytes"
            )
        if not 0 <= self.count <= RECEIVED_SLOTS:
            raise CorruptSaveError(
                f"received tablet count {self.count} is outside 0..{RECEIVED_SLOTS}"
            )

    @classmethod
    def from_save_bytes(cls, data: bytes) -> "ReceivedList":
        count = data[RECEIVED_COUNT_OFFSET]
        if count > RECEIVED_SLOTS:
            raise CorruptSaveError(
                f"received tablet count is {count}, more than the {RECEIVED_SLOTS} slots"
            )
        slots = tuple(
            bytes(
                data[
                    RECEIVED_OFFSET + i * RECEIVED_RECORD_SIZE : RECEIVED_OFFSET
                    + (i + 1) * RECEIVED_RECORD_SIZE
                ]
            )
            for i in range(RECEIVED_SLOTS)
        )
        return cls(slots=slots, count=count)

    @property
    def live(self) -> tuple[TabletRecord, ...]:
        return tuple(TabletRecord(s) for s in self.slots[: self.count])

    @property
    def free(self) -> int:
        return RECEIVED_SLOTS - self.count

    def contains(self, record: TabletRecord) -> bool:
        return any(r.identity == record.identity for r in self.live)

    def insert(self, record: TabletRecord, index: int = 0) -> "ReceivedList":
        return self.insert_many([record], index)

    def insert_many(self, records: Sequence[TabletRecord], index: int = 0) -> "ReceivedList":
        """Insert all records starting at `index`, in order, or change nothing."""
        if not 0 <= index <= self.count:
            raise IndexError(f"insert position {index} is outside 0..{self.count}")
        if len(records) > self.free:
            raise TabletCapError(
                f"This adventure log has {self.count} of {RECEIVED_SLOTS} tablets; "
                f"{len(records)} more will not fit."
            )
        seen = {r.identity for r in self.live}
        for record in records:
            if record.identity in seen:
                raise DuplicateTabletError("That tablet is already in this adventure log.")
            seen.add(record.identity)
        slots = list(self.slots)
        count = self.count
        for offset, record in enumerate(records):
            at = index + offset
            # Shift at..count-1 down one; the slot at `count` is overwritten.
            slots[at + 1 : count + 1] = slots[at:count]
            slots[at] = record.raw
            count += 1
        return ReceivedList(slots=tuple(slots), count=count)

    def remove(self, index: int) -> "ReceivedList":
        if not 0 <= index < self.count:
            raise IndexError(f"tablet position {index} is outside 0..{self.count - 1}")
        slots = list(self.slots)
        # Shift index+1..count-1 up one; slot count-1 keeps its old record, as in the game.
        slots[index : self.count - 1] = slots[index + 1 : self.count]
        return ReceivedList(slots=tuple(slots), count=self.count - 1)

    def move(self, src: int, dst: int) -> "ReceivedList":
        """Remove the tablet at `src`, then insert it at `dst` (a post-removal position)."""
        if not 0 <= src < self.count:
            raise IndexError(f"tablet position {src} is outside 0..{self.count - 1}")
        if not 0 <= dst < self.count:
            raise IndexError(f"destination {dst} is outside 0..{self.count - 1}")
        record = TabletRecord(self.slots[src])
        return self.remove(src).insert(record, dst)
