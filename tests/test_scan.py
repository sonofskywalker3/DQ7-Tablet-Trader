import logging
import os
import shutil
from pathlib import Path

import pytest
from test_sources import AZAHAR_PATH, fill, japanese_bytes

import dq7tt.scan as scan_module
from dq7tt.constants import SAVE_FILENAMES
from dq7tt.scan import (
    ANDROID_EMULATOR_FOLDERS,
    android_roots,
    default_roots,
    find_azahar_save,
    scan,
)
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


def test_android_roots_order_and_dedup(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    (storage / "Azahar").mkdir(parents=True)
    (storage / "citra-emu").mkdir()
    remembered = tmp_path / "picked"
    remembered.mkdir()
    sd = tmp_path / "sd"
    sd.mkdir()
    assert "lime3ds-emu" in ANDROID_EMULATOR_FOLDERS
    roots = android_roots(storage, remembered, [sd, storage / "Azahar", sd])
    assert roots == [remembered, storage / "Azahar", storage / "citra-emu", sd]
    assert android_roots(storage, None, []) == [storage / "Azahar", storage / "citra-emu"]


def user_folder(base: Path) -> Path:
    return base / "Azahar"


def azahar_save(base: Path) -> Path:
    return fill(user_folder(base) / AZAHAR_PATH.removeprefix("user/"))


def test_find_azahar_save_from_user_folder(tmp_path: Path) -> None:
    azahar_save(tmp_path)
    found = find_azahar_save(user_folder(tmp_path), tmp_path / "work")
    assert found is not None and found.kind is SourceKind.AZAHAR


def test_find_azahar_save_from_sdmc(tmp_path: Path) -> None:
    azahar_save(tmp_path)
    found = find_azahar_save(user_folder(tmp_path) / "sdmc", tmp_path / "work")
    assert found is not None and found.kind is SourceKind.AZAHAR


def test_find_azahar_save_from_save_folder_itself(tmp_path: Path) -> None:
    save = azahar_save(tmp_path)
    for picked in (save, save.parents[3], save.parents[1]):
        found = find_azahar_save(picked, tmp_path / "work")
        assert found is not None and found.save_dir == save


def test_find_azahar_save_none_in_unrelated_folder(tmp_path: Path) -> None:
    (tmp_path / "Downloads").mkdir()
    assert find_azahar_save(tmp_path / "Downloads", tmp_path / "work") is None
    assert find_azahar_save(tmp_path / "missing", tmp_path / "work") is None


def test_find_azahar_save_japanese_save_not_offered(tmp_path: Path) -> None:
    save = user_folder(tmp_path) / AZAHAR_PATH.removeprefix("user/")
    save.mkdir(parents=True)
    for name in SAVE_FILENAMES:
        (save / name).write_bytes(japanese_bytes())
    assert find_azahar_save(save, tmp_path / "work") is None
    assert find_azahar_save(user_folder(tmp_path), tmp_path / "work") is None


def test_find_azahar_save_ignores_checkpoint_and_jksm(world: Path) -> None:
    assert find_azahar_save(world / "sd", world / "work") is None


def test_find_azahar_save_several_returns_freshest(tmp_path: Path) -> None:
    us = azahar_save(tmp_path)
    eu = fill(us.parents[2] / "0018f000/data/00000001")
    stamp(us, 1000)
    stamp(eu, 5000)
    found = find_azahar_save(user_folder(tmp_path), tmp_path / "work")
    assert found is not None and found.save_dir == eu


def test_find_azahar_save_empty_user_folder_ancestor(tmp_path: Path) -> None:
    (user_folder(tmp_path) / "sdmc/Nintendo 3DS/x").mkdir(parents=True)
    assert find_azahar_save(user_folder(tmp_path) / "sdmc/Nintendo 3DS/x", tmp_path / "w") is None


def test_android_volumes_skips_internal_storage_links(tmp_path: Path) -> None:
    for name in ("emulated", "self", "1A2B-3C4D", ".hidden"):
        (tmp_path / name).mkdir()
    assert scan_module.android_volumes(tmp_path) == [tmp_path / "1A2B-3C4D"]
    assert scan_module.android_volumes(tmp_path / "missing") == []
