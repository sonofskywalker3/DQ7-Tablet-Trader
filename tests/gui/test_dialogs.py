from pathlib import Path

import flet as ft
from test_widgets import button_labels, buttons, label, noop, texts, walk

from dq7tt_gui import art, dialogs, theme
from dq7tt_gui.dialogs import (
    LIST_MAX_HEIGHT,
    NO_SAVES_TEXT,
    SEARCHING_TEXT,
    confirm_dialog,
    destination_dialog,
    find_saves_dialog,
    open_choice_dialog,
    searching_dialog,
    snack,
    text_prompt,
)
from dq7tt_gui.viewmodels import Confirm, Destination, FoundSave, Notice, NoticeKind


def content(dialog: ft.AlertDialog) -> ft.Control:
    assert dialog.content is not None
    return dialog.content


def title_of(dialog: ft.AlertDialog) -> str:
    assert isinstance(dialog.title, ft.Text)
    return str(dialog.title.value)


def test_confirm_dialog_shows_question_notices_and_labels() -> None:
    ask = Confirm(
        "Put into Azahar?",
        "Close Azahar first.",
        "Put it in",
        notices=(Notice(NoticeKind.INFO, "Wrote the edited save."),),
    )
    dialog = confirm_dialog(ask, noop, noop)
    assert title_of(dialog) == "Put into Azahar?"
    assert texts(content(dialog)) == ["Close Azahar first.", "Wrote the edited save."]
    assert [label(b) for b in dialog.actions] == ["Cancel", "Put it in"]  # type: ignore[arg-type]
    assert dialog.modal is True


def test_confirm_and_choice_dialogs_route_dismiss_to_cancel() -> None:
    calls: list[str] = []
    dialog = confirm_dialog(Confirm("t", "x", "OK"), noop, lambda: calls.append("cancel"))
    assert dialog.on_dismiss is not None
    dialog.on_dismiss(None)
    assert calls == ["cancel"]
    picker = destination_dialog([], lambda d: None, lambda: calls.append("gone"))
    assert picker.on_dismiss is not None
    picker.on_dismiss(None)
    assert calls == ["cancel", "gone"]


def dests() -> list[Destination]:
    return [
        Destination("Copy to Bank folder Maps", "bank", "Maps"),
        Destination("Log 2", "log", object()),
        Destination("Log 3", "log", object()),
        Destination("Unsorted", "bank", ""),
    ]


def test_destination_dialog_lists_logs_first_then_bank_folders() -> None:
    picked: list[Destination] = []
    given = dests()
    dialog = destination_dialog(given, picked.append, noop, title="Move to...")
    assert title_of(dialog) == "Move to..."
    assert button_labels(content(dialog)) == [
        "Log 2",
        "Log 3",
        "Copy to Bank folder Maps",
        "Unsorted",
    ]
    buttons(content(dialog))[2].on_click(None)  # type: ignore[misc]
    assert picked == [given[0]]


def test_destination_dialog_empty_says_so() -> None:
    dialog = destination_dialog([], lambda d: None, noop)
    assert "nowhere" in " ".join(texts(content(dialog)))
    assert button_labels(content(dialog)) == []


def test_text_prompt_passes_the_typed_name() -> None:
    names: list[str] = []
    dialog = text_prompt("New bank folder", "Folder name", "Create", names.append, noop)
    assert title_of(dialog) == "New bank folder"
    field = content(dialog)
    while not isinstance(field, ft.TextField):
        field = field.content  # type: ignore[attr-defined]
    assert field.label == "Folder name"
    field.value = "Maps"
    next(a for a in dialog.actions if "Create" in label(a)).on_click(None)  # type: ignore[arg-type, union-attr, misc]
    assert names == ["Maps"]


def test_find_saves_dialog_shows_label_path_and_logs_per_source() -> None:
    found = [
        FoundSave("Checkpoint backup A (US)", Path("C:/sd/a"), "3 adventure logs"),
        FoundSave("Azahar save (US)", Path("C:/sd/b"), "1 adventure log"),
    ]
    opened: list[Path] = []
    dialog = find_saves_dialog(found, opened.append, noop)
    shown = texts(content(dialog))
    assert "Checkpoint backup A (US)" in shown and "3 adventure logs" in shown
    assert str(Path("C:/sd/b")) in shown
    buttons(content(dialog))[1].on_click(None)  # type: ignore[misc]
    assert opened == [Path("C:/sd/b")]


def test_find_saves_dialog_empty_text() -> None:
    dialog = find_saves_dialog([], lambda p: None, noop)
    assert texts(content(dialog)) == [NO_SAVES_TEXT]
    assert NO_SAVES_TEXT == (
        "No Dragon Quest VII saves found. Plug in your 3DS SD card or open a save folder yourself."
    )


def test_searching_dialog_shows_progress_and_cancel() -> None:
    dialog = searching_dialog(noop)
    assert SEARCHING_TEXT == "Looking for saves..."
    assert SEARCHING_TEXT in texts(content(dialog))
    assert any(isinstance(c, ft.ProgressRing) for c in _all(content(dialog)))
    assert [label(b) for b in dialog.actions] == ["Cancel"]  # type: ignore[arg-type]


def _all(control: ft.Control) -> list[ft.Control]:
    from test_widgets import walk

    return list(walk(control))


def test_open_choice_offers_folder_and_file_or_zip() -> None:
    calls: list[str] = []
    dialog = open_choice_dialog(lambda: calls.append("folder"), lambda: calls.append("file"), noop)
    assert button_labels(content(dialog)) == ["Open folder", "Open file or zip"]
    for b in buttons(content(dialog)):
        b.on_click(None)  # type: ignore[misc]
    assert calls == ["folder", "file"]


def scrolling_columns(control: ft.Control) -> list[ft.Column]:
    return [c for c in walk(control) if isinstance(c, ft.Column) and c.scroll is not None]


def test_short_option_lists_fit_their_content() -> None:
    dests = [Destination(f"Log {i}", "log", None) for i in range(3)]
    for dialog in (
        destination_dialog(dests, lambda d: None, noop),
        open_choice_dialog(noop, noop, noop),
        find_saves_dialog([FoundSave("SD", Path("x"), "3 logs")], lambda p: None, noop),
    ):
        body = content(dialog)
        assert scrolling_columns(body) == []
        assert all(c.height is None for c in walk(body) if isinstance(c, ft.Container))


def test_long_option_list_scrolls_within_a_set_height() -> None:
    dests = [Destination(f"Folder {i}", "bank", str(i)) for i in range(30)]
    body = content(destination_dialog(dests, lambda d: None, noop))
    assert len(scrolling_columns(body)) == 1
    assert any(getattr(c, "height", None) == LIST_MAX_HEIGHT for c in walk(body))


def test_destination_buttons_start_with_a_capital() -> None:
    given = [Destination("Log 2", "log", None), Destination("bank folder Unsorted", "bank", "")]
    labels = button_labels(content(destination_dialog(given, lambda d: None, noop)))
    assert labels == ["Log 2", "Bank folder Unsorted"]


def every_dialog() -> list[ft.AlertDialog]:
    return [
        confirm_dialog(Confirm("Remove?", "Sure?", "Remove"), noop, noop),
        destination_dialog(dests(), lambda d: None, noop),
        open_choice_dialog(noop, noop, noop),
        find_saves_dialog([FoundSave("SD", Path("x"), "3 logs")], lambda p: None, noop),
        searching_dialog(noop),
        text_prompt("New bank folder", "Folder name", "Create", lambda n: None, noop),
    ]


def test_every_dialog_is_a_menu_window() -> None:
    for dialog in every_dialog():
        assert dialog.bgcolor == theme.DIALOG_BG
        assert isinstance(dialog.shape, ft.RoundedRectangleBorder)
        assert dialog.shape.side.color == theme.WINDOW_EDGE  # type: ignore[union-attr]
        assert dialog.barrier_color == theme.BARRIER


def test_full_logs_are_dimmed_and_say_so() -> None:
    given = [
        Destination("Log 1", "log", None, detail="Auster, 135h, 24/24, full", full=True),
        Destination("Quick save", "log", None, detail="Auster, 10h, 6/24"),
    ]
    choices = buttons(content(destination_dialog(given, lambda d: None, noop)))
    assert [texts(b) for b in choices] == [
        ["Log 1", "Auster, 135h, 24/24, full"],
        ["Quick save", "Auster, 10h, 6/24"],
    ]
    full_name = next(c for c in walk(choices[0]) if isinstance(c, ft.Text))
    open_name = next(c for c in walk(choices[1]) if isinstance(c, ft.Text))
    assert full_name.color == theme.DIM and open_name.color == theme.TEXT


def test_menu_choices_show_the_pointer_while_the_mouse_is_on_them(monkeypatch) -> None:
    choice = buttons(content(open_choice_dialog(noop, noop, noop)))[0]
    (mark,) = [c for c in walk(choice) if isinstance(c, ft.Image)]
    monkeypatch.setattr(mark, "update", noop)
    assert mark.src == art.POINTER and not mark.visible
    choice.on_hover(ft.Event(name="hover", control=choice, data=True))  # type: ignore[misc, arg-type]
    assert mark.visible
    choice.on_hover(ft.Event(name="hover", control=choice, data=False))  # type: ignore[misc, arg-type]
    assert not mark.visible


def test_the_choice_that_goes_ahead_is_gold() -> None:
    dialog = confirm_dialog(Confirm("Remove?", "Sure?", "Remove"), noop, noop)
    ok = action_button(dialog, "Remove")
    assert ok.style.side.color == theme.GOLD  # type: ignore[union-attr]


def action_button(dialog: ft.AlertDialog, word: str) -> ft.Button:
    return next(b for b in dialog.actions if isinstance(b, ft.Button) and word in label(b))


def test_notices_float_in_a_small_window() -> None:
    bar = snack(Notice(NoticeKind.INFO, "Done."))
    assert bar.behavior == ft.SnackBarBehavior.FLOATING
    assert bar.bgcolor == theme.DIALOG_BG
    assert bar.shape.side.color == theme.WINDOW_EDGE  # type: ignore[union-attr]
    error = snack(Notice(NoticeKind.ERROR, "No."))
    assert error.shape.side.color == theme.DANGER_BORDER  # type: ignore[union-attr]


def test_long_choice_list_scrolls_at_the_height_given() -> None:
    options = [(f"Option {i}", lambda: None) for i in range(5)]
    tall = dialogs.choice_dialog("Pick", options, lambda: None)
    assert not isinstance(tall.content.content, ft.Container)  # type: ignore[union-attr]
    short = dialogs.choice_dialog("Pick", options, lambda: None, max_height=120)
    body = short.content.content  # type: ignore[union-attr]
    assert isinstance(body, ft.Container) and body.height == 120
    assert body.content.scroll == ft.ScrollMode.AUTO  # type: ignore[union-attr]
