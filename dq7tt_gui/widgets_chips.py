"""The chips a pane shows: its save's logs, and the bank's folders."""

from collections.abc import Callable

import flet as ft

from dq7tt.savefile import SlotRole
from dq7tt_gui import theme
from dq7tt_gui.viewmodels import FolderChip, LogChip
from dq7tt_gui.widgets import BUTTON_RADIUS, ROW_GAP, Callback, text

CHIP_HEIGHT = 54
# The narrowest a log chip gets: room for "Quick save 6/24".
LOG_CHIP_MIN_W = 130
CHIP_PADDING_H = 6
CHIP_TEXT_GAP = 6
CHIP_GAP = 8
FOLDER_CHIP_HEIGHT = 40
FOLDER_CHIP_PADDING_H = 16


def _chip(
    parts: ft.Control,
    *,
    active: bool,
    muted: bool,
    height: int,
    padding_h: int,
    on_click: Callback,
    data: object,
    aligned: bool = False,
) -> ft.Container:
    if active:
        border, edge, bg = theme.GOLD, theme.WINDOW_EDGE_W, theme.GOLD_WASH
    elif muted:
        border, edge, bg = theme.CHIP_BORDER, theme.CONTROL_EDGE_W, None
    else:
        border, edge, bg = theme.CHIP_BORDER, theme.CONTROL_EDGE_W, theme.CHIP
    return ft.Container(
        content=parts,
        height=height,
        padding=ft.Padding.symmetric(horizontal=padding_h),
        border_radius=BUTTON_RADIUS,
        border=ft.Border.all(edge, border),
        bgcolor=bg,
        # Only a chip given its width by its line is aligned; one sized by its text (in a
        # wrapping row) would be stretched across the line by the alignment.
        alignment=ft.Alignment.CENTER_LEFT if aligned else None,
        ink=True,
        on_click=lambda _e: on_click(),
        data=data,
    )


def log_chip(chip: LogChip, on_pick: Callable[[SlotRole], object]) -> ft.Container:
    """A log to show: its name and count on top, who plays it and for how long below."""
    if chip.muted:
        title_color = detail_color = theme.DIM
    elif chip.active:
        title_color, detail_color = theme.GOLD_TEXT, theme.MUTED
    else:
        title_color, detail_color = theme.TEXT, theme.MUTED
    top: list[ft.Control] = [text(chip.label, color=title_color, expand=True)]
    if chip.fill:
        top.append(text(chip.fill, color=detail_color, size=theme.DETAIL_SIZE))
    lines: list[ft.Control] = [
        ft.Row(top, spacing=CHIP_TEXT_GAP, vertical_alignment=ft.CrossAxisAlignment.END)
    ]
    if chip.detail:
        lines.append(text(chip.detail, color=detail_color, size=theme.DETAIL_SIZE))
    return _chip(
        ft.Column(lines, spacing=2, tight=True, alignment=ft.MainAxisAlignment.CENTER),
        active=chip.active,
        muted=chip.muted,
        height=CHIP_HEIGHT,
        padding_h=CHIP_PADDING_H,
        on_click=lambda: on_pick(chip.role),
        data=chip.role,
        aligned=True,
    )


def folder_chip(chip: FolderChip, on_pick: Callable[[str], object]) -> ft.Container:
    return _chip(
        ft.Row(
            [
                text(chip.label, color=theme.GOLD_TEXT if chip.active else theme.TEXT),
                text(str(chip.count), color=theme.TEXT if chip.active else theme.MUTED),
            ],
            spacing=ROW_GAP,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        active=chip.active,
        muted=False,
        height=FOLDER_CHIP_HEIGHT,
        padding_h=FOLDER_CHIP_PADDING_H,
        on_click=lambda: on_pick(chip.name),
        data=chip.name,
    )
