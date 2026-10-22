"""Every dialog the window raises, as pure builders that need no page.

Each is a menu window like the rest: dark, a thin white rounded edge, serif text. A list of
choices reads like a game menu, with the gold pointer beside the one under the mouse.
"""

from collections.abc import Callable, Sequence
from pathlib import Path

import flet as ft

from dq7tt_gui import theme
from dq7tt_gui.viewmodels import Confirm, Destination, FoundSave, Notice, NoticeKind
from dq7tt_gui.widgets import bar_button, gold_button, hover_overlay, text
from dq7tt_gui.widgets_frame import point_on_hover, pointer_slot

Callback = Callable[[], object]
DIALOG_WIDTH = 480
DIALOG_BG = theme.DIALOG_BG
SNACK_SECONDS = 6
SNACK_WIDTH = 640
CANCEL_LABEL = "Cancel"
NO_SAVES_TEXT = (
    "No Dragon Quest VII saves found. Plug in your 3DS SD card or open a save folder yourself."
)
SEARCHING_TEXT = "Looking for saves..."
NO_DESTINATIONS_TEXT = "There is nowhere to send these tablets."
FOUND_TITLE = "Saves on this PC"
OPEN_TITLE = "Open a save"
OPEN_FOLDER = "Open folder"
OPEN_FILE = "Open file or zip"
FOUND_PATH_SIZE = theme.DETAIL_SIZE
SPINNER_SIZE = 28
CHOICE_HEIGHT = 50
SOURCE_BUTTON_HEIGHT = 72
LIST_SPACING = 0
# A list of options taller than this scrolls inside the dialog.
LIST_MAX_HEIGHT = 360
SIDE = 24
CHOICE_LEFT = 12
CHOICE_GAP = 12
BODY_GAP = 10
LIST_PADDING_V = 8
TITLE_PADDING = ft.Padding(left=SIDE, top=16, right=SIDE, bottom=10)
ACTIONS_PADDING = ft.Padding(left=18, top=12, right=18, bottom=14)
TEXT_PADDING = ft.Padding(left=SIDE, top=14, right=SIDE, bottom=14)
LIST_PADDING = ft.Padding(left=0, top=LIST_PADDING_V, right=0, bottom=LIST_PADDING_V)


def _window_shape(edge: str = theme.WINDOW_EDGE) -> ft.RoundedRectangleBorder:
    return ft.RoundedRectangleBorder(
        radius=theme.WINDOW_RADIUS, side=ft.BorderSide(theme.WINDOW_EDGE_W, edge)
    )


def snack(notice: Notice) -> ft.SnackBar:
    """One notice as a small floating window; errors are edged and written in red."""
    error = notice.kind is NoticeKind.ERROR
    return ft.SnackBar(
        content=ft.Text(
            notice.text,
            color=theme.DANGER_TEXT if error else theme.TEXT,
            size=theme.TEXT_SIZE,
        ),
        bgcolor=theme.ERROR_WINDOW if error else DIALOG_BG,
        shape=_window_shape(theme.DANGER_BORDER if error else theme.WINDOW_EDGE),
        behavior=ft.SnackBarBehavior.FLOATING,
        width=SNACK_WIDTH,
        duration=SNACK_SECONDS * 1000,
    )


def _dialog(
    title: str,
    content: ft.Control,
    actions: list[ft.Control],
    on_dismiss: Callback,
    *,
    listing: bool = False,
) -> ft.AlertDialog:
    """A dialog window: its title over a hairline, the body, a hairline, then the buttons.

    A list of choices (`listing`) runs from edge to edge so the gold wash under the mouse
    fills the line; anything else is inset like the title.
    """
    rule = ft.BorderSide(1, theme.RULE)
    return ft.AlertDialog(
        modal=True,
        title=ft.Text(title, color=theme.TEXT, size=theme.DIALOG_TITLE_SIZE),
        content=ft.Container(
            content=content,
            width=DIALOG_WIDTH,
            padding=LIST_PADDING if listing else TEXT_PADDING,
            border=ft.Border(top=rule, bottom=rule),
        ),
        actions=actions,
        bgcolor=DIALOG_BG,
        shape=_window_shape(),
        barrier_color=theme.BARRIER,
        title_padding=TITLE_PADDING,
        content_padding=ft.Padding.all(0),
        actions_padding=ACTIONS_PADDING,
        on_dismiss=lambda _e: on_dismiss(),
    )


def _option_list(items: list[ft.Control], item_height: int) -> ft.Control:
    """Options stacked in a column that fits them; past LIST_MAX_HEIGHT the column scrolls.

    A scrolling column in a dialog takes all the height it is offered, so only a list too
    long to fit is made to scroll, and then at a set height.
    """
    column = ft.Column(
        items,
        tight=True,
        spacing=LIST_SPACING,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    if len(items) * (item_height + LIST_SPACING) - LIST_SPACING <= LIST_MAX_HEIGHT:
        return column
    column.scroll = ft.ScrollMode.AUTO
    return ft.Container(content=column, height=LIST_MAX_HEIGHT)


def _cancel(on_cancel: Callback) -> ft.Button:
    return bar_button(CANCEL_LABEL, on_cancel, size=theme.CLEARS_SIZE)


def menu_choice(
    content: ft.Control,
    on_click: Callback,
    height: int = CHOICE_HEIGHT,
) -> ft.Button:
    """One line of a menu: the pointer shows beside it while the mouse is on it."""
    slot = pointer_slot(False)
    return ft.Button(
        content=ft.Row(
            [slot, content],
            spacing=CHOICE_GAP,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        height=height,
        on_click=lambda _e: on_click(),
        on_hover=point_on_hover(slot),
        style=ft.ButtonStyle(
            bgcolor=theme.CLEAR,
            shadow_color=theme.CLEAR,
            overlay_color=hover_overlay(),
            elevation=0,
            shape=ft.RoundedRectangleBorder(radius=0),
            padding=ft.Padding(left=CHOICE_LEFT, top=0, right=SIDE, bottom=0),
            alignment=ft.Alignment.CENTER_LEFT,
        ),
    )


def _choice_text(label: str, detail: str = "", dim: bool = False) -> ft.Control:
    """A choice's name, and what it holds on the right when there is something to say."""
    name = text(label, color=theme.DIM if dim else theme.TEXT, size=theme.TITLE_SIZE, expand=True)
    if not detail:
        return name
    return ft.Row(
        [name, text(detail, color=theme.DIM if dim else theme.MUTED, size=theme.SMALL_SIZE)],
        spacing=CHOICE_GAP,
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _empty(message: str) -> ft.Control:
    return ft.Container(
        content=ft.Text(message, color=theme.MUTED, size=theme.TEXT_SIZE),
        padding=ft.Padding.symmetric(horizontal=SIDE, vertical=LIST_PADDING_V),
    )


def confirm_dialog(confirm: Confirm, on_ok: Callback, on_cancel: Callback) -> ft.AlertDialog:
    """The question of a `Confirm`, like a text box in the game, with its notices under it."""
    lines: list[ft.Control] = [ft.Text(confirm.text, color=theme.TEXT, size=theme.NAME_SIZE)]
    lines += [ft.Text(n.text, color=theme.MUTED, size=theme.SMALL_SIZE) for n in confirm.notices]
    return _dialog(
        confirm.title,
        ft.Column(lines, tight=True, spacing=BODY_GAP),
        [
            bar_button(confirm.cancel_label, on_cancel, size=theme.CLEARS_SIZE),
            gold_button(confirm.ok_label, on_ok, size=theme.CLEARS_SIZE),
        ],
        on_dismiss=on_cancel,
    )


def choice_dialog(
    title: str,
    options: Sequence[tuple[str, Callback]],
    on_cancel: Callback,
    empty_text: str = "",
    details: Sequence[tuple[str, bool]] = (),
) -> ft.AlertDialog:
    """A menu of choices, one line each. `details` (text, dim) go beside them, in order."""
    body: list[ft.Control] = []
    for i, (label, pick) in enumerate(options):
        detail, dim = details[i] if i < len(details) else ("", False)
        body.append(menu_choice(_choice_text(label, detail, dim), pick))
    if not body:
        body = [_empty(empty_text)]
    return _dialog(
        title,
        _option_list(body, CHOICE_HEIGHT),
        [_cancel(on_cancel)],
        on_dismiss=on_cancel,
        listing=True,
    )


def _capitalised(label: str) -> str:
    """The first letter made upper case, the rest left as it is (unlike str.capitalize)."""
    return label[:1].upper() + label[1:]


def destination_dialog(
    dests: Sequence[Destination],
    on_pick: Callable[[Destination], object],
    on_cancel: Callback,
    title: str = "Copy to...",
) -> ft.AlertDialog:
    """Adventure logs first, then bank folders; a log says who, how long and how full.

    A full log is dimmed but still offered: the model explains what happens. A destination's
    label is written to sit mid-sentence ("Copy to bank folder Keep"), so a
    button showing it on its own starts with a capital.
    """
    ordered = sorted(dests, key=lambda d: d.kind != "log")
    options = [(_capitalised(d.label), lambda d=d: on_pick(d)) for d in ordered]
    details = [(d.detail, d.full) for d in ordered]
    return choice_dialog(title, options, on_cancel, NO_DESTINATIONS_TEXT, details)


def open_choice_dialog(
    on_folder: Callback, on_file: Callback, on_cancel: Callback
) -> ft.AlertDialog:
    return choice_dialog(OPEN_TITLE, [(OPEN_FOLDER, on_folder), (OPEN_FILE, on_file)], on_cancel)


def text_prompt(
    title: str,
    field_label: str,
    ok_label: str,
    on_ok: Callable[[str], str | None],
    on_cancel: Callback,
    on_redraw: Callback | None = None,
) -> ft.AlertDialog:
    """Ask for one line of text.

    `on_ok` returns why the text was refused, or None. A refusal stays in the open dialog
    under the field, with the typed text kept; `on_redraw` then shows it.
    """
    field = ft.TextField(
        label=field_label,
        autofocus=True,
        color=theme.TEXT,
        text_size=theme.NAME_SIZE,
        label_style=ft.TextStyle(color=theme.MUTED),
        border_color=theme.CONTROL_BORDER,
        focused_border_color=theme.GOLD,
        cursor_color=theme.GOLD,
        error_style=ft.TextStyle(color=theme.DANGER_TEXT),
        border_radius=theme.CONTROL_RADIUS,
    )

    def submit() -> None:
        problem = on_ok(field.value or "")
        field.error = problem
        if problem is not None and on_redraw is not None:
            on_redraw()

    field.on_submit = lambda _e: submit()
    return _dialog(
        title,
        field,
        [_cancel(on_cancel), gold_button(ok_label, submit, size=theme.CLEARS_SIZE)],
        on_dismiss=on_cancel,
    )


def _source_button(found: FoundSave, on_open: Callable[[Path], object]) -> ft.Button:
    lines = ft.Column(
        [
            text(found.label, size=theme.NAME_SIZE),
            text(str(found.path), color=theme.MUTED, size=FOUND_PATH_SIZE),
            text(found.logs_text, color=theme.MUTED, size=FOUND_PATH_SIZE),
        ],
        spacing=1,
        tight=True,
        expand=True,
        alignment=ft.MainAxisAlignment.CENTER,
    )
    return menu_choice(lines, lambda: on_open(found.path), height=SOURCE_BUTTON_HEIGHT)


def find_saves_dialog(
    found: Sequence[FoundSave], on_open: Callable[[Path], object], on_cancel: Callback
) -> ft.AlertDialog:
    """One button per save found: label, path and how many adventure logs it holds."""
    body: list[ft.Control] = [_source_button(f, on_open) for f in found]
    if not body:
        body = [_empty(NO_SAVES_TEXT)]
    return _dialog(
        FOUND_TITLE,
        _option_list(body, SOURCE_BUTTON_HEIGHT),
        [_cancel(on_cancel)],
        on_dismiss=on_cancel,
        listing=True,
    )


def searching_dialog(on_cancel: Callback) -> ft.AlertDialog:
    """Shown while the scan runs off the UI thread."""
    row = ft.Row(
        [
            ft.ProgressRing(width=SPINNER_SIZE, height=SPINNER_SIZE, color=theme.GOLD),
            ft.Text(SEARCHING_TEXT, color=theme.TEXT, size=theme.NAME_SIZE),
        ],
        spacing=16,
    )
    return _dialog(FOUND_TITLE, row, [_cancel(on_cancel)], on_dismiss=on_cancel)
