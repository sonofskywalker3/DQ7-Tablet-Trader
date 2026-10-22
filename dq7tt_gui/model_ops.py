"""The window's tablet commands: copy, move, remove, reset, reorder and drag and drop."""

import logging
from collections.abc import Callable, Sequence
from functools import partial

from dq7tt.bank import BankList
from dq7tt.errors import DuplicateTabletError, SaveIOError, SessionError, TabletTraderError
from dq7tt.session import Target
from dq7tt.session_ops import role_name
from dq7tt.tablets import TabletRecord
from dq7tt_gui.model_base import BANK_KIND, NOTHING_SELECTED, ModelBase
from dq7tt_gui.model_text import (
    BANK_MOVE_TO_LOG,
    BANK_WRITE,
    already_in,
    not_banked,
    stayed_in,
)
from dq7tt_gui.model_views import folder_label, what
from dq7tt_gui.viewmodels import Confirm, Destination, Notice, NoticeKind, Outcome, PaneSide

log = logging.getLogger(__name__)

RESET_NOTE = "One-time rewards for the first clear do not come back."
NO_OTHER_SIDE = "Open a save or show the bank on the other side first."
SELFMADE_COPY = "Self-made tablets cannot be copied to another bank folder yet."
NO_CLEARS = 0
SINGLE = 1
LAST_OFFSET = 1


def _bank_trouble(exc: SaveIOError) -> Notice:
    log.warning("could not write to the bank: %s", exc)
    return Notice(NoticeKind.ERROR, BANK_WRITE)


def _info(text: str) -> Notice:
    return Notice(NoticeKind.INFO, text)


class EditOps(ModelBase):
    """Commands that change tablets. Each returns notices, or a Confirm to accept first."""

    # Selection-based commands

    def copy_selected(self, dest: Destination, confirmed: bool = False) -> Outcome:
        return self._run(lambda: self._send_selected(dest, False, confirmed))

    def move_selected(self, dest: Destination, confirmed: bool = False) -> Outcome:
        return self._run(lambda: self._send_selected(dest, True, confirmed))

    def quick_copy(self, confirmed: bool = False) -> Outcome:
        """Copy the selection to whatever the other pane shows."""

        def act() -> Outcome:
            dest = self._quick_dest()
            if dest is None:
                raise SessionError(NO_OTHER_SIDE if self._sel_side else NOTHING_SELECTED)
            return self._send_selected(dest, False, confirmed)

        return self._run(act)

    def remove_selected(self, confirmed: bool = False) -> Outcome:
        return self._run(lambda: self._remove(confirmed))

    def reset_selected(self, confirmed: bool = False) -> Outcome:
        return self._run(lambda: self._reset(confirmed))

    # Direct commands

    def reorder(self, side: PaneSide, old: int, new: int, confirmed: bool = False) -> Outcome:
        """Move one tablet within its log so it ends up at position `new`."""
        return self._run(lambda: self._reorder(side, old, new, confirmed))

    def drop(
        self,
        src_side: PaneSide,
        indexes: Sequence[int],
        dst_side: PaneSide,
        index: int,
        confirmed: bool = False,
    ) -> Outcome:
        """A drag onto a pane: reorder within one list, copy to the other pane at `index`."""

        def act() -> Outcome:
            if src_side is dst_side:
                if self._is_bank(src_side):
                    return []
                if len(indexes) != SINGLE:
                    raise SessionError("Drag one tablet at a time to reorder.")
                return self._reorder(src_side, indexes[0], index, confirmed)
            if self._is_bank(dst_side):
                dest = self._bank_dest(self._folder)
            else:
                dest = self._log_dest(self._target(dst_side))
            again = partial(self.drop, src_side, indexes, dst_side, index, True)
            return self._send(src_side, indexes, dest, False, index, confirmed, again)

        return self._run(act)

    def import_all_to_bank(self, side: PaneSide) -> Outcome:
        """Copy every tablet of the side's log into the open bank folder, skipping repeats."""

        def act() -> Outcome:
            if self._is_bank(side):
                raise SessionError("Pick a save to copy from.")
            try:
                added = self._session.bank_all(self._target(side), self._bank, self._folder)
            except SaveIOError as exc:
                return [_bank_trouble(exc)]
            self._clear_selection()
            where = f"bank folder {folder_label(self._folder)}"
            if not added:
                return [_info(f"Every tablet of this log is already in {where}.")]
            return [_info(f"Copied {len(added)} tablets to {where}.")]

        return self._run(act)

    # Internals

    def _quick_dest(self) -> Destination | None:
        side = self._sel_side
        if side is PaneSide.LEFT:
            if self._bank_shown:
                return self._bank_dest(self._folder)
            right = self._ids[PaneSide.RIGHT]
            if right is None:
                return None
            return self._log_dest(Target(right, self._roles[PaneSide.RIGHT]), qualify=False)
        if side is PaneSide.RIGHT and self._ids[PaneSide.LEFT] is not None:
            return self._log_dest(self._target(PaneSide.LEFT), qualify=False)
        return None

    def _send_selected(self, dest: Destination, move: bool, confirmed: bool) -> Outcome:
        side = self._sel_side
        if side is None:
            raise SessionError(NOTHING_SELECTED)
        again = self.move_selected if move else self.copy_selected
        return self._send(side, self._sel, dest, move, 0, confirmed, partial(again, dest, True))

    def _send(
        self,
        side: PaneSide,
        indexes: Sequence[int],
        dest: Destination,
        move: bool,
        index: int,
        confirmed: bool,
        again: Callable[[], Outcome],
    ) -> Outcome:
        indexes = self._check_rows(side, indexes)
        if self._is_bank(side):
            if dest.kind == BANK_KIND:
                return self._bank_to_bank(indexes, str(dest.target), move)
            # Anything leaving the bank is a copy: the bank file always stays.
            if move:
                raise SessionError(BANK_MOVE_TO_LOG)
            return self._bank_to_log(indexes, dest, index, confirmed, again)
        src = self._target(side)
        if dest.kind == BANK_KIND:
            return self._save_to_bank(src, indexes, str(dest.target), move, confirmed, again)
        dst = dest.target
        if not isinstance(dst, Target) or dst == src:
            raise SessionError("Pick a different adventure log.")
        index = min(max(index, 0), self._save_of(dst).received.count)
        records = [self._save_of(src).received.live[i] for i in indexes]
        changes = {dst: self._would_insert(dst, records, index)}
        if move:
            changes[src] = self._would_remove(src, indexes)
        reasons = self._reasons(changes)
        ask = self._gate(reasons, "Move" if move else "Copy", confirmed, again)
        if ask is not None:
            return ask
        op = self._session.move_many if move else self._session.copy_many
        return self._edited(partial(op, src, indexes, dst, index), list(changes), reasons)

    def _save_to_bank(
        self,
        src: Target,
        indexes: Sequence[int],
        folder: str,
        move: bool,
        confirmed: bool,
        again: Callable[[], Outcome],
    ) -> Outcome:
        reasons = self._reasons({src: self._would_remove(src, indexes)}) if move else []
        ask = self._gate(reasons, "Move", confirmed, again)
        if ask is not None:
            return ask
        names = [name for name, _, _ in self._session.tablets(src)]
        where = f"bank folder {folder_label(folder)}"
        done: list[int] = []
        failed: list[Notice] = []
        for i in indexes:
            try:
                self._session.bank_from(src, i, self._bank, folder)
                done.append(i)
            except DuplicateTabletError:
                text = (
                    stayed_in(names[i], where, role_name(src.role))
                    if move
                    else already_in(names[i], where)
                )
                failed.append(Notice(NoticeKind.ERROR, text))
            except SaveIOError as exc:
                failed.append(_bank_trouble(exc))
            except TabletTraderError as exc:
                log.warning("could not bank %s: %s", names[i], exc)
                failed.append(Notice(NoticeKind.ERROR, not_banked(names[i], exc)))
        if not done:
            return failed
        moved = what([names[i] for i in done])
        if not move:
            self._clear_selection()
            return [_info(f"Copied {moved} to {where}."), *failed]
        try:
            warnings = self._edited(partial(self._session.remove_many, src, done), [src], reasons)
        except TabletTraderError as exc:
            log.warning("could not take banked tablets out of the log: %s", exc)
            self._clear_selection()
            note = (
                f"Copied {moved} to {where}, but could not take it out of the log. "
                f"It is still in {role_name(src.role)}."
            )
            return [Notice(NoticeKind.WARNING, note), *failed]
        return [_info(f"Moved {moved} to {where}."), *failed, *warnings]

    def _bank_to_log(
        self,
        indexes: Sequence[int],
        dest: Destination,
        index: int,
        confirmed: bool,
        again: Callable[[], Outcome],
    ) -> Outcome:
        dst = dest.target
        if not isinstance(dst, Target):
            raise SessionError("Pick an adventure log.")
        tablets = self._picked_tablets(indexes)
        index = min(max(index, 0), self._save_of(dst).received.count)
        records = [TabletRecord(t.record_raw) for t in tablets if t.list_kind is BankList.RECEIVED]
        reasons = self._reasons({dst: self._would_insert(dst, records, index)})
        ask = self._gate(reasons, "Copy", confirmed, again)
        if ask is not None:
            return ask
        add = partial(self._session.add_many_from_bank, dst, tablets, index)
        return self._edited(add, [dst], reasons)

    def _bank_to_bank(self, indexes: Sequence[int], folder: str, move: bool) -> Outcome:
        if folder == self._folder:
            raise SessionError("Pick a different bank folder.")
        tablets = self._picked_tablets(indexes)
        where = f"bank folder {folder_label(folder)}"
        if move:
            try:
                self._bank.move([t.path for t in tablets], folder)
            except DuplicateTabletError as exc:
                raise SessionError(already_in(exc.name or "A tablet", where)) from exc
            except SaveIOError as exc:
                return [_bank_trouble(exc)]
            self._clear_selection()
            return [_info(f"Moved {what([t.name for t in tablets])} to {where}.")]
        done: list[str] = []
        failed: list[Notice] = []
        for t in tablets:
            if t.list_kind is not BankList.RECEIVED:
                failed.append(Notice(NoticeKind.ERROR, SELFMADE_COPY))
                continue
            try:
                record = TabletRecord(t.record_raw)
                db = self._session.db
                self._bank.add(record, folder, db, t.source_note, t.region, t.from_real_save)
                done.append(t.name)
            except DuplicateTabletError:
                failed.append(Notice(NoticeKind.ERROR, already_in(t.name, where)))
            except SaveIOError as exc:
                failed.append(_bank_trouble(exc))
            except TabletTraderError as exc:
                log.warning("could not bank %s: %s", t.name, exc)
                failed.append(Notice(NoticeKind.ERROR, not_banked(t.name, exc)))
        if not done:
            return failed
        self._clear_selection()
        return [_info(f"Copied {what(done)} to {where}."), *failed]

    def _remove(self, confirmed: bool) -> Outcome:
        side = self._sel_side
        if side is None:
            raise SessionError(NOTHING_SELECTED)
        indexes = self._check_rows(side, self._sel)
        if self._is_bank(side):
            tablets = self._picked_tablets(indexes)
            names = what([t.name for t in tablets])
            where = f"bank folder {folder_label(self._folder)}"
            if not confirmed:
                text = f"Move {names} from {where} to the recycle bin?"
                again = partial(self.remove_selected, True)
                return Confirm("Remove from the bank?", text, "Remove", on_ok=again)
            try:
                self._bank.delete([t.path for t in tablets])
            except SaveIOError as exc:
                log.warning("could not delete from the bank: %s", exc)
                text = f"Could not move {names} to the recycle bin. {BANK_WRITE}"
                return [Notice(NoticeKind.ERROR, text)]
            self._clear_selection()
            return [_info(f"Moved {names} to the recycle bin.")]
        target = self._target(side)
        reasons = self._reasons({target: self._would_remove(target, indexes)})
        ask = self._gate(reasons, "Remove", confirmed, partial(self.remove_selected, True))
        if ask is not None:
            return ask
        remove = partial(self._session.remove_many, target, indexes)
        return self._edited(remove, [target], reasons)

    def _reset(self, confirmed: bool) -> Outcome:
        side = self._sel_side
        if side is None:
            raise SessionError(NOTHING_SELECTED)
        if self._is_bank(side):
            raise SessionError("Clear counts can only be reset in a save.")
        indexes = self._check_rows(side, self._sel)
        target = self._target(side)
        live = self._save_of(target).received.live
        cleared = [
            i for i in indexes if live[i].clear_count != NO_CLEARS or not live[i].clear_counts_agree
        ]
        reasons = self._reasons({target: self._would_reset(target, indexes)})
        ask = self._gate(reasons, "Reset", confirmed, partial(self.reset_selected, True))
        if ask is not None:
            return ask
        reset = partial(self._session.reset_clears_many, target, indexes)
        warnings = self._edited(reset, [target], reasons)
        done = "Clear count reset." if len(cleared) == SINGLE else "Clear counts reset."
        return [_info(f"{done} {RESET_NOTE}"), *warnings]

    def _reorder(self, side: PaneSide, old: int, new: int, confirmed: bool) -> Outcome:
        if self._is_bank(side):
            return []
        (old,) = self._check_rows(side, [old])
        target = self._target(side)
        new = min(max(new, 0), self._row_count(side) - LAST_OFFSET)
        reasons = self._reasons({target: self._would_reorder(target, old, new)})
        again = partial(self.reorder, side, old, new, True)
        ask = self._gate(reasons, "Move", confirmed, again)
        if ask is not None:
            return ask
        return self._edited(partial(self._session.move, target, old, new), [target], reasons)
