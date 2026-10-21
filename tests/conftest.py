from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_SETS = ("us_superkiefer", "us_postgame", "pal_superkiefer", "pal_postgame")
SLOTS = range(4)

ALL_SAVES: list[Path] = [FIXTURES / s / f"save{i:03d}.bin" for s in FIXTURE_SETS for i in SLOTS]


def load_fixture(set_name: str, slot: int) -> bytes:
    """Return the bytes of one fixture save (read-only input)."""
    return (FIXTURES / set_name / f"save{slot:03d}.bin").read_bytes()


@pytest.fixture(params=ALL_SAVES, ids=lambda p: f"{p.parent.name}/{p.name}")
def save_bytes(request: pytest.FixtureRequest) -> bytes:
    """Every fixture save in turn."""
    return request.param.read_bytes()


@pytest.fixture(autouse=True)
def isolated_app_folders(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Command line runs without --app-dir must never touch the real app folders."""
    from dq7tt.apppaths import AppPaths

    root = tmp_path_factory.mktemp("default_app")
    monkeypatch.setattr(AppPaths, "default", classmethod(lambda cls: cls.under(root)))
