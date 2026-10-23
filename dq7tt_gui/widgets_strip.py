"""The compact layout's two slim strips and the controls drawn in them.

Each strip is a menu window 48 px tall. Its controls are drawn 36 px tall, but each sits in
a tap area the full height of the strip, so a finger that lands just above or below a
button still presses it.
"""

from dataclasses import dataclass

import flet as ft

from dq7tt_gui import theme
from dq7tt_gui.widgets import BUTTON_ICON_SIZE, BUTTON_RADIUS, Callback, text
from dq7tt_gui.widgets_focus import focus_button, focus_ring, keep_page_text
from dq7tt_gui.widgets_frame import menu_window

STRIP_PAD_LEFT = theme.WINDOW_RING_W + theme.WINDOW_EDGE_W + 6
STRIP_PAD_RIGHT = theme.WINDOW_RING_W + theme.WINDOW_EDGE_W + 4
# The strip's two columns line up with the panes below them.
COLUMN_GAP = theme.COMPACT_GAP + 2 * (theme.WINDOW_EDGE_W + theme.WINDOW_RING_W)
STRIP_SPACING = 4
BUTTON_PAD_H = 8
ICON_ONLY_PAD_H = 8
CAPTION_GAP = 4
CAP_HEIGHT = 18
CAP_PAD_H = 4
CAP_RADIUS = 4
CAP_SPACING = 0.3
SEPARATOR_H = 26
WRITE_GLOW = 14
WRITE_MARGIN_R = 2


@dataclass(frozen=True)
class Look:
    """How a strip control is drawn: its fill, its edge and the colour of its words."""

    bg: str | None
    edge: str | None
    edge_w: float
    color: str
    bold: bool = False


CHIP = Look(theme.CHIP, theme.CHIP_BORDER, theme.CONTROL_EDGE_W, theme.TEXT)
CHIP_ON = Look(theme.GOLD_WASH, theme.GOLD, theme.WINDOW_EDGE_W, theme.GOLD_TEXT)
OUTLINE = Look(theme.CONTROL, theme.CONTROL_BORDER, theme.CONTROL_EDGE_W, theme.TEXT)
PLAIN = Look(None, None, 0, theme.TEXT)
GOLD = Look(theme.GOLD_WASH, theme.GOLD, theme.WINDOW_EDGE_W, theme.GOLD_TEXT)
DANGER = Look(theme.DANGER_BG, theme.DANGER_BORDER, theme.CONTROL_EDGE_W, theme.DANGER_TEXT)
WRITE = Look(theme.ACCENT, theme.ACCENT_EDGE, theme.WINDOW_EDGE_W, theme.ACCENT_TEXT, bold=True)
DISABLED = Look(None, None, 0, theme.DIM)


def strip(content: ft.Control) -> ft.Container:
    """A slim menu window across the screen with `content` laid over its full height."""
    return ft.Container(
        content=ft.Stack(
            [
                menu_window(None),
                ft.Container(
                    content=content,
                    padding=ft.Padding(left=STRIP_PAD_LEFT, top=0, right=STRIP_PAD_RIGHT, bottom=0),
                ),
            ],
            fit=ft.StackFit.EXPAND,
        ),
        height=theme.STRIP_HEIGHT,
    )


def columns(left: ft.Control, right: ft.Control) -> ft.Row:
    """Two halves, each over one pane."""
    return ft.Row(
        [ft.Container(content=left, expand=True), ft.Container(content=right, expand=True)],
        spacing=COLUMN_GAP,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def group(controls: list[ft.Control], end: bool = False) -> ft.Row:
    return ft.Row(
        controls,
        spacing=STRIP_SPACING,
        alignment=ft.MainAxisAlignment.END if end else ft.MainAxisAlignment.START,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def key_cap(label: str, color: str = theme.MUTED, edge: str = theme.CHIP_BORDER) -> ft.Container:
    """A controller key's name in a small box, like the "L" over the save."""
    return ft.Container(
        content=ft.Text(
            label,
            color=color,
            size=theme.KEY_CAP_SIZE,
            weight=ft.FontWeight.W_700,
            font_family=theme.HEADING_FONT,
            style=ft.TextStyle(letter_spacing=CAP_SPACING, height=1.0),
        ),
        height=CAP_HEIGHT,
        width=CAP_HEIGHT if len(label) == 1 else None,
        padding=ft.Padding.symmetric(horizontal=0 if len(label) == 1 else CAP_PAD_H),
        border=ft.Border.all(1, edge),
        border_radius=CAP_RADIUS,
        alignment=ft.Alignment.CENTER,
    )


def caption(
    label: str | None,
    look: Look,
    *,
    icon: ft.IconData | None = None,
    after_icon: ft.IconData | None = None,
    extra: str | None = None,
    cap: str | None = None,
    width: float | None = None,
) -> ft.Control:
    """A control's words, with an icon before or after, a count in muted text, or a key.

    `width` holds the words to that width, ending in "..." (a long bank folder name).
    """
    parts: list[ft.Control] = []
    icon_color = theme.DIM if look is DISABLED else theme.MUTED
    if icon is not None:
        parts.append(ft.Icon(icon, color=icon_color, size=BUTTON_ICON_SIZE))
    if label is not None:
        weight = ft.FontWeight.W_600 if look.bold else None
        size = theme.BUTTON_TEXT_SIZE
        parts.append(text(label, color=look.color, size=size, weight=weight, width=width))
    if extra is not None:
        parts.append(text(extra, color=theme.MUTED, size=theme.DETAIL_SIZE))
    if after_icon is not None:
        parts.append(ft.Icon(after_icon, color=icon_color, size=BUTTON_ICON_SIZE))
    if cap is not None:
        parts.append(key_cap(cap, look.color, look.color))
    return ft.Row(
        parts,
        spacing=CAPTION_GAP,
        tight=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def strip_button(
    content: ft.Control,
    on_click: Callback | None,
    look: Look,
    *,
    data: object = None,
    icon_only: bool = False,
    tooltip: str | None = None,
    focusable: bool = False,
) -> ft.Container:
    """A control drawn 36 px tall in a tap area the strip's full height.

    `on_click` None draws it as there but not usable (Undo with nothing to undo).
    `focusable` (Android): the D-pad can reach it, A presses it and a gold ring shows it.
    """
    act = None if on_click is None else (lambda _e: on_click())
    visual = ft.Container(
        content=content,
        height=theme.STRIP_BUTTON_HEIGHT,
        padding=ft.Padding.symmetric(horizontal=ICON_ONLY_PAD_H if icon_only else BUTTON_PAD_H),
        bgcolor=look.bg,
        border=ft.Border.all(look.edge_w, look.edge) if look.edge else None,
        border_radius=BUTTON_RADIUS,
        alignment=ft.Alignment.CENTER,
        ink=on_click is not None and not focusable,
        on_click=None if focusable else act,
        tooltip=tooltip,
    )
    if look is WRITE:
        visual.shadow = [
            ft.BoxShadow(spread_radius=theme.WINDOW_RING_W, color=theme.ACCENT_RING),
            ft.BoxShadow(blur_radius=WRITE_GLOW, color=theme.ACCENT_GLOW),
        ]
        visual.margin = ft.Margin.only(right=WRITE_MARGIN_R)
    shown: ft.Control = visual
    if focusable:
        shown = focus_button(
            keep_page_text(visual), on_click, data=data, on_focus=focus_ring(visual)
        )
    return ft.Container(
        content=shown,
        height=theme.STRIP_HEIGHT,
        alignment=ft.Alignment.CENTER,
        on_click=act,
        data=data,
    )


def separator() -> ft.Container:
    return ft.Container(width=1, height=SEPARATOR_H, bgcolor=theme.RULE)
