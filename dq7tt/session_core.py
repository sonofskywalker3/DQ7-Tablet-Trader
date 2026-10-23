"""The session's state: up to two open saves, all-or-nothing steps, undo, and safe writes."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dq7tt import output
from dq7tt.apppaths import AppPaths
from dq7tt.database import TabletDatabase
from dq7tt.errors import AzaharRereadError, SessionError, TabletTraderError, ValidationError
from dq7tt.history import History
from dq7tt.savefile import SaveFile, SlotRole
from dq7tt.session_ops import (
    State,
    load_saves,
    real_identities,
    remove_extraction,
    role_name,
    role_problems,
    same_place,
    tablet_rows,
    with_saves,
    with_source,
    without_source,
)
from dq7tt.sources import SaveSource, SourceKind, open_source
from dq7tt.tablets import TabletKind, TabletRecord
from dq7tt.validate import Problem, Severity, require_valid, validate

log = logging.getLogger(__name__)

MAX_OPEN_SOURCES = 2
FIRST_SOURCE_ID = 1


@dataclass(frozen=True)
class Target:
    source_id: int
    role: SlotRole


@dataclass(frozen=True)
class OpenSource:
    """One open save: `original` is the state as last written (or as opened), not the disk."""

    source: SaveSource
    original: dict[SlotRole, SaveFile]
    edited: dict[SlotRole, SaveFile]


class SessionCore:
    """Open saves, history and writing; `Session` adds the edits on top.

    One History covers all open saves together, so undo walks back edits in the order they
    were made, whichever save they touched.
    """

    def __init__(
        self,
        paths: AppPaths,
        db: TabletDatabase | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._paths = paths
        self._db = db if db is not None else TabletDatabase.load()
        self._clock = clock
        self._sources: dict[int, SaveSource] = {}
        # The saves as they are on disk: every write compares with and validates against this.
        self._disk: State = {}
        # The saves as last written (or as opened): "dirty" means changed since this.
        self._clean: State = {}
        self._outputs: dict[int, Path] = {}
        # Identities of live records as first read from disk, before any edit or write.
        self._read_identities: dict[int, frozenset[bytes]] = {}
        self._allowed: frozenset[bytes] = frozenset()
        self._history: History[State] = History({})
        self._next_id = FIRST_SOURCE_ID

    # Opening and closing

    def open(self, path: Path) -> int:
        """Open a save source and return its id."""
        if len(self._sources) >= MAX_OPEN_SOURCES:
            raise SessionError("Close a save before opening a third.")
        path = Path(path)
        for src in self._sources.values():
            if same_place(path, src.path) or same_place(path, src.save_dir):
                raise SessionError(f"{src.label} is already open.")
        source = open_source(path, self._paths.work_dir)
        try:
            for src in self._sources.values():
                if same_place(source.save_dir, src.save_dir):
                    raise SessionError(f"{src.label} is already open.")
            saves = load_saves(source)
        except TabletTraderError:
            remove_extraction(source, self._paths.work_dir)
            raise
        source_id = self._next_id
        self._next_id += 1
        self._sources[source_id] = source
        self._disk[source_id] = saves
        self._clean[source_id] = saves
        self._read_identities[source_id] = real_identities({source_id: saves})
        self._history.rewrite(lambda s: with_source(s, source_id, saves))
        log.info("opened %s as save %d", source.label, source_id)
        return source_id

    def close(self, source_id: int, force: bool = False) -> None:
        self._source(source_id)
        if self.is_dirty(source_id) and not force:
            raise SessionError("This save has changes that were not written. Write it first.")
        source = self._sources.pop(source_id)
        del self._disk[source_id]
        del self._clean[source_id]
        del self._read_identities[source_id]
        self._outputs.pop(source_id, None)
        self._history.rewrite(lambda s: without_source(s, source_id))
        remove_extraction(source, self._paths.work_dir)

    def sources(self) -> dict[int, OpenSource]:
        current = self._history.current
        return {
            sid: OpenSource(src, dict(self._clean[sid]), dict(current[sid]))
            for sid, src in self._sources.items()
        }

    def is_dirty(self, source_id: int) -> bool:
        return bool(self.dirty_roles(source_id))

    def dirty_roles(self, source_id: int) -> set[SlotRole]:
        self._source(source_id)
        clean = self._clean[source_id]
        return {r for r, save in self._history.current[source_id].items() if save != clean[r]}

    def last_output(self, source_id: int) -> Path | None:
        self._source(source_id)
        return self._outputs.get(source_id)

    @property
    def db(self) -> TabletDatabase:
        return self._db

    def tablets(self, target: Target) -> list[tuple[str, TabletKind, TabletRecord]]:
        """The live tablets of one save, newest first: name, kind and record."""
        return tablet_rows(self._save(target), self._db)

    # Undo and redo

    @property
    def can_undo(self) -> bool:
        return self._history.can_undo

    @property
    def can_redo(self) -> bool:
        return self._history.can_redo

    @property
    def undo_label(self) -> str | None:
        return self._history.undo_label

    @property
    def redo_label(self) -> str | None:
        return self._history.redo_label

    def undo(self) -> str:
        label = self._history.undo_label or ""
        self._history.undo()
        return label

    def redo(self) -> str:
        label = self._history.redo_label or ""
        self._history.redo()
        return label

    # Checking and writing

    def problems(self, source_id: int) -> dict[SlotRole, list[Problem]]:
        """Problems per opened save; errors in saves left unchanged are reported as warnings."""
        self._source(source_id)
        disk = self._disk[source_id]
        return {
            role: role_problems(save, disk[role], self._db, self._allowed)
            for role, save in self._history.current[source_id].items()
        }

    def write(self, source_id: int, out_dir: Path | None = None, backup: bool = True) -> Path:
        """Write the edited copy beside or away from the input, never over it; returns it.

        `out_dir` names a new folder to write instead of the default location. `backup=False`
        skips backing the input up, for a copy put into Azahar next (that backs Azahar up).
        """
        source = self._source(source_id)
        if not self.is_dirty(source_id):
            raise SessionError("There are no changes to write.")
        current = self._history.current[source_id]
        disk = self._disk[source_id]
        # Every output is a complete edited copy of the input, so it carries every save that
        # differs from the disk, including ones already written in an earlier output.
        changed = {role: save for role, save in current.items() if save != disk[role]}
        if source.kind is SourceKind.FILE:
            changed = dict(current)
        for role, save in changed.items():
            require_valid(save, disk[role], self._db, allowed=self._allowed)
        protect = [
            folder
            for sid, src in self._sources.items()
            if sid != source_id
            for folder in output.protected_dirs(src)
        ]
        # Saves equal to the disk are copied byte for byte by write_source.
        out = output.write_source(
            source, changed, self._paths, self._clock(), protect, out_dir, backup
        )
        self._clean[source_id] = dict(current)
        self._outputs[source_id] = out
        if not any(self.is_dirty(sid) for sid in self._sources if sid != source_id):
            self._history = History(self._history.current)
        log.info("wrote %s to %s", source.label, out)
        return out

    def put_into_azahar(self, source_id: int, azahar_source_id: int) -> Path:
        """Copy the last written output of `source_id` into an open Azahar save; returns backup."""
        self._source(source_id)
        azahar = self._source(azahar_source_id)
        written = self._outputs.get(source_id)
        if written is None:
            raise SessionError("Write this save first. There is nothing to put into Azahar yet.")
        if self.is_dirty(source_id):
            raise SessionError("Write your latest changes first.")
        if azahar.kind is not SourceKind.AZAHAR:
            raise SessionError(f"{azahar.label} is not an Azahar save.")
        if not written.is_dir():
            raise SessionError("Only a whole save folder can be put into Azahar.")
        if azahar_source_id != source_id and self.is_dirty(azahar_source_id):
            raise SessionError(
                f"{azahar.label} has changes that were not written. Undo them first."
            )
        backup = output.put_into_azahar(written, azahar.save_dir, self._paths, self._clock())
        try:
            saves = load_saves(azahar)
        except TabletTraderError as exc:
            log.warning("put into %s, but could not read it back: %s", azahar.label, exc)
            if azahar_source_id == source_id:
                # What Azahar holds now is what was written: the current state.
                self._disk[source_id] = dict(self._history.current[source_id])
            raise AzaharRereadError(str(exc), backup) from exc
        self._disk[azahar_source_id] = saves
        if azahar_source_id != source_id:
            self._clean[azahar_source_id] = saves
            self._history.rewrite(lambda s: with_source(s, azahar_source_id, saves))
        return backup

    # Internals

    def _source(self, source_id: int) -> SaveSource:
        try:
            return self._sources[source_id]
        except KeyError:
            raise SessionError(f"Save {source_id} is not open.") from None

    def _save(self, target: Target) -> SaveFile:
        source = self._source(target.source_id)
        try:
            return self._history.current[target.source_id][target.role]
        except KeyError:
            raise SessionError(f"{source.label} has no {role_name(target.role)}.") from None

    @staticmethod
    def _key(target: Target) -> tuple[int, SlotRole]:
        return (target.source_id, target.role)

    def _read_from_disk(self) -> frozenset[bytes]:
        """Identities of every live record the open saves held when they were opened."""
        return frozenset().union(*self._read_identities.values())

    def _is_real(self, record: TabletRecord) -> bool:
        """True if the record came from a real save, not only from the tablet database."""
        return record.identity in (self._read_from_disk() | self._allowed)

    def _apply(
        self,
        changes: dict[tuple[int, SlotRole], SaveFile],
        label: str,
        extra: frozenset[bytes] = frozenset(),
    ) -> None:
        """Validate the would-be state of every touched save, then commit it as one step."""
        allowed = self._allowed | extra
        errors = [
            problem
            for (sid, role), save in changes.items()
            for problem in validate(save, self._disk[sid][role], self._db, allowed=allowed)
            if problem.severity is Severity.ERROR
        ]
        if errors:
            raise ValidationError(errors)
        self._history.push(with_saves(self._history.current, changes), label)
        self._allowed = allowed
