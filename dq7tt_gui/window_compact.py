"""The compact layout, for short screens such as the AYN Thor's top screen.

The save and the bank stay side by side. One slim strip along the top holds the save's log
chips (over the save) and the bank's folder picker, Undo and Save (over the bank); one
along the bottom holds what can be done with the ticked tablets. No engraved bands, no logo.
"""

from collections.abc import Callable
from functools import partial

import flet as ft

from dq7tt.savefile import SlotRole
from dq7tt_gui import theme
from dq7tt_gui.layout import fit_right_column, roomy
from dq7tt_gui.model import AppModel
from dq7tt_gui.viewmodels import LogChip, PaneSide, RightMode
from dq7tt_gui.widgets import text
from dq7tt_gui.widgets_frame import pointer
from dq7tt_gui.widgets_strip import (
    CHIP,
    CHIP_ON,
    DANGER,
    DISABLED,
    GOLD,
    OUTLINE,
    PLAIN,
    WRITE,
    Look,
    caption,
    columns,
    group,
    key_cap,
    strip,
    strip_button,
)
from dq7tt_gui.window_dialogs import (
    CLOSE_SAVE,
    COPY_ANY,
    MORE,
    NOTHING_ELSE,
    short_copy,
)
from dq7tt_gui.window_open import OpenFlows

KEY_MARKS: dict[PaneSide, str] = {PaneSide.LEFT: "L", PaneSide.RIGHT: "R"}
QUICK_SHORT = "Quick"
UNDO_WORD = "Undo"
START_KEY = "Start"
SELECTED_FORMAT = "{count} selected"
NEW_FOLDER = "New folder"
OPEN_SECOND = "Open a second save"
SHOW_SECOND = "Show the second save"
SHOW_BANK = "Show the bank"
BANK_MENU = "Bank"
SECOND_MENU = "Second save"
HINTS = (("A", "tick"), ("B", "back"))

COUNT_GAP = 6
HINT_GAP = 4
BAR_GAP = 8


def chip_count(chip: LogChip) -> str:
    """How many tablets a log holds: the first half of its "23/24"."""
    return chip.fill.split("/", 1)[0]


class CompactLayout(OpenFlows):
    """Mixed into `Window`; relies on its model, panes and commands."""

    model: AppModel
    active_side: PaneSide
    touch: bool

    def shown_width(self) -> float:
        raise NotImplementedError

    def undo(self) -> None:
        raise NotImplementedError

    def write_all(self) -> None:
        raise NotImplementedError

    def _pick_log(self, side: PaneSide, role: SlotRole) -> None:
        raise NotImplementedError

    def _on_mode(self, mode: RightMode) -> None:
        raise NotImplementedError

    # The top strip

    def _compact_top(self) -> ft.Control:
        wide = roomy(self.shown_width())
        left = self.model.left()
        chips: list[ft.Control] = [self._log_chip(c, wide) for c in left.log_chips]
        label, count = self._picker_words(wide)
        fit = fit_right_column(
            self.shown_width(),
            save_label=self.strip_write_label(),
            undo_word=wide,
            folder=label,
            count=count,
            start_key=wide and self.touch,
        )
        right = ft.Row(
            [
                self._folder_picker(label, count, fit.label_width),
                group([self._undo_button(fit.undo_word), self._save_button(fit.start_key)]),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return strip(columns(group(chips), right))

    def strip_write_label(self) -> str:
        """The Save (or Write) words the strip has room for."""
        tb = self.model.toolbar()
        return tb.short_label or tb.write_label

    def _undo_button(self, word: bool) -> ft.Container:
        """Undo: the arrow, with its word when there is room; dim with nothing to undo."""
        can_undo = self.model.toolbar().undo_label is not None
        return strip_button(
            caption(
                UNDO_WORD if word else None, PLAIN if can_undo else DISABLED, icon=ft.Icons.UNDO
            ),
            self.undo if can_undo else None,
            PLAIN,
            data="undo",
            icon_only=not word,
            tooltip=None if word else UNDO_WORD,
            focusable=self.touch,
        )

    def _save_button(self, start_key: bool) -> ft.Container:
        """Save (or Write): gold and glowing while there is something to write."""
        tb = self.model.toolbar()
        look = WRITE if tb.can_write else DISABLED
        return strip_button(
            caption(self.strip_write_label(), look, cap=START_KEY if start_key else None),
            self.write_all if tb.can_write else None,
            look,
            data="write",
            focusable=self.touch,
        )

    def _log_chip(self, chip: LogChip, wide: bool) -> ft.Container:
        look = CHIP_ON if chip.active else CHIP
        short = chip.role is SlotRole.QUICK_SAVE and not wide
        label = QUICK_SHORT if short else chip.label
        return strip_button(
            caption(label, look, extra=chip_count(chip) if wide and chip.fill else None),
            lambda: self._pick_log(PaneSide.LEFT, chip.role),
            look,
            data=chip.role,
            focusable=self.touch,
        )

    def _picker_words(self, wide: bool) -> tuple[str, str | None]:
        """What the picker says: the bank folder (and, with room, its count; the pane's
        header has it too), or the log of a second save."""
        view = self.model.right()
        if self.model.right_mode() is RightMode.BANK:
            folder = next((c for c in view.folder_chips if c.active), None)
            if folder is None:
                return view.title, None
            return folder.label, str(folder.count) if wide else None
        chip = next((c for c in view.log_chips if c.active), None)
        return (view.title if chip is None else chip.label), None

    def _folder_picker(
        self, label: str, count: str | None, label_width: float | None
    ) -> ft.Container:
        """What the right pane shows; tapping it offers the folders (or logs).

        No folder icon (the mockup's 853 frame had one): there is not room for it beside a
        real folder name at the Thor's 832 dp. A long name is held to `label_width`.
        """
        return strip_button(
            caption(
                label, OUTLINE, extra=count, after_icon=ft.Icons.EXPAND_MORE, width=label_width
            ),
            self.right_menu,
            OUTLINE,
            data="picker",
            focusable=self.touch,
        )

    def right_menu(self) -> None:
        """The bank's folders (or the second save's logs), and switching between the two."""
        view = self.model.right()
        options: list[tuple[str, Callable[[], object]]] = []
        if self.model.right_mode() is RightMode.BANK:
            for folder in view.folder_chips:
                pick = partial(self.model.pick_folder, folder.name)
                options.append((f"{folder.label} ({folder.count})", pick))
            options.append((NEW_FOLDER, self.new_folder))
            second = SHOW_SECOND if self.model.has_save(PaneSide.RIGHT) else OPEN_SECOND
            options.append((second, partial(self._on_mode, RightMode.SAVE)))
            self._choose(BANK_MENU, options, NOTHING_ELSE)
            return
        for chip in view.log_chips:
            pick = partial(self._pick_log, PaneSide.RIGHT, chip.role)
            options.append((f"{chip.label} ({chip.detail})", pick))
        options.append((SHOW_BANK, partial(self._on_mode, RightMode.BANK)))
        options.append((CLOSE_SAVE, self.model.close_right))
        self._choose(SECOND_MENU, options, NOTHING_ELSE)

    # The bottom strip

    def _compact_bottom(self) -> ft.Control:
        bar = self.model.action_bar()
        lead: list[ft.Control] = []
        if bar.selected_count:
            count = SELECTED_FORMAT.format(count=bar.selected_count)
            lead += [pointer(), text(count, size=theme.CLEARS_SIZE)]
        if self.touch and roomy(self.shown_width()):
            lead.append(self._hints())
        buttons: list[ft.Control] = []
        if bar.selected_count:
            if bar.quick_copy_label:
                label = short_copy(bar.quick_copy_label)
                copy = self._bar_button(label, self.quick_copy, GOLD, "copy")
            else:
                copy = self._bar_button(COPY_ANY, self.send_to, GOLD, "copy")
            buttons.append(copy)
            if bar.can_move:
                move = partial(self.pick_destination, move=True)
                buttons.append(self._bar_button("Move", move, OUTLINE, "move"))
            remove = self.remove_selected
            buttons.append(self._bar_button("Remove", remove, DANGER, "remove"))
        buttons.append(self._bar_button(MORE, self.compact_more, PLAIN, "more"))
        return strip(
            ft.Row(
                [
                    ft.Container(
                        content=ft.Row(
                            lead,
                            spacing=COUNT_GAP,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        expand=True,
                    ),
                    group(buttons, end=True),
                ],
                spacing=BAR_GAP,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

    def _bar_button(
        self, label: str, on_click: Callable[[], object], look: Look, data: str
    ) -> ft.Control:
        return strip_button(caption(label, look), on_click, look, data=data, focusable=self.touch)

    @staticmethod
    def _hints() -> ft.Row:
        """Which controller keys tick and go back, after the count."""
        parts: list[ft.Control] = []
        for key, word in HINTS:
            parts += [key_cap(key), text(word, color=theme.DIM, size=theme.DETAIL_SIZE)]
        return ft.Row(
            parts, spacing=HINT_GAP, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER
        )

    def quick_copy(self) -> None:
        self.handle(self.model.quick_copy())

    def remove_selected(self) -> None:
        self.handle(self.model.remove_selected())

    def compact_more(self, full: bool = False) -> None:
        """Everything that has no room in the strips, for the pane with the focus.

        `full` (the short tabs, whose bottom strip has only Send) adds the quick copy, Move
        and Remove that the compact layout's strip shows itself.
        """
        options = self.more_options(self.active_side, strip_actions=full, slim=True)
        self._choose(MORE, options, NOTHING_ELSE)
