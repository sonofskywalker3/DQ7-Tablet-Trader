import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SMOKE_ENV = "DQ7TT_GUI_SMOKE"
APP_DIR_ENV = "DQ7TT_APP_DIR"
SMOKE_TIMEOUT_SECONDS = 60


def test_core_never_imports_flet() -> None:
    for source in (ROOT / "dq7tt").glob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert "import flet" not in text, source.name
        assert "from flet" not in text, source.name


def test_gui_package_imports() -> None:
    import dq7tt_gui.main as gui_main
    import dq7tt_gui.theme as theme

    assert callable(gui_main.run)
    assert theme.ROW_HEIGHT == 40


@pytest.mark.skipif(os.environ.get(SMOKE_ENV) != "1", reason="opens a real window")
def test_launch_smoke(tmp_path: Path) -> None:
    result = subprocess.run(
        ["uv", "run", "dq7tt-gui"],
        cwd=ROOT,
        env={**os.environ, SMOKE_ENV: "1", APP_DIR_ENV: str(tmp_path)},
        timeout=SMOKE_TIMEOUT_SECONDS,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "data" / "logs").is_dir()  # nothing went to the real app folders
