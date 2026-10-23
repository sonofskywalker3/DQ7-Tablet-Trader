"""The window model: everything the desktop window shows and does, without any window code."""

import logging
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path

from dq7tt.apppaths import android_storage, load_settings
from dq7tt.bank import ROOT_FOLDER
from dq7tt.errors import BankFileError, SaveIOError, SessionError, TabletTraderError
from dq7tt.savefile import SlotRole
from dq7tt.scan import android_roots, android_volumes, default_roots, scan
from dq7tt.session import Target
from dq7tt.sources import SaveSource, SourceKind
from dq7tt_gui import model_views as views
from dq7tt_gui.device_profile import Platform
from dq7tt_gui.model_base import BANK_KIND
from dq7tt_gui.model_files import SIDES, SaveOps
from dq7tt_gui.model_text import (
    BANK_WRITE,
    EMPTY_FORMAT,
    FILE_TROUBLE,
    NO_LOG,
    NOT_IN_LIST,
    bank_problem,
)
from dq7tt_gui.viewmodels import (
    PUT_INTO_AZAHAR,
    ActionBar,
    Destination,
    FoundSave,
    Notice,
    NoticeKind,
    Outcome,
    PaneSide,
    PaneView,
    RightMode,
    ToolbarView,
)

log = logging.getLogger(__name__)

WRITE_ONE = "Write changes"
WRITE_BOTH = "Write changes to both saves"
WRITE_BOTH_SHORT = "Write both"
SAVE_INTO = "Save into Azahar"


class AppModel(SaveOps):
    """The open save on the left; the bank or a second save on the right."""

    # Queries

    def left(self) -> PaneView:
        return self._save_view(PaneSide.LEFT)

    def right(self) -> PaneView:
        if not self._bank_shown:
            return self._save_view(PaneSide.RIGHT)
        side = PaneSide.RIGHT
        right = self._ids[side]
        chips = () if right is None else views.log_chips(self._saves(right), None)
        selected = self._sel if self._sel_side is side else ()
        try:
            counts = {
                name: len(self._read_bank(partial(self._bank.list, name)))
                for name in self._folder_names()
            }
            rows = views.bank_rows(side, self._bank_tablets(), selected)
        except TabletTraderError as exc:
            log.warning("could not read the bank: %s", exc)
            return views.bank_pane(side, str(self._bank.root), chips, (), (), str(exc))
        folders = views.folder_chips(counts, self._folder)
        return views.bank_pane(side, str(self._bank.root), chips, folders, rows)

    def has_save(self, side: PaneSide) -> bool:
        """A save is open on this side (on the right, possibly behind the bank)."""
        return self._ids[side] is not None

    def right_mode(self) -> RightMode:
        return RightMode.BANK if self._bank_shown else RightMode.SAVE

    def right_tab_label(self) -> str:
        """The narrow layout's second tab: "Bank", or a short name for the second save."""
        sid = self._ids[PaneSide.RIGHT]
        if self._bank_shown or sid is None:
            return views.BANK_TITLE
        return views.tab_label(self._session.sources()[sid].source.kind)

    def toolbar(self) -> ToolbarView:
        sides = self.write_sides()
        label = WRITE_BOTH if len(sides) == len(SIDES) else WRITE_ONE
        # Save into Azahar when every save Write acts on is an Azahar save; with nothing to
        # write, when an open save is one.
        if self._profile.one_step_azahar:
            open_sides = [s for s in SIDES if self._ids[s] is not None]
            azahar = [s for s in (sides or open_sides) if self._is_azahar(s)]
            if azahar and (not sides or len(azahar) == len(sides)):
                label = SAVE_INTO
        return ToolbarView(
            undo_label=self._session.undo_label,
            redo_label=self._session.redo_label,
            can_write=bool(sides),
            write_label=label,
            short_label=WRITE_BOTH_SHORT if label == WRITE_BOTH else None,
        )

    def empty_text(self) -> str:
        return EMPTY_FORMAT.format(device=self._profile.device_word)

    def action_bar(self) -> ActionBar:
        count = len(self._sel)
        if not count:
            return ActionBar(0, "", None, False, False, False)
        quick = self._quick_dest()
        return ActionBar(
            selected_count=count,
            summary=f"{views.tablets_text(count)} selected",
            quick_copy_label=None if quick is None else f"Copy to {quick.label}",
            # From the bank, Move only goes to another bank folder; into a log is a copy.
            can_move=bool(self.destinations(move=True)),
            can_reset=self._can_reset(),
            can_remove=True,
        )

    def destinations(self, move: bool = False) -> list[Destination]:
        """Every log of every open save except the selection's own, then every bank folder.

        A move out of the bank lists bank folders only: a tablet never leaves the bank.
        """
        own = None
        from_bank = self._sel_side is not None and self._is_bank(self._sel_side)
        if self._sel_side is not None and not from_bank:
            own = self._target(self._sel_side)
        home = self._home_id()
        sids = sorted(self._session.sources(), key=lambda sid: sid != home)
        found = [
            self._log_dest(target)
            for sid in sids
            for role in views.ordered_roles(self._saves(sid))
            if (target := Target(sid, role)) != own
        ]
        own_folder = self._folder if from_bank else None
        try:
            folders = self._folder_names()
        except TabletTraderError as exc:
            log.warning("could not list bank folders: %s", exc)
            folders = []
        found += [self._bank_dest(name) for name in folders if name != own_folder]
        if move and from_bank:
            return [d for d in found if d.kind == BANK_KIND]
        return found

    def has_unwritten(self) -> bool:
        return any(self._unsaved(sid) for sid in self._session.sources())

    def dirty_sides(self) -> list[PaneSide]:
        return [
            s for s in SIDES if (sid := self._ids[s]) is not None and self._session.is_dirty(sid)
        ]

    def write_sides(self) -> list[PaneSide]:
        """The sides Write acts on: unwritten changes, and with one-step saving also an Azahar
        save whose last Save into Azahar did not finish."""
        dirty = self.dirty_sides()
        if not self._profile.one_step_azahar:
            return dirty
        return [
            s
            for s in SIDES
            if s in dirty or ((sid := self._ids[s]) is not None and self._unsaved(sid))
        ]

    def scan_results(self, roots: Sequence[Path] | None = None) -> list[SaveSource]:
        found = self._search_roots() if roots is None else list(roots)
        return scan(found, self._paths.work_dir)

    def _search_roots(self) -> list[Path]:
        """Where Find saves looks: emulator folders and removable drives for this device."""
        if self._profile.platform is not Platform.ANDROID:
            return default_roots()
        remembered = load_settings(self._paths).azahar_dir
        return android_roots(android_storage(), remembered, android_volumes())

    def find_saves(
        self, roots: Sequence[Path] | None = None
    ) -> tuple[list[FoundSave], list[Notice]]:
        """Scan for saves; a file-system failure becomes an error notice, never an exception."""
        try:
            return [views.found_save(src) for src in self.scan_results(roots)], []
        except OSError as exc:
            log.exception("scan for saves failed: %s", exc)
            return [], [Notice(NoticeKind.ERROR, FILE_TROUBLE)]
        except TabletTraderError as exc:
            log.warning("scan for saves refused: %s", exc)
            return [], [Notice(NoticeKind.ERROR, str(exc))]

    # Panes and selection

    def show_bank(self) -> Outcome:
        self._bank_shown = True
        self._clear_selection(PaneSide.RIGHT)
        return []

    def pick_log(self, side: PaneSide, role: SlotRole) -> Outcome:
        def act() -> Outcome:
            sid = self._sid(side)
            if role not in self._saves(sid):
                raise SessionError(NO_LOG)
            self._roles[side] = role
            if side is PaneSide.RIGHT:
                self._bank_shown = False
            self._clear_selection(side)
            return []

        return self._run(act)

    def pick_folder(self, name: str) -> Outcome:
        def act() -> Outcome:
            if name != ROOT_FOLDER and name not in self._read_bank(self._bank.folders):
                raise SessionError(f"There is no bank folder named {name}.")
            self._folder = name
            self._bank_shown = True
            self._clear_selection(PaneSide.RIGHT)
            return []

        return self._run(act)

    def new_folder(self, name: str) -> Outcome:
        def act() -> Outcome:
            try:
                self._bank.create_folder(name)
            except BankFileError as exc:
                raise SessionError(bank_problem(exc, name)) from exc
            except SaveIOError as exc:
                log.warning("could not create bank folder: %s", exc)
                raise SessionError(BANK_WRITE) from exc
            return self.pick_folder(name)

        return self._run(act)

    def toggle_row(self, side: PaneSide, index: int) -> Outcome:
        def act() -> Outcome:
            if not 0 <= index < self._row_count(side):
                raise SessionError(NOT_IN_LIST)
            current = set(self._sel) if self._sel_side is side else set()
            current ^= {index}
            self._sel_side = side if current else None
            self._sel = tuple(sorted(current))
            return []

        return self._run(act)

    def select_all(self, side: PaneSide) -> Outcome:
        def act() -> Outcome:
            count = self._row_count(side)
            self._sel_side = side if count else None
            self._sel = tuple(range(count))
            return []

        return self._run(act)

    def clear_selection(self) -> Outcome:
        self._clear_selection()
        return []

    # History

    def undo(self) -> Outcome:
        return self._run(partial(self._step, self._session.undo, "Undone"))

    def redo(self) -> Outcome:
        return self._run(partial(self._step, self._session.redo, "Redone"))

    # Internals

    def _folder_names(self) -> list[str]:
        found = self._read_bank(self._bank.folders)
        names = [ROOT_FOLDER, *(n for n in found if n != ROOT_FOLDER)]
        if self._folder not in names:
            names.append(self._folder)
        return names

    def _save_view(self, side: PaneSide) -> PaneView:
        sid = self._ids[side]
        if sid is None:
            return views.empty_pane(side)
        opened = self._session.sources()[sid]
        role = self._roles[side]
        selected = self._sel if self._sel_side is side else ()
        rows = views.save_rows(side, self._session.tablets(self._target(side)), selected)
        dirty = role in self._session.dirty_roles(sid)
        put = self._can_put_into_azahar(sid)
        put_label = SAVE_INTO if self._profile.one_step_azahar else PUT_INTO_AZAHAR
        return views.save_pane(
            side, opened.source.label, opened.edited, role, rows, dirty, put, put_label
        )

    def _is_azahar(self, side: PaneSide) -> bool:
        sid = self._ids[side]
        return sid is not None and self._session.sources()[sid].source.kind is SourceKind.AZAHAR

    def _can_reset(self) -> bool:
        side = self._sel_side
        if side is None or self._is_bank(side):
            return False
        live = self._save_of(self._target(side)).received.live
        return any(
            live[i].clear_count or not live[i].clear_counts_agree
            for i in self._sel
            if i < len(live)
        )

    def _step(self, step: Callable[[], str], word: str) -> Outcome:
        label = step()
        self._clear_selection()
        return [Notice(NoticeKind.INFO, f"{word}: {label}")]
