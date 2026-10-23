"""Which layout the window takes for the size it is given; no window code here.

WIDE: the desktop window, panes side by side under the engraved bands.
COMPACT: short or not-so-wide screens such as the AYN Thor's top screen; the panes stay
side by side between two slim strips, and the bands and the logo go.
TABS: narrow screens (phones, the Thor's bottom screen); one pane at a time.
"""

from dataclasses import dataclass
from enum import StrEnum

COMPACT_MIN_WIDTH = 600
NARROW_WIDTH = 900
SHORT_HEIGHT = 520
# From this width the compact strips have room for the log counts and the word Undo.
ROOMY_WIDTH = 760


class Layout(StrEnum):
    WIDE = "wide"
    COMPACT = "compact"
    TABS = "tabs"


def choose_layout(width: float, height: float) -> Layout:
    if width < COMPACT_MIN_WIDTH:
        return Layout.TABS
    if width < NARROW_WIDTH or height < SHORT_HEIGHT:
        return Layout.COMPACT
    return Layout.WIDE


def roomy(width: float) -> bool:
    """The compact strips can show the log counts, the word Undo and the key hints."""
    return width >= ROOMY_WIDTH


# Fitting the compact top strip's right half (over the bank): the folder picker, Undo and
# Save. Flet cannot ask how wide a text will be, so widths are reckoned from the letters
# (measured on the emulator: about 7.5 dp a letter at the strip's 16 dp text, rounded up).
CHAR_W = 8.0
STRIP_EDGES = 2 * 6 + 2 * 4 + 6 + 4  # page margins, window edges, strip padding
COLUMN_GAP = 14
BUTTON_PAD = 16  # both sides of a strip button
BUTTON_EDGES = 4
ICON_W = 18
GAP = 4
START_KEY_W = 43
WRITE_MARGIN = 2
GROUP_GAPS = 2 * GAP
MIN_LABEL_W = 40.0
# Kept free beside a shortened name, for the letters reckoned rather than measured.
CUT_SPARE = 6.0
# Words whose width was measured on the emulator (dp), for the ones that are always there.
MEASURED_W: dict[str, float] = {"Save into Azahar": 120.0, "Undo": 32.0}


@dataclass(frozen=True)
class StripFit:
    """Whether the Save button keeps its Start key, the width the folder name is held to
    (None: its own width), whether Undo keeps its word, and whether it all fits."""

    start_key: bool
    label_width: float | None
    undo_word: bool = True
    fits: bool = True


def text_width(words: str) -> float:
    """About how wide `words` are in the strip's text: measured, else reckoned by letter."""
    return MEASURED_W.get(words, len(words) * CHAR_W)


def _undo_width(word: bool) -> float:
    return BUTTON_PAD + BUTTON_EDGES + ICON_W + (GAP + text_width("Undo") if word else 0)


def fit_right_column(
    width: float,
    *,
    save_label: str,
    undo_word: bool,
    folder: str,
    count: str | None,
    start_key: bool,
) -> StripFit:
    """Fit the bank's half of the strip into `width`: drop the Start key first, then cut
    the folder name short (never below MIN_LABEL_W), then show Undo as its arrow alone."""
    column = (width - STRIP_EDGES - COLUMN_GAP) / 2
    save = BUTTON_PAD + BUTTON_EDGES + text_width(save_label) + WRITE_MARGIN
    picker = BUTTON_PAD + BUTTON_EDGES + GAP + ICON_W
    if count is not None:
        picker += GAP + text_width(count)
    room = column - save - _undo_width(undo_word) - picker - GROUP_GAPS
    name = text_width(folder)
    if start_key and name <= room - GAP - START_KEY_W:
        return StripFit(True, None, undo_word)
    if name <= room:
        return StripFit(False, None, undo_word)
    if undo_word and room - CUT_SPARE < MIN_LABEL_W:
        room += _undo_width(True) - _undo_width(False)
        undo_word = False
        if name <= room:
            return StripFit(False, None, undo_word)
    cut = max(MIN_LABEL_W, room - CUT_SPARE)
    return StripFit(False, cut, undo_word, cut <= room)
