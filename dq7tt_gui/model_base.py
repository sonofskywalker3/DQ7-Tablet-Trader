"""The window model's state and the helpers its commands share; no window code here."""

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path

from dq7tt.apppaths import AppPaths, effective_bank_dir, load_settings
from dq7tt.bank import ROOT_FOLDER, Bank, BankTablet
from dq7tt.errors import (
    BankFileError,
    InvalidSlotError,
    SaveIOError,
    SessionError,
    TabletTraderError,
    ValidationError,
)
from dq7tt.savefile import SaveFile, SlotRole
from dq7tt.session import Session, Target
from dq7tt.tablet_list import ReceivedList
from dq7tt.tablets import TabletRecord
from dq7tt.validate import Severity, validate
from dq7tt_gui.device_profile import DESKTOP_PROFILE, Profile
from dq7tt_gui.model_text import (
    BANK_READ,
    FILE_TROUBLE,
    NO_LOG,
    NOT_IN_LIST,
    REMOVED_CODE,
    bank_problem,
    confirm_text,
)
from dq7tt_gui.model_views import destination_detail, folder_label, is_full, short_label
from dq7tt_gui.viewmodels import Confirm, Destination, Notice, NoticeKind, Outcome, PaneSide

log = logging.getLogger(__name__)

NO_SAVE = "Open a save first."
NOTHING_SELECTED = "Select at least one tablet first."
QUICK_TEXT = (
    "This is the quick save (a suspended game). Resuming it may overwrite or ignore changes "
    "made here. Edit it anyway?"
)
QUICK_TITLE = "Edit the quick save?"
QUICK_OK = "Edit anyway"
QUICK_CODE = "QUICK_SAVE"
STORY_CODE = "STORY_ADDED"
SPECIAL_TITLES = {REMOVED_CODE: "Remove a special tablet?", STORY_CODE: "Add a story tablet?"}
REASON_SEPARATOR = "\n\n"
OTHER_SAVE = " in the other save"
BANK_KIND = "bank"
LOG_KIND = "log"
# Would-be saves per target; None when the change cannot happen (the core then says why).
Changes = Mapping[Target, SaveFile | None]


class ModelBase:
    """State of the two panes plus the helpers every command uses.

    Commands change this state only after the core has accepted the change, so a refused
    command leaves the window exactly as it was.
    """

    def __init__(
        self,
        paths: AppPaths,
        profile: Profile = DESKTOP_PROFILE,
        bank_root: Path | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._paths = paths
        self._profile = profile
        self._session = Session(paths, clock=clock)
        root = (
            bank_root if bank_root is not None else effective_bank_dir(paths, load_settings(paths))
        )
        self._bank = Bank(root)
        self._ids: dict[PaneSide, int | None] = {PaneSide.LEFT: None, PaneSide.RIGHT: None}
        self._roles: dict[PaneSide, SlotRole] = {
            PaneSide.LEFT: SlotRole.LOG_1,
            PaneSide.RIGHT: SlotRole.LOG_1,
        }
        self._bank_shown = True
        self._folder = ROOT_FOLDER
        self._sel_side: PaneSide | None = None
        self._sel: tuple[int, ...] = ()
        self._quick_ok = False
        # The written output each save last put into Azahar; it is not offered twice.
        self._put_outputs: dict[int, Path] = {}
        # The work folder each save was last written to on its way into Azahar (one step).
        self._staging: dict[int, Path] = {}

    @property
    def profile(self) -> Profile:
        return self._profile

    # Where things are

    def _is_bank(self, side: PaneSide) -> bool:
        return side is PaneSide.RIGHT and self._bank_shown

    def _sid(self, side: PaneSide) -> int:
        sid = self._ids[side]
        if sid is None:
            raise SessionError(NO_SAVE)
        return sid

    def _target(self, side: PaneSide) -> Target:
        return Target(self._sid(side), self._roles[side])

    def _saves(self, sid: int) -> dict[SlotRole, SaveFile]:
        return self._session.sources()[sid].edited

    def _save_of(self, target: Target) -> SaveFile:
        try:
            return self._saves(target.source_id)[target.role]
        except KeyError:
            raise SessionError(NO_LOG) from None

    def _bank_tablets(self) -> list[BankTablet]:
        return self._read_bank(lambda: self._bank.list(self._folder))

    def _read_bank[T](self, read: Callable[[], T]) -> T:
        """Read from the bank; file-system trouble becomes a plain sentence (detail logged)."""
        try:
            return read()
        except SaveIOError as exc:
            log.warning("could not read the bank: %s", exc)
            raise SessionError(BANK_READ) from exc
        except BankFileError as exc:
            log.warning("unusable bank file: %s", exc)
            raise SessionError(bank_problem(exc)) from exc

    def _row_count(self, side: PaneSide) -> int:
        if self._is_bank(side):
            return len(self._bank_tablets())
        return self._save_of(self._target(side)).received.count

    def _check_rows(self, side: PaneSide, indexes: Sequence[int]) -> tuple[int, ...]:
        if not indexes:
            raise SessionError(NOTHING_SELECTED)
        count = self._row_count(side)
        if any(not 0 <= i < count for i in indexes):
            raise SessionError(NOT_IN_LIST)
        if len(set(indexes)) != len(indexes):
            raise SessionError("The same tablet was picked twice.")
        return tuple(indexes)

    def _picked_tablets(self, indexes: Sequence[int]) -> list[BankTablet]:
        tablets = self._bank_tablets()
        return [tablets[i] for i in indexes]

    def _home_id(self) -> int | None:
        """The save that log labels are relative to: the selection's, else the left one."""
        if self._sel_side is not None and not self._is_bank(self._sel_side):
            return self._ids[self._sel_side]
        return self._ids[PaneSide.LEFT]

    def _log_dest(self, target: Target, qualify: bool = True) -> Destination:
        label = short_label(target.role)
        if qualify and target.source_id != self._home_id():
            label += OTHER_SAVE
        save = self._saves(target.source_id).get(target.role)
        if save is None:
            return Destination(label, LOG_KIND, target)
        return Destination(
            label, LOG_KIND, target, detail=destination_detail(save), full=is_full(save)
        )

    def _bank_dest(self, folder: str) -> Destination:
        return Destination(f"bank folder {folder_label(folder)}", BANK_KIND, folder)

    # Selection

    def _clear_selection(self, side: PaneSide | None = None) -> None:
        if side is None or side is self._sel_side:
            self._sel_side = None
            self._sel = ()

    # Running commands

    def _run(self, action: Callable[[], Outcome]) -> Outcome:
        """Run a command; any refusal from the core becomes one error notice."""
        try:
            return action()
        except ValidationError as exc:
            errors = [p for p in exc.problems if getattr(p, "severity", None) is Severity.ERROR]
            text = " ".join(str(p) for p in errors) or str(exc)
        except InvalidSlotError as exc:
            log.info("bad position: %s", exc)
            text = NOT_IN_LIST
        except SaveIOError as exc:
            log.warning("file error in a window command: %s", exc)
            text = FILE_TROUBLE
        except BankFileError as exc:
            log.warning("unusable bank file: %s", exc)
            text = bank_problem(exc)
        except TabletTraderError as exc:
            text = str(exc)
        except OSError as exc:
            log.exception("file error in a window command: %s", exc)
            text = FILE_TROUBLE
        log.info("refused: %s", text)
        return [Notice(NoticeKind.ERROR, text)]

    # Confirms

    def _would_insert(
        self, target: Target, records: Sequence[TabletRecord], index: int
    ) -> SaveFile | None:
        try:
            save = self._save_of(target)
            return save.with_received(save.received.insert_many(records, index))
        except TabletTraderError:
            return None

    def _would_remove(self, target: Target, indexes: Sequence[int]) -> SaveFile | None:
        try:
            save = self._save_of(target)
            lst = save.received
            for i in sorted(indexes, reverse=True):
                lst = lst.remove(i)
            return save.with_received(lst)
        except TabletTraderError:
            return None

    def _would_reorder(self, target: Target, old: int, new: int) -> SaveFile | None:
        try:
            save = self._save_of(target)
            return save.with_received(save.received.move(old, new))
        except TabletTraderError:
            return None

    def _would_reset(self, target: Target, indexes: Sequence[int]) -> SaveFile | None:
        """The save with the picked clear counts at 0; None when none of them was cleared."""
        try:
            save = self._save_of(target)
            lst = save.received
            raw = list(lst.slots)
            for i in indexes:
                record = lst.live[i]
                if record.clear_count or not record.clear_counts_agree:
                    raw[i] = record.with_clear_count(0).raw
            if tuple(raw) == lst.slots:
                return None
            return save.with_received(ReceivedList(slots=tuple(raw), count=lst.count))
        except (TabletTraderError, IndexError):
            return None

    def _reasons(self, changes: Changes) -> list[tuple[str, str]]:
        """Why this change needs a yes first, as (code, text), using the core's wording.

        A change the core will refuse (a would-be save of None) asks nothing, so the refusal
        shows straight away.
        """
        if any(new is None for new in changes.values()):
            return []
        reasons: list[tuple[str, str]] = []
        if not self._quick_ok and any(t.role is SlotRole.QUICK_SAVE for t in changes):
            reasons.append((QUICK_CODE, QUICK_TEXT))
        for code in (REMOVED_CODE, STORY_CODE):
            for target, new in changes.items():
                current = self._save_of(target)
                for problem in validate(new, current, self._session.db):
                    if problem.code == code and (code, problem.message) not in reasons:
                        reasons.append((code, problem.message))
        return reasons

    def _gate(
        self,
        reasons: list[tuple[str, str]],
        ok_label: str,
        confirmed: bool,
        again: Callable[[], Outcome],
    ) -> Confirm | None:
        if confirmed or not reasons:
            return None
        codes = [code for code, _ in reasons]
        if QUICK_CODE in codes:
            title, ok_label = QUICK_TITLE, QUICK_OK
        else:
            title = SPECIAL_TITLES[codes[0]]
        text = REASON_SEPARATOR.join(confirm_text(code, text) for code, text in reasons)
        return Confirm(title, text, ok_label, on_ok=again)

    # After an edit

    def _warnings(self) -> list[tuple[str, str]]:
        """Every warning the core has for the open saves, as (code, text)."""
        return [
            (problem.code, problem.message)
            for sid in self._session.sources()
            for problems in self._session.problems(sid).values()
            for problem in problems
            if problem.severity is Severity.WARNING
        ]

    def _edited(
        self,
        edit: Callable[[], object],
        touched: Sequence[Target],
        reasons: list[tuple[str, str]],
    ) -> list[Notice]:
        """Make one edit through the core; new warnings the user did not just accept follow."""
        before = {text for _, text in self._warnings()}
        edit()
        if any(t.role is SlotRole.QUICK_SAVE for t in touched):
            self._quick_ok = True
        self._clear_selection()
        accepted = {text for _, text in reasons}
        # A yes to editing the quick save covers the core's quick save warning too.
        quick_accepted = any(code == QUICK_CODE for code, _ in reasons)
        found: list[Notice] = []
        for code, text in self._warnings():
            notice = Notice(NoticeKind.WARNING, text)
            if code == QUICK_CODE and quick_accepted:
                continue
            if text not in before and text not in accepted and notice not in found:
                found.append(notice)
        return found
