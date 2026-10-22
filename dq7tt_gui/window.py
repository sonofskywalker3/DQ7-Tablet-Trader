"""The main window: toolbar, two panes (or Save/Bank tabs when narrow), action bar, keys."""

import logging
from collections.abc import Sequence

import flet as ft

from dq7tt.savefile import SlotRole
from dq7tt_gui import art, theme
from dq7tt_gui.model import AppModel
from dq7tt_gui.model_text import DISCARD_TITLE
from dq7tt_gui.viewmodels import (
    Confirm,
    Notice,
    Outcome,
    PaneSide,
    RightMode,
)
from dq7tt_gui.widgets import bar_button, text
from dq7tt_gui.widgets_bars import ActionCallbacks, ToolbarCallbacks, action_bar, toolbar
from dq7tt_gui.widgets_drag import DragPayload, final_position
from dq7tt_gui.widgets_frame import band, ground, menu_window
from dq7tt_gui.widgets_pane import PaneCallbacks, PaneShell
from dq7tt_gui.window_dialogs import TAB_SAVE
from dq7tt_gui.window_narrow import BAR_SPACING, NarrowLayout

log = logging.getLogger(__name__)

APP_TITLE = "DQ7 Tablet Trader"
UNWRITTEN_MARK = " *"
EMPTY_TEXT = "Open a save or find saves on this PC"
CLOSE_TEXT = "You have changes that are not written yet. Close anyway and lose them?"
KEY_UNDO, KEY_REDO, KEY_WRITE, KEY_ALL, KEY_ESCAPE = "Z", "Y", "S", "A", "ESCAPE"
FRAME_TOP = 10
EMPTY_COMPASS = 160
EMPTY_SPACING = 16


class Window(NarrowLayout):
    def __init__(self, page: ft.Page, model: AppModel) -> None:
        self.page = page
        self.model = model
        self.active_side = PaneSide.LEFT
        self.pending_confirm: Confirm | None = None
        self.narrow = self._width() < theme.NARROW_WIDTH
        self.tab_index = TAB_SAVE
        self.picker: ft.FilePicker | None = None
        self._mounted = False
        self._queue: list[Confirm] = []
        self._dialogs: list[ft.AlertDialog] = []
        self._close_question: Confirm | None = None
        self._scan_id = 0
        self._searching: ft.AlertDialog | None = None
        self._top = ft.Container()
        self._body = ft.Container(expand=True)
        self._bottom = ft.Container()
        self._shells = {PaneSide.LEFT: PaneShell(), PaneSide.RIGHT: PaneShell()}
        self._panes = ft.Row(spacing=theme.PANE_GAP)
        self._wide = ft.Container(content=self._panes, expand=True)
        self._layout = ft.Column(
            [self._top, self._body, self._bottom],
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self._frame = ft.Container(content=self._layout, expand=True)
        self._build_tabs()

    # Building

    def build(self) -> ft.Control:
        """Parchment with an engraved band along the top and bottom, the windows between."""
        self._fill()
        return ground(
            ft.Column(
                [band(top=True), self._frame, band(top=False)],
                spacing=0,
                expand=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            )
        )

    def _width(self) -> float:
        """The page width; Flet reports none until the first resize event."""
        return self.page.width or theme.WINDOW_W

    def install(self) -> None:
        """Hook the window to its page: title, keys, resizing, close."""
        self.page.on_keyboard_event = self.on_key
        self.page.on_resize = self.on_resize
        self.page.window.prevent_close = True
        self.page.window.on_event = self.on_window_event
        self.narrow = self._width() < theme.NARROW_WIDTH
        self.page.add(self.build())
        self._mounted = True
        self.refresh()

    def refresh(self) -> None:
        """Rebuild toolbar, panes and action bar from the model."""
        self._fill()
        suffix = UNWRITTEN_MARK if self.model.has_unwritten() else ""
        self.page.title = APP_TITLE + suffix
        if self._mounted:
            self.page.update()

    def apply_width(self, width: float) -> None:
        narrow = width < theme.NARROW_WIDTH
        if narrow != self.narrow:
            self.narrow = narrow
            self.refresh()

    def on_resize(self, e: ft.PageResizeEvent) -> None:
        self.apply_width(e.width)

    def _fill(self) -> None:
        tb = self.model.toolbar()
        margin = theme.FRAME_MARGIN_NARROW if self.narrow else theme.FRAME_MARGIN
        self._frame.padding = ft.Padding(left=margin, top=FRAME_TOP, right=margin, bottom=FRAME_TOP)
        self._layout.spacing = theme.FRAME_GAP_NARROW if self.narrow else theme.FRAME_GAP
        if self.narrow:
            self._top.content = self._narrow_top(tb.undo_label is not None)
            self._show_layout(self._tabs())
            self._bottom.content = self._narrow_bar()
            return
        self._top.content = toolbar(tb, self._toolbar_callbacks())
        self._panes.controls = [self._pane(PaneSide.LEFT), self._pane(PaneSide.RIGHT)]
        self._show_layout(self._wide)
        self._bottom.content = action_bar(self.model.action_bar(), self._action_callbacks())

    def _show_layout(self, layout: ft.Control) -> None:
        """Put `layout` in the body. Left as is on later redraws so the lists keep their scroll.

        Moving the panes under a different parent remounts their lists at the top, so their
        trackers start over; the list controls themselves are kept.
        """
        if self._body.content is layout:
            return
        self._body.content = layout
        for shell in self._shells.values():
            shell.scroll.pixels = 0.0

    def _pane(self, side: PaneSide) -> ft.Control:
        view = self.model.left() if side is PaneSide.LEFT else self.model.right()
        if side is PaneSide.LEFT and view.empty_text is not None:
            self._shells[side].reset()
            return self._empty_state()
        mode = self.model.right_mode()
        return self._shells[side].update(view, self._pane_callbacks(side), mode, self.narrow)

    def _empty_state(self) -> ft.Control:
        buttons = ft.Row(
            [bar_button("Open save", self.open_dialog), bar_button("Find saves", self.find_saves)],
            alignment=ft.MainAxisAlignment.CENTER,
            wrap=True,
            spacing=BAR_SPACING,
            run_spacing=BAR_SPACING,
        )
        return menu_window(
            ft.Column(
                [
                    ft.Image(src=art.COMPASS_FAINT, width=EMPTY_COMPASS, height=EMPTY_COMPASS),
                    text(EMPTY_TEXT, color=theme.MUTED, size=theme.TITLE_SIZE),
                    buttons,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=EMPTY_SPACING,
            ),
            expand=True,
        )

    # Callback bundles

    def _toolbar_callbacks(self) -> ToolbarCallbacks:
        return ToolbarCallbacks(
            on_open=self.open_dialog,
            on_find=self.find_saves,
            on_undo=self.undo,
            on_redo=self.redo,
            on_write=self.write_all,
        )

    def _action_callbacks(self) -> ActionCallbacks:
        return ActionCallbacks(
            on_quick_copy=lambda: self.handle(self.model.quick_copy()),
            on_copy=lambda: self.pick_destination(move=False),
            on_move=lambda: self.pick_destination(move=True),
            on_reset=lambda: self.handle(self.model.reset_selected()),
            on_remove=lambda: self.handle(self.model.remove_selected()),
        )

    def _pane_callbacks(self, side: PaneSide) -> PaneCallbacks:
        left = side is PaneSide.LEFT
        return PaneCallbacks(
            on_pick_log=lambda role: self._pick_log(side, role),
            on_pick_folder=lambda name: self.handle(self.model.pick_folder(name)),
            on_toggle=self.toggle,
            on_close=lambda: self.handle(
                self.model.close_left() if left else self.model.close_right()
            ),
            on_mode=self._on_mode,
            on_new_folder=self.new_folder,
            on_reorder=lambda old, new: self.handle(self.model.reorder(side, old, new)),
            on_drop=lambda payload, gap: self._drop(payload, side, gap),
            on_bank_all=lambda: self.handle(self.model.import_all_to_bank(side)),
            on_put_into_azahar=lambda: self.handle(self.model.put_into_azahar(side)),
        )

    def _drop(self, payload: DragPayload, dest: PaneSide, gap: int) -> None:
        index = final_position(payload, dest, gap)
        self.handle(self.model.drop(payload.side, payload.indexes, dest, index))

    # Commands

    def handle(self, outcome: Outcome) -> None:
        """Show what a command returned (notices or a question), then redraw."""
        if isinstance(outcome, Confirm):
            self.show_confirm(outcome)
        else:
            self.show_notices(outcome)
        self.refresh()

    def toggle(self, key: str) -> None:
        side, _, index = key.partition(":")
        self.active_side = PaneSide(side)
        self.handle(self.model.toggle_row(self.active_side, int(index)))

    def undo(self) -> None:
        self.handle(self.model.undo())

    def redo(self) -> None:
        self.handle(self.model.redo())

    def write_all(self) -> None:
        self._write(self.model.dirty_sides())

    def _write(self, sides: Sequence[PaneSide]) -> None:
        notices: list[Notice] = []
        asks: list[Confirm] = []
        for side in sides:
            result = self.model.write(side)
            if isinstance(result, Confirm):
                asks.append(result)
            else:
                notices.extend(result)
        self.show_notices(notices)
        for ask in asks:
            self.show_confirm(ask)
        self.refresh()

    def _pick_log(self, side: PaneSide, role: SlotRole) -> None:
        self.active_side = side
        self.handle(self.model.pick_log(side, role))

    def _on_mode(self, mode: RightMode) -> None:
        if mode is RightMode.BANK:
            self.handle(self.model.show_bank())
            return
        chips = [c for c in self.model.right().log_chips if not c.muted]
        if chips:
            self._pick_log(PaneSide.RIGHT, chips[0].role)
        else:
            self.open_dialog(PaneSide.RIGHT)

    # Keyboard and closing

    def on_key(self, e: ft.KeyboardEvent) -> None:
        if self._dialogs:
            return
        key = e.key.upper()
        if key == KEY_ESCAPE:
            self.handle(self.model.clear_selection())
        elif not e.ctrl:
            return
        elif key == KEY_UNDO and not e.shift:
            self.undo()
        elif key == KEY_REDO or (key == KEY_UNDO and e.shift):
            self.redo()
        elif key == KEY_ALL:
            self.handle(self.model.select_all(self.active_side))
        elif key == KEY_WRITE and self.model.dirty_sides():
            self.write_all()  # the same as the Write button

    async def on_window_event(self, e: ft.WindowEvent) -> None:
        if e.type is not ft.WindowEventType.CLOSE:
            return
        if not self.model.has_unwritten():
            self.destroy_window()
            return
        if self._close_question is not None:
            return  # the question is already on screen or waiting its turn
        self._close_question = Confirm(
            DISCARD_TITLE, CLOSE_TEXT, "Discard", on_ok=self._close_window
        )
        self.show_confirm(self._close_question)

    def destroy_window(self) -> None:
        self.page.run_task(self.page.window.destroy)

    def _close_window(self) -> list[Notice]:
        self.destroy_window()
        return []
