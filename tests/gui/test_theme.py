"""Text stays readable: every text colour against what it is drawn on, by WCAG contrast."""

import pytest

from dq7tt_gui import theme

MIN_CONTRAST = 4.5
GROUNDS = (theme.PARCHMENT_LIGHT, theme.PARCHMENT_DARK)

RGB = tuple[float, float, float]


def colour(value: str) -> tuple[RGB, float]:
    """A theme colour as 0..1 channels and an opacity ("#rrggbb" or "#rrggbb,0.9")."""
    hex_part, _, opacity = value.partition(",")
    digits = hex_part.lstrip("#")
    rgb = (int(digits[0:2], 16) / 255, int(digits[2:4], 16) / 255, int(digits[4:6], 16) / 255)
    return rgb, float(opacity) if opacity else 1.0


def over(top: str, bottom: RGB) -> RGB:
    rgb, alpha = colour(top)
    r, g, b = (t * alpha + u * (1 - alpha) for t, u in zip(rgb, bottom, strict=True))
    return (r, g, b)


def luminance(rgb: RGB) -> float:
    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(text: str, ground: RGB) -> float:
    lighter, darker = sorted((luminance(over(text, ground)), luminance(ground)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def layered(*layers: str) -> list[RGB]:
    """What `layers` (bottom first) look like over the lightest and darkest parchment."""
    found = []
    for ground in GROUNDS:
        rgb = colour(ground)[0]
        for layer in layers:
            rgb = over(layer, rgb)
        found.append(rgb)
    return found


IN_WINDOWS = [
    theme.TEXT,
    theme.MUTED,
    theme.TITLES,
    theme.DIM,
    theme.TAB_OFF,
    theme.GOLD_TEXT,
    theme.DANGER_TEXT,
    *theme.KIND_COLORS.values(),
]

CASES: list[tuple[str, str, list[RGB]]] = [
    *[(f"{c} in a window", c, layered(theme.WINDOW_BG)) for c in IN_WINDOWS],
    *[(f"{c} in a dialog", c, layered(theme.DIALOG_BG)) for c in IN_WINDOWS],
    *[
        (f"{c} on a ticked row", c, layered(theme.WINDOW_BG, theme.SELECTED_BG))
        for c in (theme.SELECTED_TEXT, theme.TEXT, *theme.KIND_COLORS.values())
    ],
    *[
        (f"{c} on the active chip", c, layered(theme.WINDOW_BG, theme.GOLD_WASH))
        for c in (theme.GOLD_TEXT, theme.MUTED)
    ],
    *[
        (f"{c} under the mouse", c, layered(theme.DIALOG_BG, theme.HOVER))
        for c in (theme.TEXT, theme.MUTED)
    ],
    ("red on Remove", theme.DANGER_TEXT, layered(theme.WINDOW_BG, theme.DANGER_BG)),
    ("an error notice", theme.DANGER_TEXT, layered(theme.ERROR_WINDOW)),
    ("Write changes", theme.ACCENT_TEXT, layered(theme.ACCENT)),
    ("the app's name on parchment", theme.INK, layered()),
]


@pytest.mark.parametrize(("what", "text", "grounds"), CASES, ids=[c[0] for c in CASES])
def test_text_contrast_is_at_least_four_and_a_half_to_one(
    what: str, text: str, grounds: list[RGB]
) -> None:
    for ground in grounds:
        assert contrast(text, ground) >= MIN_CONTRAST, what


def test_contrast_maths_matches_the_wcag_extremes() -> None:
    assert contrast("#000000", colour("#ffffff")[0]) == pytest.approx(21.0)
    assert contrast("#777777", colour("#777777")[0]) == pytest.approx(1.0)
