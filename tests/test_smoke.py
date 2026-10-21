from pathlib import Path

import dq7tt

FIXTURES = Path(__file__).parent / "fixtures"
SETS = ("us_superkiefer", "us_postgame", "pal_superkiefer", "pal_postgame")
SAVE_SIZE = 20480


def test_package_imports() -> None:
    assert dq7tt.__version__ == "0.1.0"


def test_fixtures_present() -> None:
    files = [FIXTURES / s / f"save00{i}.bin" for s in SETS for i in range(4)]
    assert len(files) == 16
    for f in files:
        assert f.stat().st_size == SAVE_SIZE, f
