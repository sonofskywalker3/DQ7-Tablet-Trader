"""Work out what a dropped path is: a backup folder, emulator save, plain folder, file or zip."""

import logging
import re
import shutil
import stat
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath

from dq7tt.chunks import check_layout
from dq7tt.constants import SAVE_FILENAMES
from dq7tt.errors import (
    JapaneseSaveError,
    SaveIOError,
    TabletTraderError,
    UnsupportedSourceError,
)

log = logging.getLogger(__name__)


class SourceKind(StrEnum):
    CHECKPOINT = "checkpoint"
    JKSM = "jksm"
    AZAHAR = "azahar"
    FOLDER = "folder"
    FILE = "file"
    ZIP = "zip"


class Region(StrEnum):
    US = "US"
    EU = "EU"
    JP = "JP"
    UNKNOWN = "unknown"


# Low title ids from 3dsdb. UNVERIFIED for JP and EU: only the US id has been seen on a real
# folder. Checkpoint names title folders with the id shifted right by CHECKPOINT_SHIFT bits
# (0x18EF00 -> "0x18EF0"); that shift is also unverified for JP and EU.
TITLE_LOWIDS = {Region.JP: 0x00065E00, Region.US: 0x0018EF00, Region.EU: 0x0018F000}
CHECKPOINT_SHIFT = 4
_CHECKPOINT_TOKEN = re.compile(r"0x([0-9A-Fa-f]{4,6})\b")

CHECKPOINT_MARKER = ("3ds", "checkpoint", "saves")
JKSM_MARKER = ("jksm", "user saves")
AZAHAR_ROOT = "sdmc"
AZAHAR_TAIL_PREFIX = ("title", "00040000")
AZAHAR_TAIL_SUFFIX = ("data", "00000001")
AZAHAR_TAIL_LENGTH = len(AZAHAR_TAIL_PREFIX) + 1 + len(AZAHAR_TAIL_SUFFIX)
ZIP_SUFFIX = ".zip"
MAX_ZIP_ENTRIES = 2000
MAX_ZIP_BYTES = 64 * 1024 * 1024
COPY_CHUNK = 1024 * 1024
TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
# Zip entries made by some tools carry no file-type bits at all; treat those as regular files.
REGULAR_FILE_TYPES = (0, stat.S_IFREG)
UNSAFE_MESSAGE = "This zip contains unsafe file paths and was not opened."
CLASH_MESSAGE = "This zip has conflicting file names and was not opened."
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"COM{n}" for n in range(1, 10)}
    | {f"LPT{n}" for n in range(1, 10)}
)
ZIP_TOO_LARGE = "This zip is too large to be a save backup."


@dataclass(frozen=True)
class SaveSource:
    """Where saves came from: `save_dir` holds the saveNNN.bin files to read."""

    kind: SourceKind
    path: Path
    save_dir: Path
    region: Region
    label: str


def _not_saves(path: Path) -> UnsupportedSourceError:
    return UnsupportedSourceError(f"No Dragon Quest VII saves were found in {path.name}.")


def _probe_file(path: Path) -> bool:
    """True if the file is a supported save; raises JapaneseSaveError for a Japanese one."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise SaveIOError(f"Could not read {path.name}: {exc.strerror or exc}") from exc
    try:
        check_layout(data)
    except JapaneseSaveError:
        raise
    except TabletTraderError as exc:
        log.debug("%s is not a DQ7 save: %s", path, exc)
        return False
    return True


def _folder_check(folder: Path) -> bool | JapaneseSaveError:
    """True if some save passes; the error if every present save is Japanese; else False."""
    japanese: JapaneseSaveError | None = None
    other = False
    try:
        entries = sorted(folder.iterdir(), key=lambda p: p.name.lower())
    except OSError as exc:
        raise SaveIOError(f"Could not read {folder.name}: {exc.strerror or exc}") from exc
    for candidate in entries:
        if candidate.name.lower() not in SAVE_FILENAMES or not candidate.is_file():
            continue
        try:
            if _probe_file(candidate):
                return True
            other = True
        except JapaneseSaveError as exc:
            japanese = exc
    if japanese is not None and not other:
        return japanese
    return False


def _lower_parts(path: Path) -> tuple[str, ...]:
    return tuple(part.lower() for part in path.parts)


def _has_run(parts: tuple[str, ...], marker: tuple[str, ...]) -> bool:
    size = len(marker)
    return any(parts[i : i + size] == marker for i in range(len(parts) - size + 1))


def _region_from_lowid(lowid: int) -> Region:
    for region, known in TITLE_LOWIDS.items():
        if known == lowid:
            return region
    return Region.UNKNOWN


def _azahar_region(save_dir: Path) -> Region | None:
    """The region if save_dir sits at an Azahar title data path, else None."""
    parts = _lower_parts(save_dir)
    if AZAHAR_ROOT not in parts or len(parts) < AZAHAR_TAIL_LENGTH:
        return None
    tail = parts[-AZAHAR_TAIL_LENGTH:]
    if tail[: len(AZAHAR_TAIL_PREFIX)] != AZAHAR_TAIL_PREFIX:
        return None
    if tail[-len(AZAHAR_TAIL_SUFFIX) :] != AZAHAR_TAIL_SUFFIX:
        return None
    try:
        return _region_from_lowid(int(tail[len(AZAHAR_TAIL_PREFIX)], 16))
    except ValueError:
        return Region.UNKNOWN


def _checkpoint_region(save_dir: Path) -> Region:
    by_token = {lowid >> CHECKPOINT_SHIFT: region for region, lowid in TITLE_LOWIDS.items()}
    for part in reversed(save_dir.parts):
        match = _CHECKPOINT_TOKEN.search(part)
        if match:
            return by_token.get(int(match.group(1), 16), Region.UNKNOWN)
    return Region.UNKNOWN


def _with_region(text: str, region: Region) -> str:
    return text if region is Region.UNKNOWN else f"{text} ({region.value})"


def _classify_folder(path: Path, save_dir: Path) -> SaveSource:
    parts = _lower_parts(save_dir)
    azahar = _azahar_region(save_dir)
    if azahar is not None:
        label = _with_region("Azahar save", azahar)
        return SaveSource(SourceKind.AZAHAR, path, save_dir, azahar, label)
    if _has_run(parts, CHECKPOINT_MARKER):
        region = _checkpoint_region(save_dir)
        label = _with_region(f"Checkpoint backup {save_dir.name}", region)
        return SaveSource(SourceKind.CHECKPOINT, path, save_dir, region, label)
    if _has_run(parts, JKSM_MARKER):
        region = _checkpoint_region(save_dir)
        label = _with_region(f"JKSM backup {save_dir.name}", region)
        return SaveSource(SourceKind.JKSM, path, save_dir, region, label)
    return SaveSource(SourceKind.FOLDER, path, save_dir, Region.UNKNOWN, f"Folder: {path.name}")


def _unsafe_member(name: str) -> bool:
    normal = name.replace("\\", "/")
    if normal.startswith("/"):
        return True
    for part in PurePosixPath(normal).parts:
        stem = part.split(".", 1)[0].upper()
        if (
            part == ".."
            or ":" in part
            or part != part.rstrip(". ")
            or stem in WINDOWS_RESERVED_NAMES
        ):
            return True
    return False


def _entry_parts(info: zipfile.ZipInfo) -> tuple[str, ...]:
    return PurePosixPath(info.filename.replace("\\", "/")).parts


def _is_extracted(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return not info.is_dir() and stat.S_IFMT(mode) in REGULAR_FILE_TYPES


def _check_clashes(members: list[zipfile.ZipInfo]) -> None:
    """Refuse duplicate names and names used as both a file and a folder."""
    files: set[tuple[str, ...]] = set()
    folders: set[tuple[str, ...]] = set()
    for info in members:
        parts = tuple(part.lower() for part in _entry_parts(info))
        if info.is_dir():
            folders.update(parts[:i] for i in range(1, len(parts) + 1))
            continue
        if not _is_extracted(info):
            continue
        if not parts or parts in files:
            raise UnsupportedSourceError(CLASH_MESSAGE)
        files.add(parts)
        folders.update(parts[:i] for i in range(1, len(parts)))
    if files & folders:
        raise UnsupportedSourceError(CLASH_MESSAGE)


def _check_zip(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """Validate every entry before anything is written."""
    members = archive.infolist()
    if len(members) > MAX_ZIP_ENTRIES:
        raise UnsupportedSourceError("This zip has too many files to be a save backup.")
    for info in members:
        if _unsafe_member(info.filename):
            raise UnsupportedSourceError(UNSAFE_MESSAGE)
    if sum(info.file_size for info in members) > MAX_ZIP_BYTES:
        raise UnsupportedSourceError(ZIP_TOO_LARGE)
    _check_clashes(members)
    return members


def _fresh_dir(work_dir: Path, stem: str) -> Path:
    base = f"{stem}-{datetime.now().strftime(TIMESTAMP_FORMAT)}"
    candidate = work_dir / base
    counter = 1
    while candidate.exists():
        counter += 1
        candidate = work_dir / f"{base}-{counter}"
    candidate.mkdir(parents=True)
    return candidate


def _extract_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with archive.open(info) as src, target.open("xb") as dst:
        while chunk := src.read(COPY_CHUNK):
            written += len(chunk)
            if written > MAX_ZIP_BYTES:
                raise UnsupportedSourceError(ZIP_TOO_LARGE)
            dst.write(chunk)
    return written


def _extract_zip(path: Path, work_dir: Path) -> Path:
    out: Path | None = None
    try:
        with zipfile.ZipFile(path) as archive:
            members = _check_zip(archive)
            out = _fresh_dir(work_dir, path.stem)
            root = out.resolve()
            total = 0
            for info in members:
                if not _is_extracted(info):
                    continue
                target = out.joinpath(*_entry_parts(info))
                if not target.resolve().is_relative_to(root):
                    raise UnsupportedSourceError(UNSAFE_MESSAGE)
                total += _extract_member(archive, info, target)
                if total > MAX_ZIP_BYTES:
                    raise UnsupportedSourceError(ZIP_TOO_LARGE)
    except (zipfile.BadZipFile, UnsupportedSourceError, OSError) as exc:
        if out is not None:
            shutil.rmtree(out, ignore_errors=True)
        if isinstance(exc, UnsupportedSourceError):
            raise
        if isinstance(exc, zipfile.BadZipFile):
            raise UnsupportedSourceError(f"{path.name} is not a readable zip file.") from exc
        if isinstance(exc, (FileExistsError, NotADirectoryError, IsADirectoryError)):
            raise UnsupportedSourceError(CLASH_MESSAGE) from exc
        raise SaveIOError(f"Could not unpack {path.name}: {exc.strerror or exc}") from exc
    return out


def _depth_key(root: Path) -> Callable[[Path], tuple[int, str]]:
    def key(folder: Path) -> tuple[int, str]:
        return (len(folder.relative_to(root).parts), str(folder))

    return key


def _find_save_dir(root: Path) -> Path | None:
    """Shallowest folder at or under root that holds saves; raises if only Japanese ones."""
    japanese: JapaneseSaveError | None = None
    folders = sorted((p for p in [root, *root.rglob("*")] if p.is_dir()), key=_depth_key(root))
    for folder in folders:
        result = _folder_check(folder)
        if result is True:
            return folder
        if isinstance(result, JapaneseSaveError) and japanese is None:
            japanese = result
    if japanese is not None:
        raise japanese
    return None


def open_source(path: Path, work_dir: Path) -> SaveSource:
    """Identify `path` by its content and return a SaveSource; zips unpack into `work_dir`."""
    path = Path(path)
    if path.is_dir():
        result = _folder_check(path)
        if isinstance(result, JapaneseSaveError):
            raise result
        if not result:
            raise _not_saves(path)
        return _classify_folder(path, path)
    if not path.is_file():
        raise UnsupportedSourceError(f"{path.name or path} does not exist.")
    if path.suffix.lower() == ZIP_SUFFIX:
        root = _extract_zip(path, work_dir)
        try:
            save_dir = _find_save_dir(root)
            if save_dir is None:
                raise _not_saves(path)
        except TabletTraderError:
            shutil.rmtree(root, ignore_errors=True)
            raise
        return SaveSource(SourceKind.ZIP, path, save_dir, Region.UNKNOWN, f"Zip: {path.stem}")
    if path.name.lower() not in SAVE_FILENAMES or not _probe_file(path):
        raise _not_saves(path)
    return SaveSource(SourceKind.FILE, path, path.parent, Region.UNKNOWN, f"File: {path.name}")
