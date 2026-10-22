"""Entry point for the desktop window."""

import logging
import logging.handlers
import os
from pathlib import Path

import flet as ft

from dq7tt.apppaths import AppPaths
from dq7tt.errors import TabletTraderError
from dq7tt_gui import art, theme
from dq7tt_gui.model import AppModel
from dq7tt_gui.window import APP_TITLE, Window

LOG = logging.getLogger(__name__)

SMOKE_ENV = "DQ7TT_GUI_SMOKE"
SMOKE_ON = "1"
# Puts the bank, backups, edited saves and logs under this folder (tests and trial runs).
APP_DIR_ENV = "DQ7TT_APP_DIR"
LOG_FOLDER = "logs"
LOG_FILE = "dq7tt.log"
LOG_MAX_BYTES = 500_000
LOG_BACKUPS = 2
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
START_FAILED = (
    "DQ7 Tablet Trader could not start. Something it needs when it opens could not be read "
    "or set up. Try downloading the app again."
)
LOG_WHERE = "The log file says what went wrong: {path}"
ERROR_PADDING = 24


def app_paths() -> AppPaths:
    """The app's folders: under DQ7TT_APP_DIR when it is set, else the usual places."""
    override = os.environ.get(APP_DIR_ENV)
    return AppPaths.under(Path(override)) if override else AppPaths.default()


def log_file(paths: AppPaths) -> Path:
    return paths.data_dir / LOG_FOLDER / LOG_FILE


def start_failed_text(paths: AppPaths | None) -> str:
    """What the window says when it cannot start, with the log file's place when known."""
    if paths is None:
        return START_FAILED
    return f"{START_FAILED} {LOG_WHERE.format(path=log_file(paths))}"


def setup_logging(paths: AppPaths) -> None:
    """Send diagnostics to a log file in the app data folder (the packed exe has no console).

    If the log folder cannot be made, the app still opens and logs to the console only.
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    log_path = log_file(paths)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
        )
    except OSError as exc:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(handler)
        LOG.warning("no log file, logging to the console only: %s", exc)
        return
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)


def _show_start_failure(page: ft.Page, paths: AppPaths | None) -> None:
    """The reason the app could not start, in a dark window edged in red."""
    page.add(
        ft.Container(
            content=ft.Text(
                start_failed_text(paths),
                color=theme.DANGER_TEXT,
                size=theme.TEXT_SIZE,
                selectable=True,
            ),
            padding=ERROR_PADDING,
            margin=ERROR_PADDING,
            bgcolor=theme.ERROR_WINDOW,
            border=ft.Border.all(theme.WINDOW_EDGE_W, theme.DANGER_BORDER),
            border_radius=theme.WINDOW_RADIUS,
        )
    )


async def main(page: ft.Page) -> None:
    """Build the window; in smoke mode close it right after the first render."""
    page.title = APP_TITLE
    art.style_page(page)
    paths: AppPaths | None = None
    try:
        paths = app_paths()
        model = AppModel(paths)
    except (OSError, ValueError, KeyError, TabletTraderError):
        LOG.exception("could not start")
        _show_start_failure(page, paths)
    else:
        LOG.info("window model ready")
        Window(page, model).install()
    if os.environ.get(SMOKE_ENV) == SMOKE_ON:
        LOG.info("smoke mode: closing after first render")
        await page.window.destroy()


def run() -> None:
    """Console script: open the window."""
    setup_logging(app_paths())
    ft.run(main, assets_dir=str(art.ASSETS_DIR))


if __name__ == "__main__":
    run()
