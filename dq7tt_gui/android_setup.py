"""First run on Android: ask for All files access, then for the Azahar folder, then open.

The check runs at start and every time the app comes back to the foreground, so turning
access on in Android's settings moves on without a restart, and turning it off later brings
this screen back.
"""

import asyncio
import logging
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

import flet as ft
import flet_permission_handler as fph

from dq7tt.apppaths import android_shared_dir
from dq7tt_gui import theme
from dq7tt_gui.model_setup import SetupCopy, SetupModel, SetupStep, screen_copy
from dq7tt_gui.viewmodels import Notice
from dq7tt_gui.widgets import gold_button
from dq7tt_gui.widgets_frame import ground, menu_window

log = logging.getLogger(__name__)

ACCESS = fph.Permission.MANAGE_EXTERNAL_STORAGE
PROBE_PREFIX = ".access-check-"
FOLDER_PROMPT = "Choose your Azahar folder"
WINDOW_MAX_W = 600
SIDE_MARGIN = 16
WINDOW_PADDING = 24
SPACING = 16
TITLE_SIZE = 26
TOUCH_HEIGHT = 48


def window_width(page_width: float | None) -> float:
    """As wide as WINDOW_MAX_W, narrower on a small page so a margin shows on both sides."""
    if not page_width:
        return WINDOW_MAX_W
    return max(0.0, min(WINDOW_MAX_W, page_width - 2 * SIDE_MARGIN))


def setup_view(
    copy: SetupCopy, on_click: Callable[[], object], problem: str | None, width: float
) -> ft.Control:
    """Parchment with one dark window: a Cinzel title, what to do, and one gold button."""
    lines: list[ft.Control] = [
        ft.Text(
            copy.title,
            color=theme.TITLES,
            size=TITLE_SIZE,
            weight=ft.FontWeight.W_700,
            font_family=theme.HEADING_FONT,
            text_align=ft.TextAlign.CENTER,
        ),
        ft.Text(copy.body, color=theme.TEXT, size=theme.TEXT_SIZE, text_align=ft.TextAlign.CENTER),
    ]
    if problem is not None:
        lines.append(
            ft.Text(
                problem,
                color=theme.DANGER_TEXT,
                size=theme.TEXT_SIZE,
                text_align=ft.TextAlign.CENTER,
            )
        )
    lines.append(gold_button(copy.button, on_click, height=TOUCH_HEIGHT, bold=True))
    window = menu_window(
        ft.Column(
            lines,
            spacing=SPACING,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.all(WINDOW_PADDING),
    )
    return ground(
        ft.Column(
            [
                ft.Row(
                    [ft.Container(content=window, width=width)],
                    alignment=ft.MainAxisAlignment.CENTER,
                )
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
    )


def storage_writable() -> bool:
    """A second opinion on access: can a file be made in the app's visible folder?

    Listing internal storage is not enough: Android 13 lets any app do that.
    """
    folder = android_shared_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=PROBE_PREFIX, dir=folder)
        os.close(fd)
        os.remove(name)
    except OSError as exc:
        log.info("cannot write to %s: %s", folder.name, exc)
        return False
    return True


class AndroidSetup:
    """Shows the setup screen until access and the Azahar folder are sorted, then the window."""

    def __init__(
        self,
        page: ft.Page,
        setup: SetupModel,
        show_window: Callable[[Path | None], None],
        on_key: Callable[[ft.KeyboardEvent], None] | None = None,
        on_window_hidden: Callable[[], None] | None = None,
    ) -> None:
        """`on_key` hears the keys while a setup screen shows (the window's `setup_key`,
        which keeps B from leaving the app). `on_window_hidden` runs when a setup screen
        comes back over the window (the window's `cancel_dialogs`, so no dialog stays
        over the setup screen where B cannot reach it)."""
        self.page = page
        self.setup = setup
        self.show_window = show_window
        self.on_key = on_key
        self.on_window_hidden = on_window_hidden
        self.handler = fph.PermissionHandler()
        self.picker = ft.FilePicker()
        self._lock = asyncio.Lock()
        self._window_shown = False
        self._problem: Notice | None = None
        self._step: SetupStep | None = None

    async def start(self) -> None:
        self.page.services.extend([self.handler, self.picker])
        self.page.on_app_lifecycle_state_change = self.on_lifecycle
        await self.check()

    async def on_lifecycle(self, e: ft.AppLifecycleStateChangeEvent) -> None:
        if e.state is ft.AppLifecycleState.RESUME:
            await self.check()

    async def check(self) -> None:
        """Work out the step again and show the screen for it, or the window."""
        async with self._lock:
            step = self.setup.step(await self.has_access())
            log.info("setup step: %s", step)
            if step is SetupStep.READY:
                if not self._window_shown:
                    self._window_shown = True
                    self._problem = None
                    self.show_window(self.setup.start_source())
                return
            if self._window_shown and self.on_window_hidden is not None:
                self.on_window_hidden()
            self._window_shown = False
            if step is not self._step:
                self._problem = None
            self._show(step)

    async def has_access(self) -> bool:
        """All files access, as Android reports it; if it will not say, try storage itself."""
        status: fph.PermissionStatus | None = None
        try:
            status = await self.handler.get_status(ACCESS)
        except (RuntimeError, TimeoutError, ValueError) as exc:
            log.warning("could not ask Android about All files access: %s", exc)
        writable = storage_writable()
        log.info("All files access: %s; storage writable: %s", status, writable)
        if status is None:
            return writable
        return status is fph.PermissionStatus.GRANTED

    def _show(self, step: SetupStep, width: float | None = None) -> None:
        self._step = step
        act = self.ask_access if step is SetupStep.NEED_ACCESS else self.choose_folder
        problem = None if self._problem is None else self._problem.text
        view = setup_view(
            screen_copy(step),
            lambda: self.page.run_task(act),
            problem,
            window_width(width or self.page.width),
        )
        self.page.on_keyboard_event = self.on_key
        self.page.on_resize = self.on_resize
        self.page.controls[:] = [view]
        self.page.update()

    def on_resize(self, e: ft.PageResizeEvent) -> None:
        if self._step is not None and not self._window_shown:
            self._show(self._step, e.width)

    async def ask_access(self) -> None:
        """Android opens its All files access page; coming back runs the check again."""
        try:
            status = await self.handler.request(ACCESS)
        except (RuntimeError, TimeoutError, ValueError) as exc:
            log.warning("could not ask for All files access: %s", exc)
        else:
            log.info("All files access request returned %s", status)
        await self.check()

    async def choose_folder(self) -> None:
        picked = await self.picker.get_directory_path(dialog_title=FOLDER_PROMPT)
        log.info("Azahar folder picked: %s", picked)
        if not picked:
            return
        self._problem = self.setup.folder_picked(Path(picked))
        await self.check()
