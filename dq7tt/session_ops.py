"""Small pure helpers for the editing session: names, loading, and state updates."""

import dataclasses
import logging
import shutil
from pathlib import Path

from dq7tt.database import TabletDatabase, describe
from dq7tt.errors import InvalidSlotError, SaveIOError
from dq7tt.folder import SaveFolder
from dq7tt.savefile import SaveFile, SlotRole
from dq7tt.sources import SaveSource, SourceKind
from dq7tt.tablets import TabletKind, TabletRecord
from dq7tt.validate import Problem, Severity, validate

log = logging.getLogger(__name__)

# Every open save's edited files, keyed by source id. Never mutated: edits build new dicts.
State = dict[int, dict[SlotRole, SaveFile]]

ROLE_NAMES: dict[SlotRole, str] = {
    SlotRole.QUICK_SAVE: "the quick save",
    SlotRole.LOG_1: "adventure log 1",
    SlotRole.LOG_2: "adventure log 2",
    SlotRole.LOG_3: "adventure log 3",
}


def role_name(role: SlotRole) -> str:
    return ROLE_NAMES.get(role, str(role))


def tablet_name(record: TabletRecord, db: TabletDatabase) -> str:
    return describe(record, db)[0]


def load_saves(source: SaveSource) -> dict[SlotRole, SaveFile]:
    """The saves a source offers: the one file for a single-file source, else its folder."""
    try:
        if source.kind is SourceKind.FILE:
            save = SaveFile.load(source.path)
            return {save.role: save}
        return dict(SaveFolder.open(source.save_dir).files)
    except OSError as exc:
        raise SaveIOError(f"Could not read {source.label}: {exc.strerror or exc}") from exc


def record_at(save: SaveFile, slot: int) -> TabletRecord:
    live = save.received.live
    if not 0 <= slot < len(live):
        raise InvalidSlotError(f"tablet position {slot} is outside 0..{len(live) - 1}")
    return live[slot]


def with_saves(state: State, changes: dict[tuple[int, SlotRole], SaveFile]) -> State:
    """A new state with the given saves replaced; `state` itself is left as it was."""
    result = {sid: dict(saves) for sid, saves in state.items()}
    for (sid, role), save in changes.items():
        result[sid][role] = save
    return result


def without_source(state: State, source_id: int) -> State:
    return {sid: saves for sid, saves in state.items() if sid != source_id}


def with_source(state: State, source_id: int, saves: dict[SlotRole, SaveFile]) -> State:
    return {**state, source_id: dict(saves)}


def real_identities(originals: dict[int, dict[SlotRole, SaveFile]]) -> frozenset[bytes]:
    """Identities of every live record in the saves as they were read from disk."""
    return frozenset(
        record.identity
        for saves in originals.values()
        for save in saves.values()
        for record in save.received.live
    )


def same_place(a: Path, b: Path) -> bool:
    return a.resolve() == b.resolve()


def tablet_rows(save: SaveFile, db: TabletDatabase) -> list[tuple[str, TabletKind, TabletRecord]]:
    return [(*describe(record, db), record) for record in save.received.live]


def role_problems(
    edited: SaveFile, original: SaveFile, db: TabletDatabase, allowed: frozenset[bytes]
) -> list[Problem]:
    """Problems of one save; an unchanged save is never written, so its errors only warn."""
    found = validate(edited, original, db, allowed=allowed)
    if edited != original:
        return found
    return [dataclasses.replace(p, severity=Severity.WARNING) for p in found]


def extraction_root(source: SaveSource, work_dir: Path) -> Path | None:
    """The folder a zip source was unpacked into, if it lies inside `work_dir`."""
    if source.kind is not SourceKind.ZIP:
        return None
    work = work_dir.resolve()
    save_dir = source.save_dir.resolve()
    if not save_dir.is_relative_to(work) or save_dir == work:
        return None
    return work / save_dir.relative_to(work).parts[0]


def remove_extraction(source: SaveSource, work_dir: Path) -> None:
    root = extraction_root(source, work_dir)
    if root is None:
        return
    try:
        shutil.rmtree(root)
    except OSError as exc:
        log.warning("could not remove unpacked zip folder %s: %s", root, exc)
