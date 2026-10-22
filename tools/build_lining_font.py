"""Make the window's text font with lining figures as its plain digits.

Run from the repo root: `uv run python tools/build_lining_font.py`.
Sorts Mill Goudy draws its digits as old-style figures, where a 0 reads like an "o" and a 1
like an "I". It also carries lining figures behind its `lnum` feature, but the window cannot
switch features on, so this writes a copy whose character map sends 0-9 straight to the glyphs
`lnum` would swap in. The copy gets its own family name, as a modified font should, and its
own licence file with a note of the change. The output is committed, so this only needs
running again if the source font changes. Timestamps are kept, so a rerun gives the same file.
"""

import logging
from pathlib import Path

from fontTools.ttLib import TTFont

logger = logging.getLogger("build_lining_font")

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "dq7tt_gui" / "assets" / "fonts"
SOURCE = FONTS / "SortsMillGoudy-Regular.ttf"
SOURCE_LICENCE = FONTS / "OFL-SortsMillGoudy.txt"
OUTPUT = FONTS / "SortsMillGoudyLining-Regular.ttf"
OUTPUT_LICENCE = FONTS / "OFL-SortsMillGoudyLining.txt"

DIGITS = "0123456789"
LINING_FEATURE = "lnum"
SINGLE_SUBSTITUTION = 1
EXTENSION_LOOKUP = 7

FAMILY = "Sorts Mill Goudy Lining"
STYLE = "Regular"
POSTSCRIPT_NAME = "SortsMillGoudyLining-Regular"
# name IDs: family, unique ID, full name, PostScript name
FAMILY_ID, UNIQUE_ID, FULL_NAME_ID, POSTSCRIPT_ID = 1, 3, 4, 6

LICENCE_NOTE = (
    "Sorts Mill Goudy Lining is a modified version of Sorts Mill Goudy Regular: the digits\n"
    "0-9 are mapped to the font's own lining figures (its lnum feature) and the font is\n"
    "renamed. It is made by tools/build_lining_font.py and stays under the licence below.\n\n"
)


def lining_map(font: TTFont) -> dict[str, str]:
    """Every single substitution the font's `lnum` feature makes, glyph name to glyph name."""
    gsub = font["GSUB"].table
    mapping: dict[str, str] = {}
    for record in gsub.FeatureList.FeatureRecord:
        if record.FeatureTag != LINING_FEATURE:
            continue
        for index in record.Feature.LookupListIndex:
            lookup = gsub.LookupList.Lookup[index]
            for sub in lookup.SubTable:
                if lookup.LookupType == EXTENSION_LOOKUP:
                    sub = sub.ExtSubTable
                if sub.LookupType == SINGLE_SUBSTITUTION:
                    mapping.update(sub.mapping)
    return mapping


def remap_digits(font: TTFont) -> dict[str, str]:
    """Point each digit's character map entry at its lining glyph; return digit to glyph."""
    lining = lining_map(font)
    best = font.getBestCmap()
    chosen: dict[str, str] = {}
    for digit in DIGITS:
        old = best[ord(digit)]
        if old not in lining:
            raise KeyError(f"{LINING_FEATURE} has no lining form of {digit!r} ({old})")
        chosen[digit] = lining[old]
    for table in font["cmap"].tables:
        if table.isUnicode():
            for digit, glyph in chosen.items():
                if ord(digit) in table.cmap:
                    table.cmap[ord(digit)] = glyph
    return chosen


def rename(font: TTFont) -> None:
    """Give the copy its own family, full and PostScript names."""
    names = {
        FAMILY_ID: FAMILY,
        UNIQUE_ID: f"{FAMILY} {STYLE}",
        FULL_NAME_ID: f"{FAMILY} {STYLE}",
        POSTSCRIPT_ID: POSTSCRIPT_NAME,
    }
    table = font["name"]
    for record in table.names:
        if record.nameID in names:
            record.string = names[record.nameID]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    font = TTFont(SOURCE)
    font.recalcTimestamp = False
    chosen = remap_digits(font)
    rename(font)
    if "DSIG" in font:
        del font["DSIG"]  # the signature no longer matches the changed tables
    font.save(OUTPUT)
    licence = SOURCE_LICENCE.read_text(encoding="utf-8")
    OUTPUT_LICENCE.write_text(LICENCE_NOTE + licence, encoding="utf-8", newline="")
    logger.info("digits: %s", " ".join(chosen[d] for d in DIGITS))
    for path in (OUTPUT, OUTPUT_LICENCE):
        logger.info("%s  %d bytes", path.relative_to(ROOT).as_posix(), path.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
