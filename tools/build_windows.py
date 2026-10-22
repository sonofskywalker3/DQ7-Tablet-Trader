"""Build the single-file Windows exe with `flet pack`.

Run from the repo root: `uv run python tools/build_windows.py`.
The exe lands in dist/. Nothing here is committed (dist/, build/ and *.spec are ignored).
"""

import logging
import subprocess
import sys
from pathlib import Path

from dq7tt import __version__

logger = logging.getLogger("build_windows")

ROOT = Path(__file__).resolve().parent.parent
ENTRY = "dq7tt_gui/main.py"
EXE_NAME = "DQ7 Tablet Trader"
ICON = ROOT / "assets" / "icon.ico"
DATA_DIR = ROOT / "dq7tt" / "data"
DATA_DEST = "dq7tt/data"
# The window's pictures and fonts, kept at the same place inside the bundle as in the
# source tree: dq7tt_gui/art.py finds them beside itself.
GUI_ASSETS = "dq7tt_gui/assets"
COMPANY = "DQ7 Tablet Trader"
LICENCE = "GPL-3.0-or-later"


def numeric_version(version: str) -> str:
    """Windows file versions need four numbers: 0.1.0 becomes 0.1.0.0."""
    parts = [p for p in version.split(".") if p.isdigit()][:4]
    return ".".join(parts + ["0"] * (4 - len(parts)))


def build_command() -> list[str]:
    version = numeric_version(__version__)
    cmd = [
        sys.executable, "-m", "flet_cli.cli", "pack", ENTRY, "-y",
        "--name", EXE_NAME,
        "--product-name", EXE_NAME,
        "--file-description", "Traveller's Tablet manager for Dragon Quest VII (3DS) saves",
        "--product-version", version,
        "--file-version", version,
        "--copyright", LICENCE,
        "--distpath", "dist",
    ]  # fmt: skip
    for data_file in sorted(DATA_DIR.glob("*.json")):
        rel = data_file.relative_to(ROOT).as_posix()
        cmd += ["--add-data", f"{rel}:{DATA_DEST}"]
    cmd += ["--add-data", f"{GUI_ASSETS}:{GUI_ASSETS}"]
    if ICON.exists():
        cmd += ["--icon", str(ICON)]
    return cmd


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cmd = build_command()
    logger.info("running: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT, check=False)
    if result.returncode == 0:
        logger.info("built %s", ROOT / "dist" / f"{EXE_NAME}.exe")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
