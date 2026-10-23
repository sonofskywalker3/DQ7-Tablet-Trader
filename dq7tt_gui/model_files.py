"""The window's save-file commands: open, close, write and put into Azahar."""

import logging
import shutil
import tempfile
from collections.abc import Callable
from datetime import datetime
from functools import partial
from pathlib import Path

from dq7tt.apppaths import AppPaths
from dq7tt.errors import AzaharReplaceError, AzaharRereadError, SessionError, TabletTraderError
from dq7tt.session_core import MAX_OPEN_SOURCES
from dq7tt.session_ops import load_saves, remove_extraction, same_place
from dq7tt.sources import SourceKind, open_source
from dq7tt_gui import model_views as views
from dq7tt_gui.device_profile import DESKTOP_PROFILE, Profile
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
PUT_FAILED = (
    "Could not put the edited save into Azahar, so its save was left as it was. The save "
    "from before is backed up in {backup} in the backups folder. Try Put into Azahar again."
)
PUT_BROKEN = (
    "Could not put the edited save into Azahar, and its save could not be put back as it "
    "was. Restore it from the backup {backup} in the backups folder."
)
PUT_UNREAD = (
    "The edited save is now in Azahar, but it could not be read back to show it here. Open "
    "it again to see it. The save it replaced is backed up in {backup} in the backups folder."
)
SIDES = (PaneSide.LEFT, PaneSide.RIGHT)
# One-step Save into Azahar (the Android profile).
SAVE_INTO_TITLE = "Save into Azahar?"
SAVE_INTO_TEXT = (
    "Close the game in Azahar first. Azahar's current save is backed up before it is replaced."
)
SAVE_INTO_OK = "Save"
NOT_NOW = "Not now"
SAVED_INTO = "Saved into Azahar. The save it replaced is backed up in {backup}."
SAVE_INTO_FAILED = (
    "Could not save into Azahar, so its save was left as it was. The save from before is "
    "backed up in {backup}. Try Save into Azahar again."
)
SAVED_UNREAD = (
    "Saved into Azahar, but it could not be read back to show it here. Open it again to "
    "see it. The save it replaced is backed up in {backup} in the backups folder."
)
SAVE_INTO_BROKEN = (
    "Could not save into Azahar, and its save could not be put back as it was. "
    "Restore it from the backup {backup} in the backups folder."
)
NOTHING_TO_SAVE = "There are no changes to write."
STAGING_PREFIX = "into-azahar-"
STAGED_NAME = "save"


class SaveOps(EditOps):
    """Commands on whole saves. Each returns notices, or a Confirm to accept first."""

    def __init__(
        self,
        paths: AppPaths,
        profile: Profile = DESKTOP_PROFILE,
        bank_root: Path | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        super().__init__(paths, profile, bank_root, clock)
        self._clean_leftover_staging()

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
            if self._one_step(sid) and (
                self._session.is_dirty(sid) or self._can_put_into_azahar(sid)
            ):
                again = partial(self._save_into_azahar, side)
                return Confirm(SAVE_INTO_TITLE, SAVE_INTO_TEXT, SAVE_INTO_OK, NOT_NOW, on_ok=again)
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
            if self._one_step(sid):
                return self._save_into_azahar(side) if confirmed else self.write(side)
            azahar = self._azahar_id(sid)
            if not confirmed:
                return self._azahar_offer(side)
            try:
                backup = self._session.put_into_azahar(sid, azahar)
            except AzaharReplaceError as exc:
                log.warning("could not put into Azahar: %s", exc)
                text = PUT_FAILED if exc.restored else PUT_BROKEN
                return [Notice(NoticeKind.ERROR, text.format(backup=exc.backup.name))]
            except AzaharRereadError as exc:
                self._put_done(sid)
                return [Notice(NoticeKind.INFO, PUT_UNREAD.format(backup=exc.backup.name))]
            self._put_done(sid)
            return [Notice(NoticeKind.INFO, PUT_DONE.format(backup=backup))]

        return self._run(act)

    # Internals

    def _one_step(self, sid: int) -> bool:
        """Writing this save puts it straight into Azahar (an Azahar save on Android)."""
        source = self._session.sources()[sid].source
        return self._profile.one_step_azahar and source.kind is SourceKind.AZAHAR

    def _save_into_azahar(self, side: PaneSide) -> Outcome:
        """Write the edited copy to a work folder, then put it into Azahar (backed up first).

        If putting it in fails, Azahar keeps its own save whole and the written copy stays in
        its work folder, so the save is offered for saving into Azahar again.
        """

        def act() -> Outcome:
            sid = self._sid(side)
            if self._session.is_dirty(sid):
                self._stage(sid)
            elif not self._can_put_into_azahar(sid):
                raise SessionError(NOTHING_TO_SAVE)
            try:
                backup = self._session.put_into_azahar(sid, sid)
            except AzaharReplaceError as exc:
                log.warning("could not save into Azahar: %s", exc)
                text = SAVE_INTO_FAILED if exc.restored else SAVE_INTO_BROKEN
                return [Notice(NoticeKind.ERROR, text.format(backup=exc.backup.name))]
            except AzaharRereadError as exc:
                # The edit is in Azahar: nothing is left to save again.
                self._put_done(sid)
                self._drop_staging(sid)
                return [Notice(NoticeKind.INFO, SAVED_UNREAD.format(backup=exc.backup.name))]
            self._put_done(sid)
            self._drop_staging(sid)
            return [Notice(NoticeKind.INFO, SAVED_INTO.format(backup=backup.name))]

        return self._run(act)

    def _put_done(self, sid: int) -> None:
        """The last written copy is in Azahar: it is not offered for putting in again."""
        written = self._session.last_output(sid)
        if written is not None:
            self._put_outputs[sid] = written
        self._clear_selection()

    def _stage(self, sid: int) -> None:
        """Write the save into a fresh work folder; Azahar is backed up when it is put in."""
        self._paths.work_dir.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix=STAGING_PREFIX, dir=self._paths.work_dir))
        try:
            self._session.write(sid, out_dir=folder / STAGED_NAME, backup=False)
        except (TabletTraderError, OSError):
            _remove_folder(folder)
            raise
        self._drop_staging(sid)
        self._staging[sid] = folder

    def _unsaved(self, sid: int) -> bool:
        """Changes not written, or (one step) written but not yet in Azahar."""
        if self._session.is_dirty(sid):
            return True
        return self._one_step(sid) and self._can_put_into_azahar(sid)

    def _clean_leftover_staging(self) -> None:
        """Remove work folders a previous run left on their way into Azahar."""
        try:
            leftovers = [
                p
                for p in self._paths.work_dir.glob(f"{STAGING_PREFIX}*")
                if p.is_dir() and not p.is_symlink()
            ]
        except OSError as exc:
            log.warning("could not look for leftover work folders: %s", exc)
            return
        for folder in leftovers:
            _remove_folder(folder)

    def _drop_staging(self, sid: int) -> None:
        folder = self._staging.pop(sid, None)
        if folder is not None:
            _remove_folder(folder)

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
        if old is not None and self._unsaved(old) and not confirmed:
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
            self._drop_staging(old)
            return new
        # No room to open it first: make sure it opens and reads before closing the old one.
        probe = open_source(path, self._paths.work_dir)
        try:
            load_saves(probe)
        finally:
            remove_extraction(probe, self._paths.work_dir)
        self._session.close(old, force=True)
        self._drop_staging(old)
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
        if self._unsaved(sid) and not confirmed:
            close = self.close_right if side is PaneSide.RIGHT else self.close_left
            return self._discard_confirm(partial(close, True))
        self._session.close(sid, force=True)
        self._drop_staging(sid)
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


def _remove_folder(folder: Path) -> None:
    try:
        shutil.rmtree(folder)
    except OSError as exc:
        log.warning("could not remove the work folder %s: %s", folder, exc)
