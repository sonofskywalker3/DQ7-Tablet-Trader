"""Opening saves: the folder and file pickers, and Find saves with its off-thread scan."""

import asyncio
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

import flet as ft

from dq7tt_gui.dialogs import find_saves_dialog, open_choice_dialog, searching_dialog
from dq7tt_gui.viewmodels import Notice, NoticeKind, PaneSide
from dq7tt_gui.window_dialogs import DialogFlows

log = logging.getLogger(__name__)

SAVE_EXTENSIONS = ["bin", "zip"]
FOLDER_PROMPT = "Open a save folder"
FILE_PROMPT = "Open a save file or zip"
SCAN_FAILED = "Something went wrong while looking for saves. Try opening the save folder yourself."


class OpenFlows(DialogFlows):
    picker: ft.FilePicker | None
    _scan_id: int
    _searching: ft.AlertDialog | None

    def open_dialog(self, side: PaneSide = PaneSide.LEFT) -> None:
        """Ask whether to open a folder or a file or zip, then run the matching picker.

        Where single files cannot be opened (Android), go straight to the folder picker.
        """
        if not self.model.profile.can_open_files:
            self.page.run_task(self.pick_and_open, side)
            return

        def build(close: Callable[[], bool]) -> ft.AlertDialog:
            def folder() -> None:
                if close():
                    self.page.run_task(self.pick_and_open, side)

            def file() -> None:
                if close():
                    self.page.run_task(self.pick_file_and_open, side)

            return open_choice_dialog(folder, file, close)

        self._present(build)

    def _picker(self) -> ft.FilePicker:
        if self.picker is None:
            self.picker = ft.FilePicker()
            self.page.services.append(self.picker)
        return self.picker

    async def pick_and_open(self, side: PaneSide = PaneSide.LEFT) -> None:
        path = await self._picker().get_directory_path(dialog_title=FOLDER_PROMPT)
        if path:
            self._open_path(Path(path), side)

    async def pick_file_and_open(self, side: PaneSide = PaneSide.LEFT) -> None:
        files = await self._picker().pick_files(
            dialog_title=FILE_PROMPT,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=SAVE_EXTENSIONS,
            allow_multiple=False,
        )
        if files and files[0].path:
            self._open_path(Path(files[0].path), side)

    def _open_path(self, path: Path, side: PaneSide = PaneSide.LEFT) -> None:
        opener = self.model.open_left if side is PaneSide.LEFT else self.model.open_right
        self.handle(opener(path))

    # Find saves

    def find_saves(self, roots: Sequence[Path] | None = None) -> None:
        if self._searching is not None and self._searching in self._dialogs:
            return
        self._scan_id += 1
        scan_id = self._scan_id

        def build(close: Callable[[], bool]) -> ft.AlertDialog:
            def cancel() -> None:
                if close():
                    self._scan_id += 1

            return searching_dialog(cancel)

        self._searching = self._present(build)
        self.page.run_task(self.scan_and_show, roots, scan_id)

    async def scan_and_show(self, roots: Sequence[Path] | None, scan_id: int) -> None:
        try:
            found, notices = await asyncio.to_thread(self.model.find_saves, roots)
        except Exception:  # noqa: BLE001 - nothing may leave the searching dialog up
            log.exception("scan for saves failed unexpectedly")
            found, notices = [], [Notice(NoticeKind.ERROR, SCAN_FAILED)]
        if scan_id != self._scan_id:
            return
        if self._searching is not None:
            self._close_dialog(self._searching)
        if notices:
            self.handle(notices)
            return

        def build(close: Callable[[], bool]) -> ft.AlertDialog:
            def open_it(path: Path) -> None:
                if close():
                    self._open_path(path)

            return find_saves_dialog(found, open_it, close, self.list_height())

        self._present(build)
