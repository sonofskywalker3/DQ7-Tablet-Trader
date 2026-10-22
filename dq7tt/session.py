"""The editing session: up to two open saves, all-or-nothing edits, undo, and safe writes."""

import logging
from collections.abc import Sequence
from pathlib import Path

from dq7tt.bank import Bank, BankList, BankTablet
from dq7tt.errors import DuplicateTabletError, SessionError
from dq7tt.savefile import SaveFile, SlotRole
from dq7tt.session_core import OpenSource, SessionCore, Target
from dq7tt.session_ops import record_at, role_name, tablet_name
from dq7tt.tablet_list import ReceivedList
from dq7tt.tablets import TabletRecord

__all__ = ["OpenSource", "Session", "Target"]

log = logging.getLogger(__name__)

NO_CLEARS = 0
SINGLE = 1
SELFMADE_REFUSED = "Self-made tablets can be banked but not added to a save yet."
NOTHING_SELECTED = "Select at least one tablet first."
PICKED_TWICE = "The same tablet was picked twice."
NOT_CLEARED = "That tablet has not been cleared."
NONE_CLEARED = "None of those tablets have been cleared."
Changes = dict[tuple[int, SlotRole], SaveFile]


class Session(SessionCore):
    """Everything the app edits goes through here; every edit is validated first and undoable.

    Operations on several tablets at once either fit entirely or change nothing, and are one
    undo step.
    """

    # Adding

    def add_from_database(self, target: Target, name_en: str, index: int = 0) -> None:
        record = self._db.by_name(name_en).record
        self._insert(target, [record], index, frozenset(), [tablet_name(record, self._db)])

    def add_from_bank(self, target: Target, bank_tablet: BankTablet, index: int = 0) -> None:
        self.add_many_from_bank(target, [bank_tablet], index)

    def add_many_from_bank(
        self, target: Target, bank_tablets: Sequence[BankTablet], index: int = 0
    ) -> None:
        """Add banked tablets in the given order starting at `index`, all or none."""
        if not bank_tablets:
            raise SessionError(NOTHING_SELECTED)
        if any(t.list_kind is not BankList.RECEIVED for t in bank_tablets):
            raise SessionError(SELFMADE_REFUSED)
        records = [TabletRecord(t.record_raw) for t in bank_tablets]
        extra = frozenset(t.identity for t in bank_tablets if t.from_real_save)
        self._insert(target, records, index, extra, [t.name for t in bank_tablets])

    # Changing one log

    def remove(self, target: Target, slot: int) -> None:
        self.remove_many(target, [slot])

    def remove_many(self, target: Target, slots: Sequence[int]) -> None:
        """Take the tablets at `slots` out of one log; one step, all or none."""
        save = self._save(target)
        records = self._picked(save, slots)
        lst = save.received
        for slot in sorted(slots, reverse=True):
            lst = lst.remove(slot)
        what = self._what([tablet_name(r, self._db) for r in records])
        self._apply(
            {self._key(target): save.with_received(lst)},
            f"Remove {what} from {role_name(target.role)}",
        )

    def move(self, target: Target, src: int, dst: int) -> None:
        save = self._save(target)
        name = tablet_name(record_at(save, src), self._db)
        new = save.with_received(save.received.move(src, dst))
        self._apply({self._key(target): new}, f"Reorder {name} in {role_name(target.role)}")

    def reset_clears(self, target: Target, slot: int) -> None:
        self.reset_clears_many(target, [slot])

    def reset_clears_many(self, target: Target, slots: Sequence[int]) -> None:
        """Set the clear counts of the picked tablets to 0, skipping uncleared ones; one step."""
        save = self._save(target)
        records = self._picked(save, slots)
        cleared = [
            (slot, record)
            for slot, record in zip(slots, records, strict=True)
            if record.clear_count != NO_CLEARS or not record.clear_counts_agree
        ]
        if not cleared:
            raise SessionError(NOT_CLEARED if len(slots) == SINGLE else NONE_CLEARED)
        lst = save.received
        raw = list(lst.slots)
        for slot, record in cleared:
            raw[slot] = record.with_clear_count(NO_CLEARS).raw
        new = save.with_received(ReceivedList(slots=tuple(raw), count=lst.count))
        names = [tablet_name(record, self._db) for _, record in cleared]
        what = self._what(names)
        noun = "clear count" if len(names) == SINGLE else "clear counts"
        self._apply({self._key(target): new}, f"Reset {noun} of {what} in {role_name(target.role)}")

    # Copying and moving between logs

    def copy(
        self, src: Target, slot: int, dst: Target, index: int = 0, reset_clears: bool = False
    ) -> None:
        self.copy_many(src, [slot], dst, index, reset_clears)

    def copy_many(
        self,
        src: Target,
        slots: Sequence[int],
        dst: Target,
        index: int = 0,
        reset_clears: bool = False,
    ) -> None:
        """Copy the tablets at `slots`, in that order, into `dst` at `index`; all or none."""
        changes, extra, what = self._copy_changes(src, slots, dst, index, reset_clears)
        label = f"Copy {what} from {role_name(src.role)} to {role_name(dst.role)}"
        self._apply(changes, label, extra)

    def move_to(
        self, src: Target, slot: int, dst: Target, index: int = 0, reset_clears: bool = False
    ) -> None:
        self.move_many(src, [slot], dst, index, reset_clears)

    def move_many(
        self,
        src: Target,
        slots: Sequence[int],
        dst: Target,
        index: int = 0,
        reset_clears: bool = False,
    ) -> None:
        """Like copy_many, then take the tablets out of `src`; one step, all or none."""
        if self._key(src) == self._key(dst):
            raise SessionError("Use reorder to move a tablet within the same adventure log.")
        changes, extra, what = self._copy_changes(src, slots, dst, index, reset_clears)
        before = self._save(src)
        lst = before.received
        for slot in sorted(slots, reverse=True):
            lst = lst.remove(slot)
        changes[self._key(src)] = before.with_received(lst)
        label = f"Move {what} from {role_name(src.role)} to {role_name(dst.role)}"
        self._apply(changes, label, extra)

    # The bank

    def bank_from(self, target: Target, slot: int, bank: Bank, folder: str) -> Path:
        """Copy one tablet into the bank; the session's saves are not changed."""
        record = record_at(self._save(target), slot)
        return self._bank_record(target, record, bank, folder)

    def bank_all(self, target: Target, bank: Bank, folder: str) -> list[Path]:
        """Copy every tablet of one log into the bank, skipping ones already in that folder."""
        added: list[Path] = []
        for record in self._save(target).received.live:
            try:
                added.append(self._bank_record(target, record, bank, folder))
            except DuplicateTabletError:
                log.debug("%s is already in the bank folder", tablet_name(record, self._db))
        return added

    # Internals

    def _bank_record(self, target: Target, record: TabletRecord, bank: Bank, folder: str) -> Path:
        source = self._source(target.source_id)
        from_real = self._is_real(record)
        return bank.add(record, folder, self._db, source.label, source.region.value, from_real)

    def _picked(self, save: SaveFile, slots: Sequence[int]) -> list[TabletRecord]:
        """The records at `slots`; refuses an empty pick, a repeat, or a slot past the end."""
        if not slots:
            raise SessionError(NOTHING_SELECTED)
        if len(set(slots)) != len(slots):
            raise SessionError(PICKED_TWICE)
        return [record_at(save, slot) for slot in slots]

    def _what(self, names: Sequence[str]) -> str:
        return names[0] if len(names) == SINGLE else f"{len(names)} tablets"

    def _insert(
        self,
        target: Target,
        records: Sequence[TabletRecord],
        index: int,
        extra: frozenset[bytes],
        names: Sequence[str],
    ) -> None:
        save = self._save(target)
        new = save.with_received(save.received.insert_many(records, index))
        label = f"Add {self._what(names)} to {role_name(target.role)}"
        self._apply({self._key(target): new}, label, extra)

    def _copy_changes(
        self, src: Target, slots: Sequence[int], dst: Target, index: int, reset_clears: bool
    ) -> tuple[Changes, frozenset[bytes], str]:
        """The new destination save, identities to allow, and the label's 'what' part."""
        if not slots:
            raise SessionError(NOTHING_SELECTED)
        source = self._save(src)
        records = [record_at(source, slot) for slot in slots]
        read = self._read_from_disk()
        extra: set[bytes] = set()
        for record in records:
            info = self._db.lookup(record)
            exact = info is not None and info.record.identity == record.identity
            # A record read from a save on disk is real, even if its database entry is untested.
            if not exact or record.identity in read:
                extra.add(record.identity)
        if reset_clears:
            records = [r.with_clear_count(NO_CLEARS) for r in records]
        target = self._save(dst)
        new = target.with_received(target.received.insert_many(records, index))
        what = self._what([tablet_name(r, self._db) for r in records])
        return {self._key(dst): new}, frozenset(extra), what
