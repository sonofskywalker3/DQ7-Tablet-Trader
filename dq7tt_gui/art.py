"""The window's pictures and fonts: where they live, and setting up a page to use them.

The files sit in the package's assets folder, beside this module, both when run from the
source tree and inside the packed exe (the build copies the folder to the same place under
the bundle). Image and font paths below are relative to that folder, as Flet expects.
"""

from pathlib import Path

import flet as ft

from dq7tt.tablets import TabletKind
from dq7tt_gui import theme

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
SCROLLBAR_RADIUS = 2

PARCHMENT = "parchment.png"
BAND_TOP = "band_top.png"
BAND_BOTTOM = "band_bottom.png"
COMPASS = "compass.svg"
COMPASS_FAINT = "compass_faint.svg"
POINTER = "pointer.svg"
TABLET_ICONS: dict[TabletKind, str] = {
    TabletKind.STORY: "tablets/story.svg",
    TabletKind.DLC: "tablets/dlc.svg",
    TabletKind.RESIDENT: "tablets/resident.svg",
    TabletKind.STREETPASS: "tablets/streetpass.svg",
    TabletKind.UNKNOWN: "tablets/unknown.svg",
}
FONTS: dict[str, str] = {
    theme.BODY_FONT: "fonts/SortsMillGoudyLining-Regular.ttf",
    theme.HEADING_FONT: "fonts/Cinzel.ttf",
}


def asset_files() -> list[str]:
    """Every asset path the window refers to, relative to ASSETS_DIR."""
    return [
        PARCHMENT,
        BAND_TOP,
        BAND_BOTTOM,
        COMPASS,
        COMPASS_FAINT,
        POINTER,
        *TABLET_ICONS.values(),
        *FONTS.values(),
    ]


def page_theme() -> ft.Theme:
    """Serif text everywhere, and slim pale scrollbars to suit the menu windows."""
    return ft.Theme(
        font_family=theme.BODY_FONT,
        scrollbar_theme=ft.ScrollbarTheme(
            thumb_color=theme.SCROLL_THUMB,
            track_color=theme.SCROLL_TRACK,
            radius=SCROLLBAR_RADIUS,
        ),
    )


def style_page(page: ft.Page) -> None:
    """Register the fonts and set the page's theme, size limits and ground colour."""
    page.fonts = dict(FONTS)
    page.theme = page_theme()
    page.dark_theme = page_theme()
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = theme.BG
    page.padding = 0
    page.window.width = theme.WINDOW_W
    page.window.height = theme.WINDOW_H
    page.window.min_width = theme.MIN_W
    page.window.min_height = theme.MIN_H
