"""The window's save-file commands: open, close, write and put into Azahar."""

import logging
from collections.abc import Callable
from functools import partial
from pathlib import Path

from dq7tt.errors import SessionError, TabletTraderError
from dq7tt.session_core import MAX_OPEN_SOURCES
from dq7tt.session_ops import load_saves, remove_extraction, same_place
from dq7tt.sources import SourceKind, open_source
from dq7tt_gui import model_views as views
from dq7tt_gui.model_ops import EditOps
from dq7tt_gui.model_text import DISCARD_TITLE
from dq7tt_gui.viewmodels import Confirm, Notice, NoticeKind, Outcome, PaneSide

log = logging.getLogger(__name__)

DISCARD_TEXT = "You have changes that are not written yet. Discard them?"
WRITTEN = "Wrote the edited save to {out}. Your original is untouched; a backup is in {backups}."
RESTORE_LIST = "It appears as a new backup in {app}'s restore list."
RESTORE_APPS = {SourceKind.CHECKPOINT: "Checkpoint", SourceKind.JKSM: "JKSM"}
AZAHAR_TITLE = "Put into Azahar?"
AZAHAR_TEXT = (
    "Put this into Azahar now? Close Azahar first. The current Azahar save is backed up "
    "before it is replaced."
)
PUT_DONE = "The edited save is now in Azahar. The save it replaced is backed up in {backup}."
SIDES = (PaneSide.LEFT, PaneSide.RIGHT)


class SaveOps(EditOps):
    """Commands on whole saves. Each returns notices, or a Confirm to accept first."""

    def open_left(self, path: Path, confirmed: bool = False) -> Outcome:
        return self._run(partial(self._open, PaneSide.LEFT, Path(path), confirmed))

    def open_right(self, path: Path, confirmed: bool = False) -> Outcome:
        return self._run(partial(self._open, PaneSide.RIGHT, Path(path), confirmed))

    def close_left(self, confirmed: bool = False) -> Outcome:
        return self._run(partial(self._close, PaneSide.LEFT, confirmed))

    def close_right(self, confirmed: bool = False) -> Outcome:
        return self._run(partial(self._close, PaneSide.RIGHT, confirmed))

    def write(self, side: PaneSide) -> Outcome:
        def act() -> Outcome:
            sid = self._sid(side)
            source = self._session.sources()[sid].source
            out = self._session.write(sid)
            backups = self._paths.backups_dir
            notes = [Notice(NoticeKind.INFO, WRITTEN.format(out=out, backups=backups))]
            app = RESTORE_APPS.get(source.kind)
            if app is not None:
                notes.append(Notice(NoticeKind.INFO, RESTORE_LIST.format(app=app)))
            if source.kind is SourceKind.AZAHAR:
                return self._azahar_offer(side, tuple(notes))
            return notes

        return self._run(act)

    def put_into_azahar(self, side: PaneSide, confirmed: bool = False) -> Outcome:
        def act() -> Outcome:
            sid = self._sid(side)
            azahar = self._azahar_id(sid)
            if not confirmed:
                return self._azahar_offer(side)
            backup = self._session.put_into_azahar(sid, azahar)
            written = self._session.last_output(sid)
            if written is not None:
                self._put_outputs[sid] = written
            self._clear_selection()
            return [Notice(NoticeKind.INFO, PUT_DONE.format(backup=backup))]

        return self._run(act)

    # Internals

    def _can_put_into_azahar(self, sid: int) -> bool:
        """An Azahar save written with no changes since, and not yet put in: it can go back in."""
        source = self._session.sources()[sid].source
        written = self._session.last_output(sid)
        return (
            source.kind is SourceKind.AZAHAR
            and written is not None
            and not self._session.is_dirty(sid)
            and self._put_outputs.get(sid) != written
        )

    def _discard_confirm(self, again: Callable[[], Outcome]) -> Confirm:
        return Confirm(DISCARD_TITLE, DISCARD_TEXT, "Discard", on_ok=again)

    def _open(self, side: PaneSide, path: Path, confirmed: bool) -> Outcome:
        old = self._ids[side]
        if old is not None and self._session.is_dirty(old) and not confirmed:
            reopen = self.open_right if side is PaneSide.RIGHT else self.open_left
            return self._discard_confirm(partial(reopen, path, True))
        other = self._ids[PaneSide.RIGHT if side is PaneSide.LEFT else PaneSide.LEFT]
        if other is not None:
            src = self._session.sources()[other].source
            if same_place(path, src.path) or same_place(path, src.save_dir):
                raise SessionError(f"{src.label} is already open.")
        if old is None:
            new = self._session.open(path)
        else:
            new = self._replace(old, path)
        self._ids[side] = new
        self._roles[side] = views.default_role(self._saves(new))
        if side is PaneSide.RIGHT:
            self._bank_shown = False
        self._clear_selection(side)
        return []

    def _replace(self, old: int, path: Path) -> int:
        """Open `path` in place of save `old`, which is closed; on failure `old` stays open."""
        source = self._session.sources()[old].source
        reopening = same_place(path, source.path) or same_place(path, source.save_dir)
        if len(self._session.sources()) < MAX_OPEN_SOURCES and not reopening:
            new = self._session.open(path)
            self._session.close(old, force=True)
            return new
        # No room to open it first: make sure it opens and reads before closing the old one.
        probe = open_source(path, self._paths.work_dir)
        try:
            load_saves(probe)
        finally:
            remove_extraction(probe, self._paths.work_dir)
        self._session.close(old, force=True)
        try:
            return self._session.open(path)
        except TabletTraderError:
            self._restore(source.path, old)
            raise

    def _restore(self, path: Path, old: int) -> None:
        side = next(s for s in SIDES if self._ids[s] == old)
        role = self._roles[side]
        try:
            self._ids[side] = self._session.open(path)
            self._roles[side] = role
        except TabletTraderError as exc:
            log.warning("could not reopen %s after a failed open: %s", path, exc)
            self._ids[side] = None
            self._clear_selection(side)

    def _close(self, side: PaneSide, confirmed: bool) -> Outcome:
        sid = self._sid(side)
        if self._session.is_dirty(sid) and not confirmed:
            close = self.close_right if side is PaneSide.RIGHT else self.close_left
            return self._discard_confirm(partial(close, True))
        self._session.close(sid, force=True)
        self._ids[side] = None
        if side is PaneSide.RIGHT:
            self._bank_shown = True
        self._clear_selection(side)
        return []

    def _azahar_id(self, sid: int) -> int:
        for candidate in (sid, *(s for s in self._ids.values() if s not in (None, sid))):
            if self._session.sources()[candidate].source.kind is SourceKind.AZAHAR:
                return candidate
        raise SessionError("No open save came from Azahar.")

    def _azahar_offer(self, side: PaneSide, notes: tuple[Notice, ...] = ()) -> Confirm:
        again = partial(self.put_into_azahar, side, True)
        return Confirm(AZAHAR_TITLE, AZAHAR_TEXT, "Put into Azahar", "Not now", notes, again)
