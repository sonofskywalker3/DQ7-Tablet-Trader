"""A Checkpoint save folder: reading its saves and writing an edited copy, never in place."""

import logging
import os
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dq7tt.errors import OutputExistsError, TabletTraderError, UnsupportedLayoutError
from dq7tt.savefile import ROLE_FILENAMES, SaveFile, SlotRole

log = logging.getLogger(__name__)

OUTPUT_NAME_FORMAT = "{name} edited {now:%Y%m%d-%H%M%S}"
TEMP_SUFFIX = ".tmp"
TEMP_DIR_PREFIX = ".dq7tt-"


@dataclass(frozen=True)
class SaveFolder:
    path: Path
    files: dict[SlotRole, SaveFile]

    @classmethod
    def open(cls, path: Path) -> "SaveFolder":
        """Load every save00N.bin that is a supported save; raise if there is none."""
        files: dict[SlotRole, SaveFile] = {}
        first_error: TabletTraderError | None = None
        for role, filename in ROLE_FILENAMES.items():
            candidate = path / filename
            if not candidate.is_file():
                continue
            try:
                files[role] = SaveFile.load(candidate)
            except TabletTraderError as exc:
                log.warning("skipping %s: %s", candidate, exc)
                first_error = first_error or exc
        if not files:
            if first_error is not None:
                raise first_error
            raise UnsupportedLayoutError(
                f"No Dragon Quest VII save files (save000.bin to save003.bin) in {path}."
            )
        return cls(path=path, files=files)


def default_output_path(src: Path, now: datetime) -> Path:
    """A sibling folder named after `src` and the local time, so it never collides by accident."""
    return src.parent / OUTPUT_NAME_FORMAT.format(name=src.name, now=now)


def _check_destination(inputs: Sequence[Path], dst: Path) -> None:
    dst_abs = dst.resolve()
    for folder in inputs:
        folder_abs = folder.resolve()
        if dst_abs == folder_abs or folder_abs in dst_abs.parents:
            raise OutputExistsError(f"The output folder must be outside {folder}.")
    if dst.exists():
        raise OutputExistsError(f"{dst} already exists. Nothing was written.")


def write_edited(
    src: Path, dst: Path, edited: dict[SlotRole, SaveFile], protect: Sequence[Path] = ()
) -> None:
    """Copy `src` to a new folder `dst` byte for byte, with `edited` saves swapped in.

    The copy is built in a hidden temporary folder next to `dst` and renamed into place
    last, so `dst` only ever appears complete. `protect` lists further input folders that
    `dst` must not be, or be inside (nothing is created there, not even the staging folder).
    """
    _check_destination([src, *protect], dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX, dir=dst.parent))
    try:
        work = staging / dst.name
        shutil.copytree(src, work)
        for role, save in edited.items():
            target = work / ROLE_FILENAMES[role]
            temp = target.with_name(target.name + TEMP_SUFFIX)
            temp.write_bytes(save.to_bytes())
            os.replace(temp, target)
        os.replace(work, dst)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
