"""Draw the desktop window's art into dq7tt_gui/assets/.

Run from the repo root: `uv run python tools/build_gui_art.py`.
Everything here is drawn from scratch: the parchment ground, the engraved bands, the compass
rose, the gold pointer, one carved stone per tablet kind and the Android launcher icon
(`icon_android.png`, drawn by `launcher_icon.py` from the story stone). The output is
committed, so this only needs running again after the drawings change. Random parts use fixed
seeds, so a rerun gives the same files.
"""

import logging
import math
import random
from pathlib import Path

from launcher_icon import draw_icon
from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger("build_gui_art")

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "dq7tt_gui" / "assets"
TABLETS = ASSETS / "tablets"
# `flet build apk` takes the launcher icon from the app's assets under this name.
LAUNCHER_ICON = ASSETS / "icon_android.png"
LAUNCHER_ICON_KIND = "story"

# Parchment ground, sized for a 1280x800 window at 150% scale and cropped to fit.
PARCHMENT_W, PARCHMENT_H = 1600, 1000
GRADIENT_STEP = 4  # gradients are worked out on a coarse grid, then smoothed up
MOTTLE_SEED = 7
FIBRE_SEED = 11
FIBRE_COUNT = 900
STRIATION_GAP = 5

# One tile of the engraved band, in drawing units, and how much finer it is drawn.
BAND_W, BAND_H = 160, 26
BAND_SCALE = 3  # the saved tile: three pixels per unit, sharp at high display scales
BAND_SUPERSAMPLE = 4  # drawn this much finer again, then shrunk, for smooth edges
WAVE_START, WAVE_END, WAVE_PERIOD, WAVE_AMPLITUDE = 28.0, 132.0, 36.0, 3.4

POINTER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="30" height="18" viewBox="0 0 30 18">
<circle cx="5" cy="9" r="3.5" fill="none" stroke="#7a4a0c" stroke-width="3"/>
<circle cx="5" cy="9" r="3.5" fill="none" stroke="#f5b82e" stroke-width="1.6"/>
<path d="M8.5 6.5 H17 L17 4 L28.5 9 L17 14 L17 11.5 H8.5 Z" fill="#f5b82e" stroke="#7a4a0c"
 stroke-width="1.2" stroke-linejoin="round"/>
<path d="M10 8 H18.5 L25 9" stroke="#ffe7a3" stroke-width="1.2" fill="none"/>
<path d="M12 6.5 V11.5 M14.5 6.5 V11.5" stroke="#7a4a0c" stroke-width="1"/>
</svg>
"""

COMPASS_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="112" height="112"
 viewBox="-56 -56 112 112">
<circle r="34" fill="none" stroke="#5a4422" stroke-width="2"/>
<circle r="29" fill="none" stroke="#5a4422" stroke-width="1"/>
<path d="M0 0 L17 -17 L5 -4 Z M0 0 L17 17 L4 5 Z M0 0 L-17 17 L-5 4 Z M0 0 L-17 -17 L-4 -5 Z"
 fill="#7a5f34"/>
<path d="M0 -50 L6 -6 L0 0 Z M50 0 L6 6 L0 0 Z M0 50 L-6 6 L0 0 Z M-50 0 L-6 -6 L0 0 Z"
 fill="#4a3518"/>
<path d="M0 -50 L-6 -6 L0 0 Z M50 0 L6 -6 L0 0 Z M0 50 L6 6 L0 0 Z M-50 0 L-6 6 L0 0 Z"
 fill="#c9b07c" stroke="#4a3518" stroke-width="1.5"/>
</svg>
"""

# The big compass drawn faintly into the bank window; the faintness is part of the file.
COMPASS_FAINT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="112" height="112"
 viewBox="-56 -56 112 112">
<g opacity="0.13">
<circle r="34" fill="none" stroke="#efe3c4" stroke-width="1.2"/>
<circle r="30" fill="none" stroke="#efe3c4" stroke-width="0.6"/>
<circle r="22" fill="none" stroke="#efe3c4" stroke-width="0.8" stroke-dasharray="1.5 2"/>
<path d="M0 0 L16 -16 L4 -4 Z M0 0 L16 16 L4 4 Z M0 0 L-16 16 L-4 4 Z M0 0 L-16 -16 L-4 -4 Z"
 fill="#efe3c4"/>
<path d="M0 -46 L5 -5 L0 0 Z M46 0 L5 5 L0 0 Z M0 46 L-5 5 L0 0 Z M-46 0 L-5 -5 L0 0 Z"
 fill="#efe3c4"/>
<path d="M0 -46 L-5 -5 L0 0 Z M46 0 L5 -5 L0 0 Z M0 46 L5 5 L0 0 Z M-46 0 L-5 5 L0 0 Z"
 fill="none" stroke="#efe3c4" stroke-width="0.8"/>
<path d="M-3 -49 V-55 L3 -49 V-55" fill="none" stroke="#efe3c4" stroke-width="1.2"/>
</g>
</svg>
"""

# Stone colours per kind: edge, face, light, carve.
STONES: dict[str, tuple[str, str, str, str]] = {
    "story": ("#4b4936", "#a39f84", "#d6d1b4", "#3b3826"),
    "dlc": ("#26375a", "#7089b0", "#b2c7e6", "#1c2a46"),
    "resident": ("#5c4426", "#c4a26c", "#ecd5a4", "#47321a"),
    "streetpass": ("#3d2f52", "#8d79a7", "#cbbbe0", "#2c2140"),
    "unknown": ("#26262b", "#60606a", "#9a9aa4", "#1b1b1f"),
}

WHOLE = {
    "slab": "M13 5 L47 3 L58 12 L59 55 L35 61 L8 58 L5 17 Z",
    "face": "M15 9 L45 7.5 L54 14 L55 52 L35 56.5 L11.5 54 L9 19 Z",
    "hi": "M10 50 L9 19 L15 9 L45 7.5",
    "panel": "M17.5 14 L43 13 L49 18 L49.5 47 L34 50.5 L16.5 48.5 L15 20 Z",
}
BROKEN = {
    "slab": "M13 5 L38 3 L41 13 L50 15 L59 27 L57 55 L35 61 L8 58 L5 17 Z",
    "face": "M15 9 L36.5 7.5 L38.5 16 L48 18.5 L55 29 L53.5 52 L35 56.5 L11.5 54 L9 19 Z",
    "hi": "M10 50 L9 19 L15 9 L36.5 7.5",
    "panel": "M17.5 14 L34 13 L35.5 19.5 L45 22 L49.5 30 L48.5 47 L34 50.5 L16.5 48.5 L15 20 Z",
}

SUN_RAYS = (
    "M32 18 V22 M32 40 V44 M19 31 H23 M41 31 H45 M23 22 L25.8 24.8 M41 22 L38.2 24.8 "
    "M23 40 L25.8 37.2 M41 40 L38.2 37.2"
)
HOUSE = "M20 34 L32 22 L44 34 M23 32 V45 H41 V32 M29.5 45 V38 H34.5 V45"
ARROWS = "M18 26 H43 M37 20.5 L43 26 L37 31.5 M46 37 H21 M27 31.5 L21 37 L27 42.5"
QUESTION = (
    "M25.5 24 C25.5 18.5 29 16.5 32.5 16.5 C36.5 16.5 39.5 19 39.5 23 C39.5 27.5 33 28.5 33 34"
)
NUDGE = 'transform="translate(0.9 0.9)"'


def _carving(kind: str, light: str, carve: str) -> str:
    """The emblem cut into the stone's face: what tells the kinds apart."""
    if kind == "story":
        return (
            f'<path d="{SUN_RAYS}" fill="none" stroke="#5e4310" stroke-width="4.4" '
            'stroke-linecap="round"/>'
            f'<path d="{SUN_RAYS}" fill="none" stroke="#efc552" stroke-width="2.4" '
            'stroke-linecap="round"/>'
            '<circle cx="32" cy="31" r="7" fill="#efc552" stroke="#5e4310" stroke-width="1.4"/>'
            '<circle cx="30" cy="29" r="2.2" fill="#fff0b8"/>'
        )
    if kind == "dlc":
        return (
            '<circle cx="32" cy="31" r="13" fill="#bdf1ff" fill-opacity="0.22"/>'
            '<path d="M32 14.5 L35.6 27.4 L48.5 31 L35.6 34.6 L32 47.5 L28.4 34.6 L15.5 31 '
            'L28.4 27.4 Z" fill="#a6ecff" stroke="#1d5877" stroke-width="1.3" '
            'stroke-linejoin="round"/>'
            '<path d="M32 20 L33.6 29.4 L42 31" fill="none" stroke="#ffffff" stroke-width="1.2" '
            'stroke-linecap="round" stroke-opacity="0.85"/>'
            '<circle cx="32" cy="31" r="2" fill="#ffffff"/>'
        )
    if kind == "resident":
        return (
            f'<path d="{HOUSE}" {NUDGE} fill="none" stroke="{light}" stroke-width="2.8" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="{HOUSE}" fill="none" stroke="{carve}" stroke-width="2.8" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="32" cy="29" r="1.8" fill="#7fbf5a" stroke="{carve}" '
            'stroke-width="0.8"/>'
        )
    if kind == "streetpass":
        return (
            f'<path d="{ARROWS}" {NUDGE} fill="none" stroke="#f1e6ff" stroke-width="2.8" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="{ARROWS}" fill="none" stroke="{carve}" stroke-width="2.8" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )
    return (
        f'<path d="M23 56 L27 47 L24 41 L29 34" fill="none" stroke="{carve}" '
        'stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<path d="{QUESTION}" {NUDGE} fill="none" stroke="{light}" stroke-width="3.2" '
        'stroke-linecap="round"/>'
        f'<path d="{QUESTION}" fill="none" stroke="{carve}" stroke-width="3.2" '
        'stroke-linecap="round"/>'
        f'<circle cx="33.9" cy="41.9" r="2.3" fill="{light}"/>'
        f'<circle cx="33" cy="41" r="2.3" fill="{carve}"/>'
    )


def tablet_svg(kind: str) -> str:
    """One carved stone tablet, drawn for list rows (it reads at 32 px)."""
    edge, face, light, carve = STONES[kind]
    shape = BROKEN if kind == "unknown" else WHOLE
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">\n'
        f'<path d="{shape["slab"]}" transform="translate(1.5 2.5)" fill="#000000" '
        'fill-opacity="0.35"/>\n'
        f'<path d="{shape["slab"]}" fill="{edge}"/>\n'
        f'<path d="{shape["face"]}" fill="{face}"/>\n'
        f'<path d="{shape["hi"]}" fill="none" stroke="{light}" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round"/>\n'
        f'<path d="{shape["panel"]}" fill="none" stroke="{carve}" stroke-opacity="0.5" '
        'stroke-width="1.2" stroke-linejoin="round"/>\n'
        f"{_carving(kind, light, carve)}\n"
        "</svg>\n"
    )


def _hex(colour: str) -> tuple[int, int, int]:
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)


def _mix(a: tuple[float, ...], b: tuple[float, ...], t: float) -> tuple[float, ...]:
    return tuple(x + (y - x) * t for x, y in zip(a, b, strict=True))


def _ground_colour(u: float, v: float) -> tuple[int, int, int]:
    """The parchment's colour at (u, v) in 0..1: a warm centre, a highlight and a shade."""
    stops = ((0.0, _hex("#e3d0a4")), (0.6, _hex("#d3bc8c")), (1.0, _hex("#b39867")))
    d = min(1.0, math.hypot(u - 0.5, v - 0.5) / math.hypot(0.5, 0.5))
    colour: tuple[float, ...] = stops[-1][1]
    for (t0, c0), (t1, c1) in zip(stops, stops[1:], strict=False):
        if d <= t1:
            colour = _mix(c0, c1, (d - t0) / (t1 - t0))
            break
    glow = max(0.0, 1.0 - math.hypot((u - 0.30) / 0.60, (v - 0.40) / 0.50) / 0.70)
    colour = _mix(colour, _hex("#fff6d6"), 0.55 * glow)
    shade = max(0.0, 1.0 - math.hypot((u - 0.82) / 0.50, (v - 0.72) / 0.60) / 0.70)
    colour = _mix(colour, _hex("#967646"), 0.28 * shade)
    return (round(colour[0]), round(colour[1]), round(colour[2]))


def parchment() -> Image.Image:
    """Aged parchment: soft gradients, blotchy mottling, fine fibres and faint striations."""
    small_w, small_h = PARCHMENT_W // GRADIENT_STEP, PARCHMENT_H // GRADIENT_STEP
    ground = Image.new("RGB", (small_w, small_h))
    ground.putdata(
        [_ground_colour(x / small_w, y / small_h) for y in range(small_h) for x in range(small_w)]
    )
    ground = ground.resize((PARCHMENT_W, PARCHMENT_H), Image.Resampling.BICUBIC)

    rng = random.Random(MOTTLE_SEED)
    mottle = Image.new("L", (PARCHMENT_W, PARCHMENT_H), 128)
    for size, weight in ((8, 0.55), (24, 0.3), (80, 0.15)):
        layer = Image.new("L", (size, max(2, size * PARCHMENT_H // PARCHMENT_W)))
        layer.putdata([rng.randint(0, 255) for _ in range(layer.width * layer.height)])
        layer = layer.resize((PARCHMENT_W, PARCHMENT_H), Image.Resampling.BICUBIC)
        mottle = Image.blend(mottle, layer, weight)
    grain = Image.effect_noise((PARCHMENT_W, PARCHMENT_H), 18).filter(ImageFilter.BoxBlur(1))
    mottle = Image.blend(mottle, grain, 0.25)
    dark = Image.new("RGB", ground.size, _hex("#8a6d40"))
    light = Image.new("RGB", ground.size, _hex("#f6e9c4"))
    # Below mid grey darkens toward old brown, above it lightens toward fresh paper.
    darker = Image.composite(dark, ground, mottle.point(lambda p: max(0, 128 - p) * 2 // 3))
    page = Image.composite(light, darker, mottle.point(lambda p: max(0, p - 128) // 2))

    fibres = Image.new("L", page.size, 0)
    pen = ImageDraw.Draw(fibres)
    rng = random.Random(FIBRE_SEED)
    for _ in range(FIBRE_COUNT):
        x, y = rng.uniform(0, PARCHMENT_W), rng.uniform(0, PARCHMENT_H)
        angle, length = rng.uniform(0, math.pi), rng.uniform(6, 40)
        bend = rng.uniform(-4, 4)
        mid = (x + math.cos(angle) * length / 2 + bend, y + math.sin(angle) * length / 2 + bend)
        end = (x + math.cos(angle) * length, y + math.sin(angle) * length)
        pen.line([(x, y), mid, end], fill=rng.randint(18, 40), width=1)
    for y in range(0, PARCHMENT_H, STRIATION_GAP):
        edge = abs(y / PARCHMENT_H - 0.5) * 2  # striations show most toward top and bottom
        pen.line([(0, y), (PARCHMENT_W, y)], fill=round(10 * edge**2))
    fibres = fibres.filter(ImageFilter.GaussianBlur(0.6))
    ink = Image.new("RGB", page.size, _hex("#6e5634"))
    return Image.composite(ink, page, fibres)


def _band_tile() -> Image.Image:
    """One 160x26 tile of the engraved border band, upright (the top band)."""
    s = BAND_SCALE * BAND_SUPERSAMPLE
    tile = Image.new("RGB", (BAND_W * s, BAND_H * s), _hex("#c6ad7e"))
    pen = ImageDraw.Draw(tile)

    def box(x0: float, y0: float, x1: float, y1: float) -> list[float]:
        return [x0 * s, y0 * s, x1 * s, y1 * s]

    pen.rectangle(box(0, 0, BAND_W, 3), fill=_hex("#7d6440"))
    pen.line(box(0, 5.5, BAND_W, 5.5), fill=_hex("#9c8358"), width=round(1 * s))
    pen.line(box(0, 22.5, BAND_W, 22.5), fill=_hex("#7d6440"), width=round(1.5 * s))
    pen.rounded_rectangle(
        box(16, 9, 144, 19),
        radius=5 * s,
        fill=_hex("#dac698"),
        outline=_hex("#7d6440"),
        width=round(1.2 * s),
    )
    wave = []
    steps = 200
    for i in range(steps + 1):
        x = WAVE_START + (WAVE_END - WAVE_START) * i / steps
        y = 14 - WAVE_AMPLITUDE * math.sin(2 * math.pi * (x - WAVE_START) / WAVE_PERIOD)
        wave.append((x * s, y * s))
    pen.line(wave, fill=_hex("#8d7349"), width=round(1.1 * s), joint="curve")
    for cx in (0, BAND_W):  # half studs at each end meet the next tile's into whole ones
        pen.ellipse(
            box(cx - 5.5, 8.5, cx + 5.5, 19.5),
            fill=_hex("#b0956a"),
            outline=_hex("#6e5634"),
            width=round(1.2 * s),
        )
        pen.ellipse(box(cx - 2, 12, cx + 2, 16), fill=_hex("#e6d6ab"))
    size = (BAND_W * BAND_SCALE, BAND_H * BAND_SCALE)
    return tile.resize(size, Image.Resampling.LANCZOS)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    TABLETS.mkdir(parents=True, exist_ok=True)
    for kind in STONES:
        (TABLETS / f"{kind}.svg").write_text(tablet_svg(kind), encoding="utf-8")
    (ASSETS / "pointer.svg").write_text(POINTER_SVG, encoding="utf-8")
    (ASSETS / "compass.svg").write_text(COMPASS_SVG, encoding="utf-8")
    (ASSETS / "compass_faint.svg").write_text(COMPASS_FAINT_SVG, encoding="utf-8")
    band = _band_tile()
    band.save(ASSETS / "band_top.png", optimize=True)
    band.transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(ASSETS / "band_bottom.png", optimize=True)
    parchment().save(ASSETS / "parchment.png", optimize=True)
    draw_icon(WHOLE, STONES[LAUNCHER_ICON_KIND], SUN_RAYS).save(LAUNCHER_ICON, optimize=True)
    for path in sorted(ASSETS.rglob("*.*")):
        logger.info("%s  %d bytes", path.relative_to(ROOT).as_posix(), path.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
