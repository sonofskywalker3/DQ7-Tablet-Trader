"""Controls the handheld's D-pad can reach.

Flutter moves the focus with the D-pad and presses the focused control with A; a Flet
`Container` can be clicked but tells Python nothing about focus. So on Android each row,
chip and strip button carries a `CupertinoButton`: it takes the focus, answers A, and
reports focus and blur. It has no minimum size and no fill of its own, so what it wraps
looks the same as before. Buttons show a gold ring while focused; rows show the pointer.

The ring is drawn here rather than left to Flutter: Flutter shows a focus ring only once
it believes a hardware keyboard is in use, and keys injected or sent by a virtual device
never switch it over, while the focus itself still moves.

The button sets Cupertino's text style for what it holds, so words inside one name the
page's own font and spacing (`BODY_SPACING`) rather than inheriting them.
"""

from collections.abc import Callable

import flet as ft

from dq7tt_gui import theme

Callback = Callable[[], object]
NO_MIN_SIZE = ft.Size(0, 0)
# How far a pressed control fades: the touch feedback in place of the ink ripple.
PRESSED_OPACITY = 0.55
FOCUS_RING_W = 3
# A row's focus control: a sliver at its left edge. Flet's CupertinoButton always claims a
# long press, so it is kept narrow and the long press that reorders lands on the list.
LEAD_FOCUS_W = 2
# Material 3's body text spacing, which words outside a button inherit from the page.
BODY_SPACING = 0.25

# Told True when the control takes the focus and False when it loses it.
type FocusChange = Callable[[bool], object]


def focus_button(
    content: ft.Control,
    on_click: Callback | None,
    *,
    data: object = None,
    on_focus: FocusChange | None = None,
    autofocus: bool = False,
    width: float | None = None,
    height: float | None = None,
    radius: float = theme.CONTROL_RADIUS,
) -> ft.CupertinoButton:
    """`content` made focusable; A (or a tap) runs `on_click`. None: shown, not usable."""

    def changed(focused: bool) -> Callable[[ft.Event[ft.CupertinoButton]], None]:
        def handler(_e: ft.Event[ft.CupertinoButton]) -> None:
            if on_focus is not None:
                on_focus(focused)

        return handler

    return ft.CupertinoButton(
        content=content,
        on_click=None if on_click is None else (lambda _e: on_click()),
        disabled=on_click is None,
        data=data,
        min_size=NO_MIN_SIZE,
        padding=0,
        border_radius=radius,
        focus_color=theme.CLEAR,  # see `focus_ring`
        opacity_on_click=PRESSED_OPACITY,
        autofocus=autofocus,
        on_focus=changed(True) if on_focus is not None else None,
        on_blur=changed(False) if on_focus is not None else None,
        width=width,
        height=height,
    )


def focus_ring(target: ft.Container) -> FocusChange:
    """Draw a ring just inside `target`'s edge while it has the focus.

    Laid over the control (a foreground decoration), so nothing moves when it comes and
    goes. Gold, or the page's light text colour on a control that is gold already (the
    active log chip, Copy to bank, Save).
    """
    edge = target.border.top.color if isinstance(target.border, ft.Border) else None
    gilded = target.bgcolor == theme.ACCENT or edge in (theme.GOLD, theme.ACCENT_EDGE)
    color = theme.TEXT if gilded else theme.GOLD

    def changed(focused: bool) -> None:
        target.foreground_decoration = (
            ft.BoxDecoration(
                border=ft.Border.all(FOCUS_RING_W, color), border_radius=target.border_radius
            )
            if focused
            else None
        )
        target.update()

    return changed


def _parts(control: ft.Control) -> list[ft.Control]:
    content = getattr(control, "content", None)
    parts = [content] if isinstance(content, ft.Control) else []
    return parts + list(getattr(control, "controls", None) or [])


def keep_page_text(control: ft.Control) -> ft.Control:
    """Name the page's font and spacing on words that would take them from the page, so
    they look the same inside a `focus_button`. Returns `control`."""
    if isinstance(control, ft.Text) and control.font_family is None:
        control.font_family = theme.BODY_FONT
        if control.style is None:
            control.style = ft.TextStyle(letter_spacing=BODY_SPACING)
        elif control.style.letter_spacing is None:
            control.style.letter_spacing = BODY_SPACING
    for part in _parts(control):
        keep_page_text(part)
    return control


def first_focus(control: ft.Control) -> ft.CupertinoButton | None:
    """The first focusable control in `control`, depth first."""
    if isinstance(control, ft.CupertinoButton):
        return control
    for part in _parts(control):
        found = first_focus(part)
        if found is not None:
            return found
    return None
