"""Which layout the window takes for a page size, and the compact layout's two widths."""

import pytest

from dq7tt_gui.layout import (
    CHAR_W,
    COMPACT_MIN_WIDTH,
    MIN_LABEL_W,
    NARROW_WIDTH,
    SHORT_HEIGHT,
    Layout,
    StripFit,
    choose_layout,
    fit_right_column,
    roomy,
)


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (1280, 800, Layout.WIDE),
        (640, 360, Layout.COMPACT),
        (853, 480, Layout.COMPACT),
        (832.52, 468.29, Layout.COMPACT),
        (1920, 1080, Layout.WIDE),
        (360, 413, Layout.TABS),
        (899, 900, Layout.COMPACT),
        (599, 360, Layout.TABS),
        (1280, 519, Layout.COMPACT),
        (900, 520, Layout.WIDE),
    ],
)
def test_choose_layout(width: float, height: float, expected: Layout) -> None:
    assert choose_layout(width, height) is expected


def test_thresholds_are_the_agreed_ones() -> None:
    assert (COMPACT_MIN_WIDTH, NARROW_WIDTH, SHORT_HEIGHT) == (600, 900, 520)


def test_roomy_only_from_the_default_thor_width() -> None:
    assert not roomy(640)
    assert roomy(832.52)
    assert roomy(853)


def test_layout_choice_needs_no_flet() -> None:
    from pathlib import Path

    import dq7tt_gui.layout as layout

    text = Path(layout.__file__).read_text(encoding="utf-8")
    assert "import flet" not in text and "from flet" not in text


def fit(width: float, folder: str, roomy_: bool, count: str | None = "4") -> StripFit:
    return fit_right_column(
        width,
        save_label="Save into Azahar",
        undo_word=roomy_,
        folder=folder,
        count=count if roomy_ else None,
        start_key=roomy_,
    )


def test_strip_keeps_everything_when_it_fits() -> None:
    at_832 = fit(832.52, "Unsorted", True)
    assert at_832.start_key and at_832.label_width is None
    at_640 = fit(640, "Unsorted", False)
    assert not at_640.start_key and at_640.label_width is None


def test_long_folder_name_drops_start_then_shortens_the_name() -> None:
    name = "Twenty letters long!"
    assert len(name) == 20
    for width, wide in ((832.52, True), (853, True), (640, False)):
        result = fit(width, name, wide)
        assert not result.start_key
        assert result.label_width is not None
        assert MIN_LABEL_W <= result.label_width < len(name) * CHAR_W


def test_start_goes_before_the_name_is_cut() -> None:
    # A name that fits only once the Start key is gone keeps its full width.
    result = fit(832.52, "Haven tablets", True)
    assert not result.start_key and result.label_width is None


WRITE_BOTH_SHORT = "Write both"


@pytest.mark.parametrize("width", [600, 640, 760, 832.52])
@pytest.mark.parametrize("folder", ["Unsorted", "Twenty letters long!"])
def test_write_both_fits_the_compact_strip(width: float, folder: str) -> None:
    wide = roomy(width)
    result = fit_right_column(
        width,
        save_label=WRITE_BOTH_SHORT,
        undo_word=wide,
        folder=folder,
        count="4" if wide else None,
        start_key=wide,
    )
    assert result.fits


def test_undo_loses_its_word_when_the_name_cannot_be_cut_further() -> None:
    result = fit_right_column(
        832.52,
        save_label="Write changes to both saves",
        undo_word=True,
        folder="Unsorted",
        count="4",
        start_key=True,
    )
    assert result.fits
    assert not result.undo_word and not result.start_key
    assert result.label_width is not None and result.label_width >= MIN_LABEL_W


def test_strip_keeps_the_undo_word_when_there_is_room() -> None:
    result = fit(832.52, "Unsorted", True)
    assert result.undo_word and result.fits
