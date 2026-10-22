"""The adventure log frame: parchment ground, engraved bands, menu windows and the pointer."""

from collections.abc import Callable

import flet as ft

from dq7tt_gui import art, theme

LOGO_COMPASS = 50
LOGO_GAP = 10
LOGO_LINE_GAP = 2
LOGO_SMALL_SPACING = 4
LOGO_SPACING = 0.6
APP_NAME_TOP = "DQ7"
APP_NAME = "Tablet Trader"


def ground(content: ft.Control) -> ft.Container:
    """Aged parchment under everything."""
    return ft.Container(
        content=content,
        image=ft.DecorationImage(src=art.PARCHMENT, fit=ft.BoxFit.COVER),
        bgcolor=theme.BG,
        expand=True,
    )


def band(top: bool) -> ft.Container:
    """An engraved border band across the window's top or bottom edge."""
    return ft.Container(
        height=theme.BAND_HEIGHT,
        image=ft.DecorationImage(
            src=art.BAND_TOP if top else art.BAND_BOTTOM,
            fit=ft.BoxFit.FIT_HEIGHT,
            repeat=ft.ImageRepeat.REPEAT_X,
            alignment=ft.Alignment.CENTER_LEFT,
        ),
    )


def menu_window(
    content: ft.Control | None,
    *,
    padding: ft.Padding | int | None = None,
    expand: bool | int = False,
    height: float | None = None,
) -> ft.Container:
    """A menu window: dark, slightly see-through, a thin white rounded edge.

    `expand` is left unset rather than False when not wanted: Flet passes an explicit False
    on to Flutter, which then treats the window like an expanding child and refuses it in a
    wrapping row (a grey error box).

    The dark ring around the white edge is the outer container's border rather than a
    shadow: a shadow is also drawn under the window and would hide the parchment through it.
    """
    inner = ft.Container(
        content=content,
        padding=padding,
        bgcolor=theme.WINDOW_BG,
        border=ft.Border.all(theme.WINDOW_EDGE_W, theme.WINDOW_EDGE),
        border_radius=theme.WINDOW_RADIUS,
        height=height,
        expand=bool(expand) or None,
    )
    return ft.Container(
        content=inner,
        border=ft.Border.all(theme.WINDOW_RING_W, theme.WINDOW_RING),
        border_radius=theme.WINDOW_RADIUS + theme.WINDOW_RING_W,
        shadow=ft.BoxShadow(
            blur_radius=theme.WINDOW_DROP_BLUR,
            color=theme.WINDOW_DROP,
            offset=ft.Offset(0, theme.WINDOW_DROP_Y),
        ),
        expand=expand or None,
    )


def rule(margin: ft.Margin | None = None) -> ft.Container:
    """A hairline inside a window."""
    return ft.Container(height=1, bgcolor=theme.RULE, margin=margin)


def logo() -> ft.Row:
    """The small compass and the app's name, inked on the parchment."""
    return ft.Row(
        [
            ft.Image(src=art.COMPASS, width=LOGO_COMPASS, height=LOGO_COMPASS),
            ft.Column(
                [
                    ft.Text(
                        APP_NAME_TOP,
                        color=theme.INK,
                        size=theme.LOGO_SMALL_SIZE,
                        weight=ft.FontWeight.W_700,
                        font_family=theme.HEADING_FONT,
                        style=ft.TextStyle(letter_spacing=LOGO_SMALL_SPACING),
                    ),
                    ft.Text(
                        APP_NAME,
                        color=theme.INK,
                        size=theme.LOGO_SIZE,
                        weight=ft.FontWeight.W_700,
                        font_family=theme.HEADING_FONT,
                        style=ft.TextStyle(letter_spacing=LOGO_SPACING, height=1.0),
                        no_wrap=True,
                    ),
                ],
                spacing=LOGO_LINE_GAP,
                tight=True,
            ),
        ],
        spacing=LOGO_GAP,
        tight=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def pointer(visible: bool = True) -> ft.Image:
    """The gold pointer that marks where you are, like the game's menu cursor."""
    return ft.Image(src=art.POINTER, width=theme.POINTER_W, height=theme.POINTER_H, visible=visible)


def pointer_slot(shown: bool) -> ft.Container:
    """Room for the pointer, kept whether or not it shows so nothing shifts."""
    return ft.Container(content=pointer(shown), width=theme.POINTER_W)


def point_on_hover(slot: ft.Container) -> Callable[[ft.Event[ft.Container]], None]:
    """A hover handler that shows `slot`'s pointer while the mouse is over its owner."""

    def on_hover(e: ft.Event[ft.Container]) -> None:
        mark = slot.content
        shown = e.data is True or e.data == "true"
        if isinstance(mark, ft.Image) and mark.visible != shown:
            mark.visible = shown
            mark.update()

    return on_hover
