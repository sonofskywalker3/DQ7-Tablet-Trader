"""Flet controls that draw the window's view models. Pure functions, no page needed."""

from collections.abc import Callable

import flet as ft

from dq7tt.savefile import SlotRole
from dq7tt.tablets import TabletKind
from dq7tt_gui import art, theme
from dq7tt_gui.viewmodels import FolderChip, LogChip, TabletRow
from dq7tt_gui.widgets_drag import DragPayload, draggable

KIND_LABELS: dict[TabletKind, str] = {
    TabletKind.DLC: "DLC",
    TabletKind.STORY: "Story",
    TabletKind.RESIDENT: "Resident",
    TabletKind.STREETPASS: "StreetPass",
    TabletKind.UNKNOWN: "Unknown",
}

# A row, left to right: pointer, (grip), check box, stone, name, kind, clears.
KIND_COLUMN_W = 86
CLEARS_COLUMN_W = 44
CHECK_SIZE = 22
CHECK_MARK_SIZE = 17
CHECK_RADIUS = 4
ICON_SIZE = 32
ROW_GAP = 10
POINTER_LEFT = 3
ROW_INSET = POINTER_LEFT + theme.POINTER_W + 1  # left of the first cell: room for the pointer
ROW_PADDING_R = 18
GRIP_SIZE = 18
GRIP_SLOT = GRIP_SIZE + ROW_GAP
NAME_START = CHECK_SIZE + ICON_SIZE + 2 * ROW_GAP  # from the first cell to the name
KIND_SPACING = 0.4

BUTTON_RADIUS = theme.CONTROL_RADIUS
CHIP_HEIGHT = 54
# The narrowest a log chip gets: room for "Quick save 6/24".
LOG_CHIP_MIN_W = 130
CHIP_PADDING_H = 6
CHIP_TEXT_GAP = 6
CHIP_GAP = 8
FOLDER_CHIP_HEIGHT = 40
FOLDER_CHIP_PADDING_H = 16
BAR_BUTTON_HEIGHT = 44
BUTTON_PADDING_H = 16
HISTORY_LABEL_MAX_W = 240
HISTORY_LABEL_FIT_CHARS = 26
ICON_GAP = 8
BUTTON_ICON_SIZE = 18

Callback = Callable[[], object]


def text(
    value: str,
    *,
    color: str = theme.TEXT,
    size: float = theme.TEXT_SIZE,
    weight: ft.FontWeight | None = None,
    expand: bool = False,
    width: float | None = None,
    spacing: float | None = None,
) -> ft.Text:
    return ft.Text(
        value,
        color=color,
        size=size,
        weight=weight,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
        expand=expand or None,
        width=width,
        style=None if spacing is None else ft.TextStyle(letter_spacing=spacing),
    )


def hover_overlay() -> dict[ft.ControlState, str]:
    """A gold wash while the mouse is over a button or it is pressed."""
    return {ft.ControlState.HOVERED: theme.HOVER, ft.ControlState.PRESSED: theme.PRESSED}


def bar_button(
    label: str,
    on_click: Callback,
    *,
    height: int = BAR_BUTTON_HEIGHT,
    color: str = theme.TEXT,
    bgcolor: str | None = theme.CONTROL,
    border: str | None = theme.CONTROL_BORDER,
    border_width: float = theme.CONTROL_EDGE_W,
    disabled: bool = False,
    bold: bool = False,
    size: float = theme.TEXT_SIZE,
    radius: int = BUTTON_RADIUS,
    max_text_width: int | None = None,
    icon: ft.IconData | None = None,
    padding_h: int = BUTTON_PADDING_H,
) -> ft.Button:
    """A button in a menu window; outlined in white unless told otherwise."""
    shown = theme.DIM if disabled else color
    fits = max_text_width is None or len(label) <= HISTORY_LABEL_FIT_CHARS
    caption: ft.Control = text(
        label,
        color=shown,
        size=size,
        weight=ft.FontWeight.W_600 if bold else None,
        width=None if fits else max_text_width,
    )
    if icon is not None:
        mark = ft.Icon(icon, color=theme.DIM if disabled else theme.MUTED, size=BUTTON_ICON_SIZE)
        caption = ft.Row([mark, caption], spacing=ICON_GAP, tight=True)
    return ft.Button(
        content=caption,
        tooltip=None if fits else label,
        height=height,
        disabled=disabled,
        on_click=lambda _e: on_click(),
        style=ft.ButtonStyle(
            bgcolor=bgcolor,
            color=shown,
            overlay_color=hover_overlay(),
            shadow_color=theme.CLEAR,
            elevation=0,
            shape=ft.RoundedRectangleBorder(radius=radius),
            side=ft.BorderSide(border_width, border) if border else None,
            padding=ft.Padding.symmetric(horizontal=padding_h),
        ),
    )


def plain_button(label: str, on_click: Callback, **kw: object) -> ft.Button:
    """A borderless choice, like the entries of a game menu."""
    return bar_button(label, on_click, bgcolor=theme.CLEAR, border=None, **kw)  # type: ignore[arg-type]


def gold_button(label: str, on_click: Callback, **kw: object) -> ft.Button:
    """The choice most likely wanted: a gold edge and a gold wash."""
    return bar_button(
        label,
        on_click,
        color=theme.GOLD_TEXT,
        bgcolor=theme.GOLD_WASH,
        border=theme.GOLD,
        border_width=theme.WINDOW_EDGE_W,
        **kw,  # type: ignore[arg-type]
    )


def danger_button(label: str, on_click: Callback, **kw: object) -> ft.Button:
    return bar_button(
        label,
        on_click,
        color=theme.DANGER_TEXT,
        bgcolor=theme.DANGER_BG,
        border=theme.DANGER_BORDER,
        **kw,  # type: ignore[arg-type]
    )


def write_button(label: str, on_click: Callback, can_write: bool) -> ft.Container:
    """Write changes: solid gold with a glow while there is something to write."""
    if not can_write:
        return ft.Container(content=bar_button(label, on_click, disabled=True, bgcolor=theme.CLEAR))
    button = bar_button(
        label,
        on_click,
        color=theme.ACCENT_TEXT,
        bgcolor=theme.ACCENT,
        border=theme.ACCENT_EDGE,
        border_width=theme.WINDOW_EDGE_W,
        size=theme.CLEARS_SIZE,
        bold=True,
    )
    return ft.Container(
        content=button,
        border_radius=BUTTON_RADIUS,
        shadow=[
            ft.BoxShadow(spread_radius=theme.WINDOW_RING_W, color=theme.ACCENT_RING),
            ft.BoxShadow(blur_radius=14, color=theme.ACCENT_GLOW),
        ],
    )


def kind_badge(kind: TabletKind) -> ft.Container:
    """The tablet's kind, written in its own colour."""
    return ft.Container(
        content=text(
            KIND_LABELS[kind],
            color=theme.KIND_COLORS[kind],
            size=theme.SMALL_SIZE,
            spacing=KIND_SPACING,
        )
    )


def tablet_icon(kind: TabletKind) -> ft.Image:
    return ft.Image(src=art.TABLET_ICONS[kind], width=ICON_SIZE, height=ICON_SIZE)


def _checkbox(selected: bool) -> ft.Container:
    return ft.Container(
        content=(
            ft.Icon(ft.Icons.CHECK_ROUNDED, color=theme.CHECK_MARK, size=CHECK_MARK_SIZE)
            if selected
            else None
        ),
        width=CHECK_SIZE,
        height=CHECK_SIZE,
        border_radius=CHECK_RADIUS,
        border=ft.Border.all(theme.WINDOW_EDGE_W, theme.GOLD if selected else theme.CHECK_BORDER),
        bgcolor=theme.GOLD if selected else None,
        alignment=ft.Alignment.CENTER,
    )


# Told a row's position and whether the mouse came onto it (True) or left it (False).
type RowHover = Callable[[int, bool], object]


def tablet_row(
    row: TabletRow,
    on_toggle: Callable[[str], object],
    drag: DragPayload | None = None,
    grip: ft.Control | None = None,
    on_hover: RowHover | None = None,
) -> ft.Container:
    """One tablet; a tick washes it gold.

    Its left edge is kept clear for the pointer, which the pane floats over the row the
    mouse is on (`on_hover` tells it). The grip (when the list can be reordered) sits
    outside the parts that toggle the tick, so pressing it only ever starts a reorder.
    """
    name_color = theme.SELECTED_TEXT if row.selected else theme.TEXT
    name: ft.Control = text(row.name, color=name_color, size=theme.NAME_SIZE, expand=drag is None)
    if drag is not None:
        # A Draggable does not take part in the row's flex, so a container holds the room
        # the name is given and the kind and clears stay in their columns.
        name = ft.Container(content=draggable(name, row, drag), expand=True)
    cells = ft.Container(
        content=ft.Row(
            [
                _checkbox(row.selected),
                tablet_icon(row.kind),
                name,
                ft.Container(
                    content=kind_badge(row.kind),
                    width=KIND_COLUMN_W,
                    alignment=ft.Alignment.CENTER_LEFT,
                ),
                ft.Container(
                    content=text(str(row.clears), size=theme.CLEARS_SIZE),
                    width=CLEARS_COLUMN_W,
                    alignment=ft.Alignment.CENTER_RIGHT,
                ),
            ],
            spacing=ROW_GAP,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        height=theme.ROW_HEIGHT,
        padding=ft.Padding.only(right=ROW_PADDING_R),
        expand=True,
        on_click=lambda _e: on_toggle(row.key),
        data=row.key,
    )
    lead = ft.Container(
        width=ROW_INSET,
        height=theme.ROW_HEIGHT,
        on_click=lambda _e: on_toggle(row.key),
    )
    parts: list[ft.Control] = [lead] if grip is None else [lead, grip]
    return ft.Container(
        content=ft.Row([*parts, cells], spacing=0),
        bgcolor=theme.SELECTED_BG if row.selected else None,
        on_hover=None if on_hover is None else _hover(row.index, on_hover),
        data=row.key,
    )


def _hover(index: int, on_hover: RowHover) -> Callable[[ft.Event[ft.Container]], None]:
    def handler(e: ft.Event[ft.Container]) -> None:
        on_hover(index, e.data is True or e.data == "true")

    return handler


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
