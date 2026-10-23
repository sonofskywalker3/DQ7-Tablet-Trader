"""Colours, fonts and sizes for the desktop window.

The look is an adventure log: aged parchment for the ground, and on it dark, slightly
see-through menu windows with a thin white rounded edge and white serif text. A gold pointer
marks where you are; ticked rows get a gold wash.
"""

import flet as ft

from dq7tt.tablets import TabletKind
from dq7tt_gui.layout import NARROW_WIDTH as NARROW_WIDTH  # the wide layout from here


def _alpha(opacity: float, colour: str) -> str:
    return ft.Colors.with_opacity(opacity, colour)


# Fonts (bundled under assets/fonts, registered by art.style_page)
BODY_FONT = "Sorts Mill Goudy Lining"  # lining digits; see tools/build_lining_font.py
HEADING_FONT = "Cinzel"

# The parchment ground and the ink drawn straight onto it
BG = "#d3bc8c"
# The lightest and darkest stops of the parchment art's gradient (tools/build_gui_art.py).
PARCHMENT_LIGHT = "#e3d0a4"
PARCHMENT_DARK = "#b39867"
INK = "#3b2a12"

# Menu windows
WINDOW_BG = _alpha(0.9, "#1e1914")
DIALOG_BG = _alpha(0.95, "#1e1914")
WINDOW_EDGE = "#f3efe4"
WINDOW_RING = _alpha(0.85, "#281c0c")
WINDOW_DROP = _alpha(0.35, "#3c280a")
BARRIER = _alpha(0.5, "#1e1406")
RULE = _alpha(0.35, "#f3efe4")

# Text inside windows
TEXT = "#f6f1e4"
MUTED = "#e2d3ae"
TITLES = "#dccb9f"
DIM = "#b3a78f"
TAB_OFF = "#cbbd9c"

# Controls inside windows
CONTROL = _alpha(0.04, "#ffffff")
CLEAR = _alpha(0.0, "#000000")  # no fill (a plain "transparent" is not honoured by buttons)
CONTROL_BORDER = _alpha(0.6, "#f3efe4")
CHIP = _alpha(0.03, "#ffffff")
CHIP_BORDER = _alpha(0.45, "#f3efe4")
HOVER = _alpha(0.13, "#f0c860")
PRESSED = _alpha(0.22, "#f0c860")
GRIP = "#bfb39a"
SCROLL_THUMB = _alpha(0.6, "#f3efe4")
SCROLL_TRACK = _alpha(0.15, "#f3efe4")

# Gold: the pointer, the active chip, ticked rows
GOLD = "#f0c860"
GOLD_TEXT = "#f7d27a"
GOLD_WASH = _alpha(0.14, "#f0c860")
SELECTED_BG = _alpha(0.16, "#f0c860")
SELECTED_TEXT = "#fff4d6"
CHECK_BORDER = _alpha(0.7, "#f6f1e4")
CHECK_MARK = "#2a1c04"

# The Write button and other first choices
ACCENT = "#ebbf52"
ACCENT_EDGE = "#fff1c2"
ACCENT_RING = "#6a4a10"
ACCENT_GLOW = _alpha(0.55, "#f7d670")
ACCENT_TEXT = "#2b1b04"

DANGER_BORDER = "#ff9b8b"
DANGER_BG = _alpha(0.08, "#ff7864")
DANGER_TEXT = "#ffab9e"
ERROR_WINDOW = _alpha(0.95, "#3a1a14")

# kind -> the colour its name is written in
KIND_COLORS: dict[TabletKind, str] = {
    TabletKind.DLC: "#a9cdfa",
    TabletKind.STORY: "#f1c860",
    TabletKind.RESIDENT: "#b4e09a",
    TabletKind.STREETPASS: "#d5bcff",
    TabletKind.UNKNOWN: "#cfc7b6",
}

# Window frame
WINDOW_RADIUS = 7
WINDOW_EDGE_W = 2
WINDOW_RING_W = 2
WINDOW_DROP_BLUR = 14
WINDOW_DROP_Y = 6
BAND_HEIGHT = 26
FRAME_MARGIN = 20
FRAME_MARGIN_NARROW = 8
FRAME_GAP = 12
FRAME_GAP_NARROW = 8
PANE_GAP = 16
CONTROL_EDGE_W = 1.5
CONTROL_RADIUS = 5
POINTER_W = 30
POINTER_H = 18

# Text sizes
TEXT_SIZE = 17
SMALL_SIZE = 15
BUTTON_TEXT_SIZE = 16
DETAIL_SIZE = 14
TITLE_SIZE = 21
TAB_SIZE = 20
NAME_SIZE = 19
CLEARS_SIZE = 18
DIALOG_TITLE_SIZE = 23
LOGO_SMALL_SIZE = 13
LOGO_SIZE = 25

ROW_HEIGHT = 40
# Android rows are touch targets: 48 dp at the least.
ANDROID_ROW_HEIGHT = 48
# The compact layouts' two-line rows need 48 on every platform.
COMPACT_ROW_HEIGHT = 48
PANE_RADIUS = WINDOW_RADIUS

# The compact layout (the Thor's top screen): slim strips, small gaps, two-line rows.
STRIP_HEIGHT = 48
STRIP_BUTTON_HEIGHT = 36
COMPACT_GAP = 6
PANE_HEAD_HEIGHT = 32
COMPACT_NAME_SIZE = 18
COMPACT_META_SIZE = 13
BADGE_SIZE = 12
BADGE_HEIGHT = 18
PANE_HEAD_SIZE = 14
PANE_TITLE_SIZE = 13
KEY_CAP_SIZE = 11
WINDOW_W = 1280
WINDOW_H = 800
MIN_W = 480
MIN_H = 520
