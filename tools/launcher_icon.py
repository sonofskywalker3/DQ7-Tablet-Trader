"""The Android launcher icon: a carved story stone inside a gold ring on the dark window ground.

Drawn by `tools/build_gui_art.py`, which passes in the stone's outlines and colours so the icon's
stone is the same drawing as the list's. The result is a finished, opaque square that `flet
build` uses as it is (`icon_android.png`) for both the plain icon and the adaptive icon's front
layer. Everything that matters sits inside the circle Android always shows, so a round, square
or rounded launcher mask never cuts the stone or the ring.
"""

import math

from PIL import Image, ImageDraw

ICON_SIZE = 1024
SUPERSAMPLE = 2  # drawn this much larger, then shrunk, for smooth edges
GRADIENT_STEP = 8

# The dark menu window's colour, a touch lighter in the middle so the stone stands forward.
GROUND_EDGE = "#16120e"
GROUND_CENTRE = "#463826"
GOLD = "#f0c860"
GOLD_DARK = "#7a4a0c"

# Shares of the icon's width. Android shows at least a centred circle 66/108 wide, so the
# ring and its compass points stay inside a radius of 0.30 (the circle is 0.306).
RING_RADIUS = 0.28
RING_WIDTH = 0.012
INNER_RING_RADIUS = 0.25
INNER_RING_WIDTH = 0.005
POINT_INNER = 0.235
POINT_OUTER = 0.30
POINT_HALF_WIDTH = 0.022
STONE_HEIGHT = 0.40  # the slab's height; the 64-unit drawing's slab spans 58 units
SLAB_UNITS = 58.0
STONE_CENTRE_UNITS = (32.0, 32.0)
SHADOW_OFFSET_UNITS = (1.5, 2.5)
SHADOW_ALPHA = 90


def _hex(colour: str) -> tuple[int, int, int]:
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)


def path_points(path: str) -> list[list[tuple[float, float]]]:
    """Split an SVG path made of M, L, H, V and Z (absolute only) into point runs."""
    runs: list[list[tuple[float, float]]] = []
    tokens = path.replace(",", " ")
    for letter in "MLHVZ":
        tokens = tokens.replace(letter, f" {letter} ")
    words = tokens.split()
    x = y = 0.0
    command = "M"
    i = 0
    while i < len(words):
        word = words[i]
        if word in "MLHVZ":
            command = word
            i += 1
            if command == "Z" and runs:
                runs[-1].append(runs[-1][0])
            continue
        if command == "M":
            x, y = float(words[i]), float(words[i + 1])
            runs.append([(x, y)])
            command = "L"  # coordinates after a move are lines
            i += 2
        elif command == "L":
            x, y = float(words[i]), float(words[i + 1])
            runs[-1].append((x, y))
            i += 2
        elif command == "H":
            x = float(word)
            runs[-1].append((x, y))
            i += 1
        elif command == "V":
            y = float(word)
            runs[-1].append((x, y))
            i += 1
        else:
            raise ValueError(f"unsupported path command {command!r}")
    return runs


def _ground(side: int) -> Image.Image:
    small = max(2, side // GRADIENT_STEP)
    edge, centre = _hex(GROUND_EDGE), _hex(GROUND_CENTRE)
    ground = Image.new("RGB", (small, small))
    pixels = []
    for y in range(small):
        for x in range(small):
            d = min(1.0, math.hypot(x / small - 0.5, y / small - 0.5) / 0.5)
            t = d**1.4
            pixels.append(tuple(round(c + (e - c) * t) for c, e in zip(centre, edge, strict=True)))
    ground.putdata(pixels)
    return ground.resize((side, side), Image.Resampling.BICUBIC)


def _ring(pen: ImageDraw.ImageDraw, side: int, radius: float, width: float, fill: str) -> None:
    c, r = side / 2, radius * side
    pen.ellipse([c - r, c - r, c + r, c + r], outline=fill, width=max(1, round(width * side)))


def _compass_points(pen: ImageDraw.ImageDraw, side: int) -> None:
    c = side / 2
    for k in range(4):
        angle = k * math.pi / 2
        ux, uy = math.cos(angle), math.sin(angle)
        px, py = -uy, ux
        inner = (c + ux * POINT_INNER * side, c + uy * POINT_INNER * side)
        outer = (c + ux * POINT_OUTER * side, c + uy * POINT_OUTER * side)
        mid_r = (POINT_INNER + POINT_OUTER) / 2 * side
        half = POINT_HALF_WIDTH * side
        left = (c + ux * mid_r + px * half, c + uy * mid_r + py * half)
        right = (c + ux * mid_r - px * half, c + uy * mid_r - py * half)
        pen.polygon([inner, left, outer, right], fill=GOLD, outline=GOLD_DARK, width=3)


def _stroke(
    pen: ImageDraw.ImageDraw,
    runs: list[list[tuple[float, float]]],
    fill: tuple[int, ...] | str,
    width: int,
) -> None:
    """Draw point runs as lines with round ends and joints."""
    for run in runs:
        pen.line(run, fill=fill, width=width, joint="curve")
        for x, y in (run[0], run[-1]):
            pen.ellipse([x - width / 2, y - width / 2, x + width / 2, y + width / 2], fill=fill)


def draw_icon(
    shape: dict[str, str], colours: tuple[str, str, str, str], rays: str, size: int = ICON_SIZE
) -> Image.Image:
    """The launcher icon, `size` pixels square and opaque.

    `shape` holds the stone's slab, face, hi and panel outlines in the 64-unit tablet drawing;
    `colours` are its edge, face, light and carve colours; `rays` is the sun's ray path.
    """
    side = size * SUPERSAMPLE
    image = _ground(side).convert("RGBA")
    pen = ImageDraw.Draw(image)
    _ring(pen, side, RING_RADIUS, RING_WIDTH, GOLD)
    _ring(pen, side, INNER_RING_RADIUS, INNER_RING_WIDTH, GOLD_DARK)
    _compass_points(pen, side)

    unit = STONE_HEIGHT * side / SLAB_UNITS
    cx, cy = STONE_CENTRE_UNITS

    def at(path: str, dx: float = 0.0, dy: float = 0.0) -> list[list[tuple[float, float]]]:
        return [
            [(side / 2 + (x + dx - cx) * unit, side / 2 + (y + dy - cy) * unit) for x, y in run]
            for run in path_points(path)
        ]

    def scaled(units: float) -> int:
        return max(1, round(units * unit))

    edge, face, light, carve = colours
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).polygon(
        at(shape["slab"], *SHADOW_OFFSET_UNITS)[0], fill=(0, 0, 0, SHADOW_ALPHA)
    )
    image = Image.alpha_composite(image, shadow)
    pen = ImageDraw.Draw(image)
    pen.polygon(at(shape["slab"])[0], fill=edge)
    pen.polygon(at(shape["face"])[0], fill=face)
    _stroke(pen, at(shape["hi"]), light, scaled(2))
    panel = Image.new("RGBA", image.size, (0, 0, 0, 0))
    _stroke(ImageDraw.Draw(panel), at(shape["panel"]), (*_hex(carve), 128), scaled(1.2))
    image = Image.alpha_composite(image, panel)
    pen = ImageDraw.Draw(image)

    # The story stone's sun: rays with a dark rim, then the disc and its glint.
    _stroke(pen, at(rays), "#5e4310", scaled(4.4))
    _stroke(pen, at(rays), "#efc552", scaled(2.4))
    sun_x, sun_y = side / 2, side / 2 + (31 - cy) * unit
    r = 7 * unit
    pen.ellipse(
        [sun_x - r, sun_y - r, sun_x + r, sun_y + r],
        fill="#efc552",
        outline="#5e4310",
        width=scaled(1.4),
    )
    glint_x, glint_y, gr = sun_x - 2 * unit, sun_y - 2 * unit, 2.2 * unit
    pen.ellipse([glint_x - gr, glint_y - gr, glint_x + gr, glint_y + gr], fill="#fff0b8")
    return image.convert("RGB").resize((size, size), Image.Resampling.LANCZOS)
