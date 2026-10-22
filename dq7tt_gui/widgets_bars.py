"""The toolbar along the top and the action bar along the bottom, as menu windows."""

from dataclasses import dataclass

import flet as ft

from dq7tt_gui import theme
from dq7tt_gui.viewmodels import ActionBar, ToolbarView
from dq7tt_gui.widgets import (
    BAR_BUTTON_HEIGHT,
    HISTORY_LABEL_MAX_W,
    Callback,
    bar_button,
    danger_button,
    gold_button,
    plain_button,
    text,
    write_button,
)
from dq7tt_gui.widgets_frame import logo, menu_window, pointer

# Bars grow a line when their buttons wrap, so they are sized by padding, not a fixed height.
TOOLBAR_PADDING = ft.Padding(left=8, top=4, right=6, bottom=4)
ACTION_BAR_PADDING = ft.Padding(left=10, top=6, right=8, bottom=6)
BAR_SPACING = 10
TOOLBAR_SPACING = 4
LOGO_GAP = 14
SEPARATOR_H = 28


@dataclass
class ToolbarCallbacks:
    on_open: Callback
    on_find: Callback
    on_undo: Callback
    on_redo: Callback
    on_write: Callback


@dataclass
class ActionCallbacks:
    on_quick_copy: Callback
    on_copy: Callback
    on_move: Callback
    on_reset: Callback
    on_remove: Callback


def _undo_redo_label(verb: str, action: str | None) -> str:
    return verb if action is None else f"{verb}: {action}"


def _wrapping(
    controls: list[ft.Control],
    alignment: ft.MainAxisAlignment = ft.MainAxisAlignment.START,
    spacing: int = BAR_SPACING,
) -> ft.Container:
    """Buttons that take the room left and wrap to a new line rather than be cut off.

    The row that wraps holds no expanding child (Flutter refuses one in a Wrap); the
    container around it is what expands.
    """
    return ft.Container(
        content=ft.Row(
            controls,
            spacing=spacing,
            run_spacing=TOOLBAR_SPACING,
            wrap=True,
            alignment=alignment,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        expand=True,
    )


def separator() -> ft.Container:
    return ft.Container(width=1, height=SEPARATOR_H, bgcolor=theme.RULE)


def toolbar(view: ToolbarView, cbs: ToolbarCallbacks) -> ft.Row:
    """The app's name on the parchment, then a window of commands with Write at its end.

    The commands before Write wrap to a second line when the window is too narrow for them.
    """
    commands = ft.Row(
        [
            _wrapping(
                [
                    plain_button("Open save", cbs.on_open),
                    plain_button("Find saves", cbs.on_find),
                    separator(),
                    plain_button(
                        _undo_redo_label("Undo", view.undo_label),
                        cbs.on_undo,
                        max_text_width=HISTORY_LABEL_MAX_W,
                        disabled=view.undo_label is None,
                        icon=ft.Icons.UNDO,
                    ),
                    plain_button(
                        _undo_redo_label("Redo", view.redo_label),
                        cbs.on_redo,
                        max_text_width=HISTORY_LABEL_MAX_W,
                        disabled=view.redo_label is None,
                    ),
                ],
                spacing=TOOLBAR_SPACING,
            ),
            write_button(view.write_label, cbs.on_write, view.can_write),
        ],
        spacing=BAR_SPACING,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    return ft.Row(
        [logo(), menu_window(commands, padding=TOOLBAR_PADDING, expand=True)],
        spacing=LOGO_GAP,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def action_bar(view: ActionBar, cbs: ActionCallbacks) -> ft.Container:
    """What can be done with the ticked tablets, the pointer by how many there are."""
    lead: list[ft.Control] = []
    controls: list[ft.Control] = []
    if view.selected_count:
        lead = [pointer(), text(view.summary, size=theme.TAB_SIZE)]
        if view.quick_copy_label:
            controls.append(gold_button(view.quick_copy_label, cbs.on_quick_copy))
        controls.append(bar_button("Copy to...", cbs.on_copy))
        if view.can_move:
            controls.append(bar_button("Move to...", cbs.on_move))
        if view.can_reset:
            controls.append(bar_button("Reset clears", cbs.on_reset))
        if view.can_remove:
            controls.append(danger_button("Remove", cbs.on_remove))
    row = ft.Row(
        [*lead, _wrapping(controls, ft.MainAxisAlignment.END)],
        spacing=BAR_SPACING,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    # An empty bar keeps the height of one row of buttons.
    edges = ACTION_BAR_PADDING.top + ACTION_BAR_PADDING.bottom + 2 * theme.WINDOW_EDGE_W
    empty_height = BAR_BUTTON_HEIGHT + edges
    return menu_window(
        row,
        padding=ACTION_BAR_PADDING,
        height=None if view.selected_count else empty_height,
    )
