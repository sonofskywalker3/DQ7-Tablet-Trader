"""Find every Dragon Quest VII save in the known emulator and SD card layouts."""

import ctypes
import logging
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from dq7tt.constants import SAVE_FILENAMES
from dq7tt.errors import TabletTraderError
from dq7tt.sources import TITLE_LOWIDS, SaveSource, open_source

log = logging.getLogger(__name__)

APPDATA_VAR = "APPDATA"
EMULATOR_FOLDERS = ("Azahar", "Citra", "Lime3DS")
DRIVE_REMOVABLE = 2
HIDDEN_PREFIX = "."
ANY = "*"
LOWID_STEP = "<lowid>"
LOWID_NAMES = frozenset(f"{lowid:08x}" for lowid in TITLE_LOWIDS.values())
# Each layout is a list of steps below the root: a folder name (any case), ANY, or LOWID_STEP.
AZAHAR_LAYOUT = (
    "sdmc",
    "Nintendo 3DS",
    ANY,
    ANY,
    "title",
    "00040000",
    LOWID_STEP,
    "data",
    "00000001",
)
CHECKPOINT_LAYOUT = ("3ds", "Checkpoint", "saves", ANY, ANY)
JKSM_LAYOUT = ("JKSM", "User Saves", ANY, ANY)
LAYOUTS = (AZAHAR_LAYOUT, CHECKPOINT_LAYOUT, JKSM_LAYOUT)
# Depth counts folder levels below the layout's first step (so "sdmc" is level 0).
FIRST_STEP_DEPTH = 1


def _removable_drives() -> list[Path]:
    if sys.platform != "win32":
        return []
    drives: list[Path] = []
    get_type = ctypes.windll.kernel32.GetDriveTypeW  # type: ignore[attr-defined,unused-ignore]
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        root = f"{letter}:\\"
        if get_type(root) == DRIVE_REMOVABLE:
            drives.append(Path(root))
    return drives


def default_roots(
    env: Mapping[str, str] = os.environ, drives: Sequence[Path] | None = None
) -> list[Path]:
    """Emulator data folders and removable drives that exist right now."""
    roots: list[Path] = []
    appdata = env.get(APPDATA_VAR)
    if appdata:
        roots.extend(p for p in (Path(appdata) / name for name in EMULATOR_FOLDERS) if p.is_dir())
    found = _removable_drives() if drives is None else drives
    roots.extend(Path(d) for d in found if Path(d).is_dir())
    return roots


def _matches(step: str, name: str) -> bool:
    if step == ANY:
        return True
    if step == LOWID_STEP:
        return name in LOWID_NAMES
    return name.lower() == step.lower()


def _children(folder: Path) -> list[Path]:
    """Visible subfolders; an unreadable folder is logged and treated as empty."""
    try:
        with os.scandir(folder) as entries:
            return [
                Path(e.path) for e in entries if not e.name.startswith(HIDDEN_PREFIX) and e.is_dir()
            ]
    except OSError as exc:
        log.info("Skipping %s: %s", folder, exc.strerror or exc)
        return []


def _expand(root: Path, layout: Sequence[str], max_depth: int) -> list[Path]:
    if len(layout) - FIRST_STEP_DEPTH > max_depth:
        return []
    level = [root]
    for step in layout:
        level = [c for folder in level for c in _children(folder) if _matches(step, c.name)]
        if not level:
            break
    return level


def _freshness(save_dir: Path) -> float | None:
    """The newest change time of the folder and its saves; None if the folder is gone."""
    try:
        stamps = [save_dir.stat().st_mtime]
    except OSError as exc:
        log.info("Skipping %s: %s", save_dir, exc.strerror or exc)
        return None
    for name in SAVE_FILENAMES:
        try:
            stamps.append((save_dir / name).stat().st_mtime)
        except OSError:
            continue
    return max(stamps)


def _try_open(folder: Path, work_dir: Path) -> SaveSource | None:
    try:
        return open_source(folder, work_dir)
    except (TabletTraderError, OSError) as exc:
        log.info("Skipping %s: %s", folder, exc)
        return None


def scan(roots: Sequence[Path], work_dir: Path, max_depth: int = 8) -> list[SaveSource]:
    """Every DQ7 save under the roots' known layouts, newest first."""
    seen: set[Path] = set()
    found: list[tuple[float, SaveSource]] = []
    for root in roots:
        if not Path(root).is_dir():
            log.info("Skipping %s: not a folder", root)
            continue
        for layout in LAYOUTS:
            for folder in _expand(Path(root), layout, max_depth):
                key = folder.resolve()
                if key in seen:
                    continue
                seen.add(key)
                source = _try_open(folder, work_dir)
                if source is None:
                    continue
                fresh = _freshness(folder)
                if fresh is not None:
                    found.append((fresh, source))
    found.sort(key=lambda pair: pair[0], reverse=True)
    return [source for _, source in found]
