"""Where edited saves are written, the backup taken first, and the explicit step into Azahar."""

import logging
import os
import re
import shutil
import zipfile
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

from dq7tt.apppaths import AppPaths
from dq7tt.errors import (
    OutputExistsError,
    SaveIOError,
    SessionError,
    TabletTraderError,
)
from dq7tt.folder import (
    OUTPUT_NAME_FORMAT,
    TEMP_DIR_PREFIX,
    TEMP_SUFFIX,
    check_destination,
    default_output_path,
    write_edited,
)
from dq7tt.savefile import ROLE_FILENAMES, SaveFile, SlotRole, role_from_filename
from dq7tt.sources import AZAHAR_ROOT, SaveSource, SourceKind, open_source

log = logging.getLogger(__name__)

STAMP_FORMAT = "{now:%Y-%m-%d %H%M%S}"
FILE_OUTPUT_SUFFIX = ".bin"
BACKUP_SUFFIX = ".zip"
SYSTEM_FILENAME = "system.bin"
AZAHAR_COPY_NAMES = (*ROLE_FILENAMES.values(), SYSTEM_FILENAME)
INVALID_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
REPLACEMENT_CHAR = "_"
STALE_STAGING_AGE = timedelta(hours=1)
SIBLING_KINDS = frozenset({SourceKind.CHECKPOINT, SourceKind.JKSM, SourceKind.FOLDER})


def _safe_label(label: str) -> str:
    return INVALID_NAME_CHARS.sub(REPLACEMENT_CHAR, label).strip()


def output_path(source: SaveSource, paths: AppPaths, now: datetime) -> Path:
    """Where the edited copy of `source` goes; never inside an emulator or input folder."""
    if source.kind in SIBLING_KINDS:
        return default_output_path(source.save_dir, now)
    if source.kind is SourceKind.FILE:
        name = OUTPUT_NAME_FORMAT.format(name=source.path.stem, now=now) + FILE_OUTPUT_SUFFIX
        return source.save_dir / name
    return paths.edited_dir / f"{STAMP_FORMAT.format(now=now)} {_safe_label(source.label)}"


def emulator_root(save_dir: Path) -> Path | None:
    """The emulator folder above the `sdmc` folder holding `save_dir`, or `sdmc` itself if
    that sits at a drive root; None when `save_dir` is not inside an `sdmc` folder."""
    parts = save_dir.resolve().parts
    found = [i for i, part in enumerate(parts) if part.lower() == AZAHAR_ROOT]
    if not found:
        return None
    sdmc = Path(*parts[: found[-1] + 1])
    return sdmc if sdmc.parent == Path(sdmc.anchor) else sdmc.parent


def protected_dirs(source: SaveSource) -> list[Path]:
    """Folders no output may land in: the save folder, and for Azahar the emulator's tree."""
    root = emulator_root(source.save_dir) if source.kind is SourceKind.AZAHAR else None
    return [source.save_dir] if root is None else [source.save_dir, root]


def _backup_members(source: SaveSource) -> list[Path]:
    if source.kind is SourceKind.FILE:
        return [source.path]
    return sorted(p for p in source.save_dir.rglob("*") if p.is_file())


def _free_zip_path(backups_dir: Path, stem: str) -> Path:
    candidate = backups_dir / f"{stem}{BACKUP_SUFFIX}"
    counter = 1
    while candidate.exists():
        counter += 1
        candidate = backups_dir / f"{stem} ({counter}){BACKUP_SUFFIX}"
    return candidate


def backup_source(source: SaveSource, paths: AppPaths, now: datetime) -> Path:
    """Zip every file of the source's saves into the backups folder and return the zip."""
    stem = f"{STAMP_FORMAT.format(now=now)} {_safe_label(source.label)}"
    temp: Path | None = None
    try:
        paths.backups_dir.mkdir(parents=True, exist_ok=True)
        target = _free_zip_path(paths.backups_dir, stem)
        temp = target.with_name(target.name + TEMP_SUFFIX)
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
            for member in _backup_members(source):
                archive.write(member, member.relative_to(source.save_dir).as_posix())
        os.replace(temp, target)
    except OSError as exc:
        if temp is not None:
            temp.unlink(missing_ok=True)
        raise SaveIOError(f"Could not back up {source.label}: {exc.strerror or exc}") from exc
    return target


def _write_file_source(source: SaveSource, edited: dict[SlotRole, SaveFile], out: Path) -> None:
    role = role_from_filename(source.path.name)
    save = edited.get(role)
    if save is None:
        raise SessionError(f"There is no edited copy of {source.path.name} to write.")
    if out.exists():
        raise OutputExistsError(f"{out} already exists. Nothing was written.")
    temp = out.with_name(out.name + TEMP_SUFFIX)
    try:
        temp.write_bytes(save.to_bytes())
        os.replace(temp, out)
    except OSError as exc:
        temp.unlink(missing_ok=True)
        raise SaveIOError(f"Could not write {out.name}: {exc.strerror or exc}") from exc


def write_source(
    source: SaveSource,
    edited: dict[SlotRole, SaveFile],
    paths: AppPaths,
    now: datetime,
    protect: Sequence[Path] = (),
    out_dir: Path | None = None,
) -> Path:
    """Back the source up, then write the edited copy to `out_dir` or `output_path`.

    The destination is checked before the backup, so a refused destination leaves nothing behind.
    The input is never touched.
    """
    if out_dir is not None and source.kind is SourceKind.FILE:
        raise SessionError("A single save file is written next to itself, not to a chosen folder.")
    out = out_dir if out_dir is not None else output_path(source, paths, now)
    if source.kind is SourceKind.FILE:
        if out.exists():
            raise OutputExistsError(f"{out} already exists. Nothing was written.")
    else:
        protect = [*protected_dirs(source)[1:], *protect]
        check_destination([source.save_dir, *protect], out)
    backup_source(source, paths, now)
    if source.kind is SourceKind.FILE:
        _write_file_source(source, edited, out)
    else:
        try:
            write_edited(source.save_dir, out, edited, protect=protect)
        except OSError as exc:
            raise SaveIOError(f"Could not write {out.name}: {exc.strerror or exc}") from exc
    return out


def _azahar_source(azahar_save_dir: Path, paths: AppPaths) -> SaveSource:
    try:
        source = open_source(azahar_save_dir, paths.work_dir)
    except TabletTraderError as exc:
        raise SessionError(f"{azahar_save_dir} is not an Azahar save folder.") from exc
    if source.kind is not SourceKind.AZAHAR:
        raise SessionError(f"{azahar_save_dir} is not an Azahar save folder.")
    return source


def _check_edited_saves(edited_dir: Path, names: Sequence[str], paths: AppPaths) -> None:
    """Refuse a folder that is not a readable DQ7 save, or any save in it that the game would
    reject, before anything in Azahar is backed up or replaced."""
    try:
        open_source(edited_dir, paths.work_dir)
    except TabletTraderError as exc:
        raise SessionError(f"{edited_dir} is not a Dragon Quest VII save folder. {exc}") from exc
    for name in names:
        if role_from_filename(name) is SlotRole.UNKNOWN:
            continue
        try:
            save = SaveFile.load(edited_dir / name)
        except TabletTraderError as exc:
            raise SessionError(f"{name} is not a Dragon Quest VII save. {exc}") from exc
        except OSError as exc:
            raise SessionError(f"{name} is not readable: {exc.strerror or exc}") from exc
        if not save.checksum_ok:
            raise SessionError(
                f"{name} has a wrong checksum, so it is not a Dragon Quest VII save "
                "the game would accept."
            )


def put_into_azahar(
    edited_dir: Path, azahar_save_dir: Path, paths: AppPaths, now: datetime
) -> Path:
    """Back up the Azahar save folder, then copy the edited saves over it; returns the backup."""
    source = _azahar_source(azahar_save_dir, paths)
    target_dir = source.save_dir
    edited_abs = edited_dir.resolve()
    target_abs = target_dir.resolve()
    if edited_abs == target_abs or target_abs in edited_abs.parents:
        raise SessionError("The edited saves must come from outside the Azahar folder.")
    names = [n for n in AZAHAR_COPY_NAMES if (edited_dir / n).is_file()]
    if not names:
        raise SessionError(f"No edited saves were found in {edited_dir}.")
    _check_edited_saves(edited_dir, names, paths)
    missing = [n for n in names if not (target_dir / n).is_file()]
    if missing:
        raise SessionError(f"The Azahar folder has no {', '.join(missing)} to replace.")
    zip_path = backup_source(source, paths, now)
    for name in names:
        target = target_dir / name
        temp = target.with_name(target.name + TEMP_SUFFIX)
        try:
            shutil.copyfile(edited_dir / name, temp)
            os.replace(temp, target)
        except OSError as exc:
            temp.unlink(missing_ok=True)
            raise SaveIOError(
                f"Could not replace {name} in Azahar: {exc.strerror or exc}. "
                f"Your original saves are in the backup {zip_path}."
            ) from exc
    return zip_path


def clean_stale_staging(
    parent: Path, older_than: timedelta = STALE_STAGING_AGE, now: datetime | None = None
) -> int:
    """Remove this tool's own leftover staging folders in `parent` older than the limit."""
    cutoff = (now or datetime.now()) - older_than
    removed = 0
    try:
        entries = list(parent.iterdir())
    except OSError as exc:
        log.debug("not cleaning %s: %s", parent, exc)
        return 0
    for entry in entries:
        if not entry.name.startswith(TEMP_DIR_PREFIX) or entry.is_symlink() or not entry.is_dir():
            continue
        try:
            if datetime.fromtimestamp(entry.stat().st_mtime) >= cutoff:
                continue
            shutil.rmtree(entry)
            removed += 1
        except OSError as exc:
            log.warning("could not remove stale staging folder %s: %s", entry, exc)
    return removed
