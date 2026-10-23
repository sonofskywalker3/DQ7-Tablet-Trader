"""The compact layout's pane parts: a slim header and two-line tablet rows."""

from collections.abc import Callable
from dataclasses import dataclass

import flet as ft

from dq7tt.tablets import TabletKind
from dq7tt_gui import theme
from dq7tt_gui.model_views import tablets_text
from dq7tt_gui.viewmodels import PaneSide, PaneView, RightMode, TabletRow
from dq7tt_gui.widgets import (
    KIND_LABELS,
    KIND_SPACING,
    RowHover,
    checkbox,
    row_hover,
    row_lead,
    tablet_icon,
    text,
)
from dq7tt_gui.widgets_drag import DragPayload, draggable
from dq7tt_gui.widgets_focus import (
    FOCUS_RING_W,
    FocusChange,
    focus_button,
    focus_ring,
    keep_page_text,
)
from dq7tt_gui.widgets_strip import key_cap

STONE_SIZE = 30
ROW_GAP = 8
ROW_PADDING_R = 12
LINE_GAP = 1
META_GAP = 8
BADGE_PAD_H = 6
# The serif capitals sit high in their line, so the badge's words are nudged down to look
# centred (measured on screen: equal room above the capitals and below the baseline).
BADGE_PAD_TOP = 3
BADGE_PAD_BOTTOM = 0
BADGE_RADIUS = 3
HEAD_PAD_LEFT = 10
HEAD_PAD_RIGHT = 12
HEAD_GAP = 8
RING_CLEARANCE = 3  # between the header's focus ring and its words
HEAD_TITLE_SPACING = 1.0
SINGLE = 1


@dataclass(frozen=True)
class HeadWords:
    title: str
    detail: str
    count: str


def head_words(view: PaneView, mode: RightMode) -> HeadWords:
    """What a pane's slim header says: the log or "Bank", who and how long or the folder,
    and how many tablets."""
    if view.side is PaneSide.RIGHT and mode is RightMode.BANK:
        folder = next((c.label for c in view.folder_chips if c.active), "")
        return HeadWords(view.title, folder, view.count_text)
    chip = next((c for c in view.log_chips if c.active), None)
    count = "" if view.empty_text is not None and not view.rows else tablets_text(len(view.rows))
    if chip is None:
        return HeadWords(view.title, view.subtitle, count)
    return HeadWords(chip.label, chip.detail, count)


def clears_text(clears: int) -> str:
    return "1 clear" if clears == SINGLE else f"{clears} clears"


def kind_box(kind: TabletKind) -> ft.Container:
    """The tablet's kind in a small box edged in its colour."""
    color = theme.KIND_COLORS[kind]
    return ft.Container(
        content=ft.Text(
            KIND_LABELS[kind],
            color=color,
            size=theme.BADGE_SIZE,
            style=ft.TextStyle(letter_spacing=KIND_SPACING, height=1.0),
            max_lines=1,
        ),
        height=theme.BADGE_HEIGHT,
        padding=ft.Padding(
            left=BADGE_PAD_H, top=BADGE_PAD_TOP, right=BADGE_PAD_H, bottom=BADGE_PAD_BOTTOM
        ),
        border=ft.Border.all(1, color),
        border_radius=BADGE_RADIUS,
        alignment=ft.Alignment.CENTER,
    )


def compact_row(
    row: TabletRow,
    on_toggle: Callable[[str], object],
    *,
    height: float,
    drag: DragPayload | None = None,
    grip: ft.Control | None = None,
    on_hover: RowHover | None = None,
    touch: bool = False,
    on_focus: FocusChange | None = None,
    autofocus: bool = False,
) -> ft.Container:
    """One tablet on two lines: its name, then its kind and how many clears.

    The left edge is kept for the pointer, as in the wide rows; with `on_focus` it takes
    the D-pad's focus (see `row_lead`).
    """
    name_color = theme.SELECTED_TEXT if row.selected else theme.TEXT
    lines = ft.Column(
        [
            text(row.name, color=name_color, size=theme.COMPACT_NAME_SIZE, line_height=1.0),
            ft.Row(
                [
                    kind_box(row.kind),
                    text(clears_text(row.clears), color=theme.DIM, size=theme.COMPACT_META_SIZE),
                ],
                spacing=META_GAP,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        spacing=LINE_GAP,
        tight=True,
        alignment=ft.MainAxisAlignment.CENTER,
    )
    body: ft.Control = lines if drag is None else draggable(lines, row, drag, touch)

    def toggle(_e: ft.Event[ft.Container]) -> None:
        on_toggle(row.key)

    cells = ft.Container(
        content=ft.Row(
            [
                checkbox(row.selected),
                tablet_icon(row.kind, STONE_SIZE),
                ft.Container(content=body, expand=True),
            ],
            spacing=ROW_GAP,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        height=height,
        padding=ft.Padding.only(right=ROW_PADDING_R),
        expand=True,
        on_click=toggle,
        data=row.key,
    )
    lead = row_lead(row.key, on_toggle, height, on_focus, autofocus)
    parts: list[ft.Control] = [lead] if grip is None else [lead, grip]
    return ft.Container(
        content=ft.Row([*parts, cells], spacing=0),
        bgcolor=theme.SELECTED_BG if row.selected else None,
        on_hover=None if on_hover is None else row_hover(row.index, on_hover),
        data=row.key,
    )


def pane_head(
    view: PaneView,
    mode: RightMode,
    *,
    active: bool,
    key: str | None,
    on_click: Callable[[], object] | None = None,
    focusable: bool = False,
) -> ft.Container:
    """A pane's 32 px header: the controller key, the title, the detail and the count.

    `focusable` (Android): the D-pad can reach it and A presses it, as a tap does.
    """
    words = head_words(view, mode)
    parts: list[ft.Control] = [] if key is None else [key_cap(key)]
    parts += [
        ft.Text(
            words.title.upper(),
            color=theme.GOLD_TEXT if active else theme.TEXT,
            size=theme.PANE_TITLE_SIZE,
            weight=ft.FontWeight.W_700,
            font_family=theme.HEADING_FONT,
            style=ft.TextStyle(letter_spacing=HEAD_TITLE_SPACING),
            max_lines=1,
            no_wrap=True,
        ),
        text(words.detail, color=theme.TITLES, size=theme.PANE_HEAD_SIZE, expand=True),
        text(words.count, color=theme.TITLES, size=theme.PANE_HEAD_SIZE),
    ]
    line: ft.Control = ft.Row(
        parts, spacing=HEAD_GAP, vertical_alignment=ft.CrossAxisAlignment.CENTER
    )
    head = ft.Container(
        content=line,
        height=theme.PANE_HEAD_HEIGHT,
        padding=ft.Padding(left=HEAD_PAD_LEFT, top=0, right=HEAD_PAD_RIGHT, bottom=0),
        border=ft.Border(bottom=ft.BorderSide(1, theme.RULE)),
        on_click=None if on_click is None else (lambda _e: on_click()),
        data="head",
    )
    if focusable and on_click is not None:
        # The ring goes on a box inside the focus control: redrawing the header itself
        # would rebuild the control that has just taken the focus, and lose it.
        # Part of the header's inset moves inside the box, so the ring (drawn just inside
        # its edge) clears the words, which stay where they were.
        inset = FOCUS_RING_W + RING_CLEARANCE
        head.padding = ft.Padding(
            left=HEAD_PAD_LEFT - inset, top=0, right=HEAD_PAD_RIGHT - inset, bottom=0
        )
        inside = ft.Container(
            content=keep_page_text(line),
            height=theme.PANE_HEAD_HEIGHT,
            alignment=ft.Alignment.CENTER_LEFT,
            padding=ft.Padding(left=inset, top=0, right=inset, bottom=0),
        )
        head.content = focus_button(
            inside, on_click, data="head", radius=0, on_focus=focus_ring(inside)
        )
    return head
