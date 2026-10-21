import logging
import os
import shutil
from pathlib import Path

import pytest
from test_sources import AZAHAR_PATH, fill

import dq7tt.scan as scan_module
from dq7tt.scan import default_roots, scan
from dq7tt.sources import SaveSource, SourceKind

DQ7_CHECKPOINT = "sd/3ds/Checkpoint/saves/0x18EF0 DRAGON QUEST VII"
BACKUP_NAMES = ("old", "new")


def stamp(folder: Path, when: int) -> None:
    for item in [*folder.iterdir(), folder]:
        os.utime(item, (when, when))


@pytest.fixture
def world(tmp_path: Path) -> Path:
    stamp(fill(tmp_path / "appdata/Azahar" / AZAHAR_PATH.removeprefix("user/")), 1000)
    stamp(fill(tmp_path / DQ7_CHECKPOINT / "old"), 2000)
    stamp(fill(tmp_path / DQ7_CHECKPOINT / "new"), 4000)
    stamp(fill(tmp_path / "sd/JKSM/User Saves/DRAGON QUEST VII/jk"), 3000)
    other = tmp_path / "sd/3ds/Checkpoint/saves/0x1234 Other Game/b1"
    other.mkdir(parents=True)
    (other / "game.sav").write_bytes(b"x" * 100)
    return tmp_path


def test_scan_finds_four_newest_first(world: Path) -> None:
    found = scan([world / "appdata/Azahar", world / "sd"], world / "work")
    assert [s.kind for s in found] == [
        SourceKind.CHECKPOINT,
        SourceKind.JKSM,
        SourceKind.CHECKPOINT,
        SourceKind.AZAHAR,
    ]
    assert [s.save_dir.name for s in found[:3]] == ["new", "jk", "old"]


def test_scan_skips_hidden_and_staging_and_other_lowids(world: Path) -> None:
    fill(world / "sd/3ds/Checkpoint/saves/.hidden/b")
    fill(world / "sd/3ds/Checkpoint/saves/.dq7tt-stage/b")
    azahar = world / "appdata/Azahar/sdmc/Nintendo 3DS" / ("0" * 32) / ("0" * 32)
    fill(azahar / "title/00040000/00112233/data/00000001")
    found = scan([world / "appdata/Azahar", world / "sd"], world / "work")
    assert len(found) == 4


def test_scan_depth_limit(world: Path) -> None:
    found = scan([world / "appdata/Azahar", world / "sd"], world / "work", max_depth=4)
    assert {s.kind for s in found} == {SourceKind.CHECKPOINT, SourceKind.JKSM}
    assert len(found) == 3


def test_scan_does_not_extract_zips(world: Path) -> None:
    (world / "sd/3ds/Checkpoint/saves/0x18EF0 DRAGON QUEST VII/z.zip").write_bytes(b"PK")
    scan([world / "sd"], world / "work")
    assert not (world / "work").exists()


def test_scan_missing_root_and_duplicates(world: Path) -> None:
    sd = world / "sd"
    found = scan([sd, sd, world / "nope"], world / "work")
    assert len(found) == 3


def test_scan_logs_skipped_folders(world: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="dq7tt.scan"):
        scan([world / "sd"], world / "work")
    assert any("Other Game" in r.getMessage() or "b1" in r.getMessage() for r in caplog.records)


def test_default_roots(tmp_path: Path) -> None:
    appdata = tmp_path / "Roaming"
    (appdata / "Azahar").mkdir(parents=True)
    (appdata / "Lime3DS").mkdir()
    drive = tmp_path / "E"
    drive.mkdir()
    roots = default_roots({"APPDATA": str(appdata)}, drives=[drive, tmp_path / "F"])
    assert roots == [appdata / "Azahar", appdata / "Lime3DS", drive]


def test_default_roots_without_appdata(tmp_path: Path) -> None:
    assert default_roots({}, drives=[]) == []


def test_scan_skips_a_folder_that_vanishes(
    world: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    real_try_open = scan_module._try_open

    def open_then_vanish(folder: Path, work_dir: Path) -> SaveSource | None:
        source = real_try_open(folder, work_dir)
        if folder.name == BACKUP_NAMES[0]:
            shutil.rmtree(folder)
        return source

    monkeypatch.setattr(scan_module, "_try_open", open_then_vanish)
    with caplog.at_level(logging.INFO, logger="dq7tt.scan"):
        found = scan([world / "appdata/Azahar", world / "sd"], world / "work")
    assert len(found) == 3
    assert all(s.save_dir.name != BACKUP_NAMES[0] for s in found)
    assert BACKUP_NAMES[0] in caplog.text
