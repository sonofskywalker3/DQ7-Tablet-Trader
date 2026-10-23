"""The window's pictures and fonts: present, registered, and packed into the exe."""

import importlib.util
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType

import flet as ft
import pytest
from test_window import FakePage

from dq7tt.tablets import TabletKind
from dq7tt_gui import art, theme

ROOT = Path(__file__).resolve().parents[2]
FONT_LICENCES = ("OFL-SortsMillGoudy.txt", "OFL-SortsMillGoudyLining.txt", "OFL-Cinzel.txt")


def load_tool(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_tool() -> ModuleType:
    return load_tool("build_windows")


def lining_tool() -> ModuleType:
    return load_tool("build_lining_font")


def test_every_asset_the_window_names_is_there() -> None:
    assert art.ASSETS_DIR == ROOT / "dq7tt_gui" / "assets"
    for name in art.asset_files():
        assert (art.ASSETS_DIR / name).is_file(), name


def test_every_kind_has_a_tablet_icon() -> None:
    assert set(art.TABLET_ICONS) == set(TabletKind)


def test_svg_art_is_well_formed() -> None:
    for name in art.asset_files():
        if name.endswith(".svg"):
            root = ET.parse(art.ASSETS_DIR / name).getroot()
            assert root.tag.endswith("svg"), name


def test_bundled_fonts_ship_with_their_licences() -> None:
    fonts = art.ASSETS_DIR / "fonts"
    for licence in FONT_LICENCES:
        text = (fonts / licence).read_text(encoding="utf-8")
        assert "SIL Open Font License" in text


def test_style_page_registers_fonts_and_serif_theme() -> None:
    page = FakePage()
    art.style_page(page)  # type: ignore[arg-type]
    assert page.fonts == art.FONTS  # type: ignore[attr-defined]
    assert set(page.fonts) == {theme.BODY_FONT, theme.HEADING_FONT}  # type: ignore[attr-defined]
    for t in (page.theme, page.dark_theme):  # type: ignore[attr-defined]
        assert isinstance(t, ft.Theme) and t.font_family == theme.BODY_FONT
    assert page.theme_mode == ft.ThemeMode.DARK  # type: ignore[attr-defined]
    assert page.window.min_width == theme.MIN_W


def test_exe_build_packs_the_window_assets_where_art_looks() -> None:
    cmd = build_tool().build_command()
    pairs = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--add-data"]
    assert "dq7tt_gui/assets:dq7tt_gui/assets" in pairs
    # art.ASSETS_DIR is found beside the package, so the bundle must keep that layout.
    assert art.ASSETS_DIR.relative_to(ROOT).as_posix() == "dq7tt_gui/assets"


def test_body_font_draws_plain_digits_as_lining_figures() -> None:
    # Old-style 0 and 1 read as "o" and "I"; the window's text font maps 0-9 to lining glyphs.
    ttlib = pytest.importorskip("fontTools.ttLib")
    font = ttlib.TTFont(art.ASSETS_DIR / art.FONTS[theme.BODY_FONT])
    cmap = font.getBestCmap()
    for digit in "0123456789":
        assert cmap[ord(digit)].endswith(".lining"), digit
    assert font["name"].getDebugName(1) == theme.BODY_FONT


def test_body_font_takes_the_lining_glyphs_from_the_source_fonts_lnum() -> None:
    pytest.importorskip("fontTools.ttLib")
    tool = lining_tool()
    built = tool.TTFont(tool.OUTPUT).getBestCmap()
    source = tool.TTFont(tool.SOURCE)
    lining = tool.lining_map(source)
    for digit in tool.DIGITS:
        assert built[ord(digit)] == lining[source.getBestCmap()[ord(digit)]], digit


ICON_NAME = "icon_android.png"
FLET_ICON_SIZE = 1024


def test_launcher_icon_path_reader_follows_lines_and_closes_shapes() -> None:
    icon = load_tool("launcher_icon")
    assert icon.path_points("M1 2 L3 4 H5 V6 Z M7 8 V9") == [
        [(1.0, 2.0), (3.0, 4.0), (5.0, 4.0), (5.0, 6.0), (1.0, 2.0)],
        [(7.0, 8.0), (7.0, 9.0)],
    ]


def test_launcher_icon_is_committed_where_flet_build_finds_it_and_is_current(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PIL import Image, ImageChops

    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    tool = load_tool("build_gui_art")
    assert tool.LAUNCHER_ICON == art.ASSETS_DIR / ICON_NAME
    committed = Image.open(tool.LAUNCHER_ICON)
    # A finished opaque square: flet build uses icon_android.png as it is, without reframing.
    assert committed.size == (FLET_ICON_SIZE, FLET_ICON_SIZE)
    assert committed.mode == "RGB"
    drawn = tool.draw_icon(tool.WHOLE, tool.STONES[tool.LAUNCHER_ICON_KIND], tool.SUN_RAYS)
    assert ImageChops.difference(drawn, committed.convert("RGB")).getbbox() is None


def test_launcher_icon_keeps_its_drawing_inside_the_adaptive_safe_circle() -> None:
    from PIL import Image

    icon = load_tool("launcher_icon")
    image = Image.open(art.ASSETS_DIR / ICON_NAME).convert("RGB")
    side = image.width
    ground = image.getpixel((0, 0))
    safe_radius = side * 33 / 108  # Android always shows a centred circle 66 of 108 wide
    for x in range(0, side, 8):
        for y in range(0, side, 8):
            if (x - side / 2) ** 2 + (y - side / 2) ** 2 > safe_radius**2:
                pixel = image.getpixel((x, y))
                # Outside the circle there is only the dark ground, no gold and no stone.
                assert max(pixel) <= max(icon._hex(icon.GROUND_CENTRE)), (x, y, pixel, ground)
