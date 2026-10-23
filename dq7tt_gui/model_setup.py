"""First run on Android: All files access, the Azahar folder, and the save to open at start.

No window code here; `android_setup` draws the screen and asks Android for access.
"""

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from dq7tt.apppaths import AppPaths, Settings, load_settings, save_settings
from dq7tt.errors import SaveIOError, TabletTraderError
from dq7tt.scan import find_azahar_save
from dq7tt.sources import SaveSource
from dq7tt_gui.viewmodels import Notice, NoticeKind

log = logging.getLogger(__name__)

NOT_AZAHAR = (
    "There is no Dragon Quest VII save in that folder. Choose the Azahar folder, usually "
    "called Azahar, in internal storage."
)


class SetupStep(StrEnum):
    NEED_ACCESS = "need_access"
    NEED_FOLDER = "need_folder"
    READY = "ready"


@dataclass(frozen=True)
class SetupCopy:
    """What the setup screen says for one step."""

    title: str
    body: str
    button: str


SCREEN_COPY = {
    SetupStep.NEED_ACCESS: SetupCopy(
        "Allow access to your saves",
        "To edit your Dragon Quest VII save where Azahar keeps it, this app needs All files "
        "access. Android opens a settings page: turn on DQ7 Tablet Trader there, then come back.",
        "Allow access",
    ),
    SetupStep.NEED_FOLDER: SetupCopy(
        "Choose your Azahar folder",
        "Pick the folder Azahar uses for its files. It is usually called Azahar, in internal "
        "storage.",
        "Choose folder",
    ),
}


def screen_copy(step: SetupStep) -> SetupCopy:
    """The setup screen's words for a step that needs one (not READY)."""
    return SCREEN_COPY[step]


def setup_step(has_access: bool, settings: Settings, found: SaveSource | None) -> SetupStep:
    """Access first, then a remembered Azahar folder that still holds a save."""
    if not has_access:
        return SetupStep.NEED_ACCESS
    if settings.azahar_dir is None or found is None:
        return SetupStep.NEED_FOLDER
    return SetupStep.READY


class SetupModel:
    """Where first run stands, and the save the window opens when it is done."""

    def __init__(self, paths: AppPaths) -> None:
        self._paths = paths
        self._found: SaveSource | None = None

    def step(self, has_access: bool) -> SetupStep:
        """Check again from scratch: settings from disk, the remembered folder on storage."""
        settings = load_settings(self._paths)
        self._found = self._remembered(settings) if has_access else None
        return setup_step(has_access, settings, self._found)

    def folder_picked(self, path: Path) -> Notice | None:
        """Remember `path` if it holds an Azahar DQ7 save; otherwise say so, remember nothing."""
        found = self._find(path)
        if found is None:
            return Notice(NoticeKind.ERROR, NOT_AZAHAR)
        settings = load_settings(self._paths)
        settings.azahar_dir = path
        try:
            save_settings(self._paths, settings)
        except SaveIOError as exc:
            # The save still opens now; the folder is asked for again next time.
            log.warning("could not remember the Azahar folder: %s", exc)
        self._found = found
        return None

    def start_source(self) -> Path | None:
        """The save folder to open on the left, once the last check found one."""
        return None if self._found is None else self._found.save_dir

    def _remembered(self, settings: Settings) -> SaveSource | None:
        folder = settings.azahar_dir
        if folder is None or not folder.is_dir():
            return None
        return self._find(folder)

    def _find(self, folder: Path) -> SaveSource | None:
        try:
            return find_azahar_save(folder, self._paths.work_dir)
        except (OSError, TabletTraderError) as exc:
            log.warning("could not look for an Azahar save in %s: %s", folder, exc)
            return None
