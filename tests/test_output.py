import os
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from conftest import load_fixture
from test_sources import AZAHAR_PATH, fill

import dq7tt.output as output
from dq7tt.apppaths import AppPaths
from dq7tt.constants import SAVE_FILENAMES
from dq7tt.errors import OutputExistsError, SaveIOError, SessionError
from dq7tt.folder import TEMP_DIR_PREFIX, SaveFolder
from dq7tt.output import (
    backup_source,
    clean_stale_staging,
    output_path,
    put_into_azahar,
    write_source,
)
from dq7tt.savefile import SaveFile, SlotRole
from dq7tt.sources import SaveSource, SourceKind, open_source

NOW = datetime(2026, 10, 21, 13, 5, 9)
CHECKPOINT_PATH = "sd/3ds/Checkpoint/saves/0x18EF0 DRAGON QUEST VII/20261020-101500"
JKSM_PATH = "sd/JKSM/User Saves/DRAGON QUEST VII/backup1"
MESSY_LABEL = 'Zip: a<b>"c|d?*e\x01 '
SECONDS_PER_TWO_HOURS = 7200
EDITED_SET = "pal_superkiefer"


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def make(tmp_path: Path, rel: str) -> tuple[SaveSource, AppPaths]:
    paths = AppPaths.under(tmp_path / "app")
    folder = fill(tmp_path / rel)
    return open_source(folder, paths.work_dir), paths


def edited_for(source: SaveSource) -> dict[SlotRole, SaveFile]:
    return dict(SaveFolder.open(source.save_dir).files)


def test_output_path_checkpoint_and_jksm(tmp_path: Path) -> None:
    for rel in (CHECKPOINT_PATH, JKSM_PATH):
        src, paths = make(tmp_path, rel)
        out = output_path(src, paths, NOW)
        assert out == src.save_dir.parent / f"{src.save_dir.name} edited 20261021-130509"


def test_output_path_folder(tmp_path: Path) -> None:
    src, paths = make(tmp_path, "plain/mysaves")
    assert src.kind is SourceKind.FOLDER
    assert output_path(src, paths, NOW) == tmp_path / "plain" / "mysaves edited 20261021-130509"


def test_output_path_azahar_is_outside_the_emulator_tree(tmp_path: Path) -> None:
    src, paths = make(tmp_path, AZAHAR_PATH)
    out = output_path(src, paths, NOW)
    assert out == paths.edited_dir / "2026-10-21 130509 Azahar save (US)"
    assert not out.resolve().is_relative_to(src.save_dir.resolve())


def test_output_path_file(tmp_path: Path) -> None:
    paths = AppPaths.under(tmp_path / "app")
    folder = fill(tmp_path / "loose")
    src = open_source(folder / SAVE_FILENAMES[1], paths.work_dir)
    assert src.kind is SourceKind.FILE
    assert output_path(src, paths, NOW) == folder / "save001 edited 20261021-130509.bin"


def test_output_path_zip(tmp_path: Path) -> None:
    paths = AppPaths.under(tmp_path / "app")
    folder = fill(tmp_path / "z")
    archive = tmp_path / "my saves.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for name in SAVE_FILENAMES:
            z.write(folder / name, name)
    src = open_source(archive, paths.work_dir)
    assert src.kind is SourceKind.ZIP
    assert output_path(src, paths, NOW) == paths.edited_dir / "2026-10-21 130509 Zip_ my saves"


def test_backup_contains_source_files_byte_for_byte(tmp_path: Path) -> None:
    src, paths = make(tmp_path, CHECKPOINT_PATH)
    (src.save_dir / "system.bin").write_bytes(b"sys")
    before = tree_bytes(src.save_dir)
    zip_path = backup_source(src, paths, NOW)
    assert zip_path.parent == paths.backups_dir
    assert zip_path.name == "2026-10-21 130509 Checkpoint backup 20261020-101500 (US).zip"
    with zipfile.ZipFile(zip_path) as z:
        assert {i.filename for i in z.infolist()} == set(before)
        assert all(i.compress_type == zipfile.ZIP_DEFLATED for i in z.infolist())
        assert {n: z.read(n) for n in z.namelist()} == before
    assert tree_bytes(src.save_dir) == before


def test_backup_name_replaces_invalid_characters(tmp_path: Path) -> None:
    src, paths = make(tmp_path, "plain/x")
    src = SaveSource(src.kind, src.path, src.save_dir, src.region, MESSY_LABEL)
    assert backup_source(src, paths, NOW).name == "2026-10-21 130509 Zip_ a_b__c_d__e_.zip"


def test_backup_file_source_is_only_that_file(tmp_path: Path) -> None:
    paths = AppPaths.under(tmp_path / "app")
    folder = fill(tmp_path / "loose")
    src = open_source(folder / SAVE_FILENAMES[2], paths.work_dir)
    zip_path = backup_source(src, paths, NOW)
    with zipfile.ZipFile(zip_path) as z:
        assert z.namelist() == [SAVE_FILENAMES[2]]
        assert z.read(SAVE_FILENAMES[2]) == (folder / SAVE_FILENAMES[2]).read_bytes()


def test_backup_never_overwrites_an_existing_backup(tmp_path: Path) -> None:
    src, paths = make(tmp_path, CHECKPOINT_PATH)
    first = backup_source(src, paths, NOW)
    second = backup_source(src, paths, NOW)
    assert first != second
    assert first.exists() and second.exists()


def test_write_source_backs_up_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src, paths = make(tmp_path, CHECKPOINT_PATH)
    seen: list[bool] = []

    def fake(*args: object, **kwargs: object) -> None:
        seen.append(any(paths.backups_dir.glob("*.zip")))

    monkeypatch.setattr(output, "write_edited", fake)
    write_source(src, edited_for(src), paths, NOW)
    assert seen == [True]


def test_write_source_checkpoint_writes_sibling_and_leaves_input(tmp_path: Path) -> None:
    src, paths = make(tmp_path, CHECKPOINT_PATH)
    before = tree_bytes(src.save_dir)
    out = write_source(src, edited_for(src), paths, NOW)
    assert out == output_path(src, paths, NOW)
    assert tree_bytes(out) == before
    assert tree_bytes(src.save_dir) == before
    assert len(list(paths.backups_dir.glob("*.zip"))) == 1


def test_write_source_azahar_lands_in_documents_folder(tmp_path: Path) -> None:
    src, paths = make(tmp_path, AZAHAR_PATH)
    before = tree_bytes(src.save_dir)
    out = write_source(src, edited_for(src), paths, NOW)
    assert out.parent == paths.edited_dir
    assert tree_bytes(out) == before
    assert tree_bytes(src.save_dir) == before


def test_write_source_file_writes_one_sibling_file(tmp_path: Path) -> None:
    paths = AppPaths.under(tmp_path / "app")
    folder = fill(tmp_path / "loose")
    src = open_source(folder / SAVE_FILENAMES[1], paths.work_dir)
    before = tree_bytes(folder)
    edited = {SlotRole.LOG_1: SaveFile.load(folder / SAVE_FILENAMES[1])}
    out = write_source(src, edited, paths, NOW)
    assert out == folder / "save001 edited 20261021-130509.bin"
    after = tree_bytes(folder)
    assert set(after) - set(before) == {out.name}
    assert {k: v for k, v in after.items() if k != out.name} == before
    assert not list(folder.glob("*.tmp"))
    assert list(paths.backups_dir.glob("*.zip"))


def test_write_source_file_refuses_when_output_exists(tmp_path: Path) -> None:
    paths = AppPaths.under(tmp_path / "app")
    folder = fill(tmp_path / "loose")
    src = open_source(folder / SAVE_FILENAMES[1], paths.work_dir)
    edited = {SlotRole.LOG_1: SaveFile.load(folder / SAVE_FILENAMES[1])}
    output_path(src, paths, NOW).write_bytes(b"mine")
    with pytest.raises(OutputExistsError):
        write_source(src, edited, paths, NOW)
    assert output_path(src, paths, NOW).read_bytes() == b"mine"


def test_write_source_file_needs_its_own_save(tmp_path: Path) -> None:
    paths = AppPaths.under(tmp_path / "app")
    folder = fill(tmp_path / "loose")
    src = open_source(folder / SAVE_FILENAMES[1], paths.work_dir)
    with pytest.raises(SessionError):
        write_source(src, {}, paths, NOW)


def azahar_setup(tmp_path: Path) -> tuple[Path, Path, AppPaths]:
    paths = AppPaths.under(tmp_path / "app")
    target = fill(tmp_path / AZAHAR_PATH)
    edited = tmp_path / "out" / "edited"
    edited.mkdir(parents=True)
    for slot, name in enumerate(SAVE_FILENAMES[:2]):
        (edited / name).write_bytes(load_fixture(EDITED_SET, slot))
    return edited, target, paths


def test_put_into_azahar_backs_up_then_replaces(tmp_path: Path) -> None:
    edited, target, paths = azahar_setup(tmp_path)
    (target / "extra.bin").write_bytes(b"keep")
    (edited / "system.bin").write_bytes(b"x")
    (target / "system.bin").write_bytes(b"old")
    before = tree_bytes(target)
    zip_path = put_into_azahar(edited, target, paths, NOW)
    assert zip_path.parent == paths.backups_dir
    with zipfile.ZipFile(zip_path) as z:
        assert z.read(SAVE_FILENAMES[0]) == before[SAVE_FILENAMES[0]]
        assert z.read("system.bin") == b"old"
    after = tree_bytes(target)
    assert after[SAVE_FILENAMES[0]] == load_fixture(EDITED_SET, 0)
    assert after[SAVE_FILENAMES[1]] == load_fixture(EDITED_SET, 1)
    assert after["system.bin"] == b"x"
    assert after["extra.bin"] == b"keep"
    assert after[SAVE_FILENAMES[2]] == before[SAVE_FILENAMES[2]]
    assert not list(target.glob("*.tmp"))


def test_put_into_azahar_refuses_edited_inside_target(tmp_path: Path) -> None:
    _, target, paths = azahar_setup(tmp_path)
    inside = target / "edited"
    inside.mkdir()
    (inside / SAVE_FILENAMES[0]).write_bytes(b"n")
    before = tree_bytes(target)
    with pytest.raises(SessionError):
        put_into_azahar(inside, target, paths, NOW)
    with pytest.raises(SessionError):
        put_into_azahar(target, target, paths, NOW)
    assert tree_bytes(target) == before
    assert not paths.backups_dir.exists()


def test_put_into_azahar_refuses_non_azahar_target(tmp_path: Path) -> None:
    edited, _, paths = azahar_setup(tmp_path)
    other = fill(tmp_path / "plain" / "saves")
    before = tree_bytes(other)
    with pytest.raises(SessionError):
        put_into_azahar(edited, other, paths, NOW)
    with pytest.raises(SessionError):
        put_into_azahar(edited, tmp_path / "missing", paths, NOW)
    assert tree_bytes(other) == before
    assert not paths.backups_dir.exists()


def test_put_into_azahar_refuses_when_target_file_missing(tmp_path: Path) -> None:
    edited, target, paths = azahar_setup(tmp_path)
    (target / SAVE_FILENAMES[1]).unlink()
    before = tree_bytes(target)
    with pytest.raises(SessionError):
        put_into_azahar(edited, target, paths, NOW)
    assert tree_bytes(target) == before
    assert not paths.backups_dir.exists()


def test_put_into_azahar_refuses_empty_edited(tmp_path: Path) -> None:
    edited, target, paths = azahar_setup(tmp_path)
    for f in edited.iterdir():
        f.unlink()
    with pytest.raises(SessionError):
        put_into_azahar(edited, target, paths, NOW)


def test_clean_stale_staging_removes_only_old_tool_folders(tmp_path: Path) -> None:
    old = tmp_path / f"{TEMP_DIR_PREFIX}abc"
    fresh = tmp_path / f"{TEMP_DIR_PREFIX}new"
    other = tmp_path / "mine"
    for d in (old, fresh, other):
        d.mkdir()
        (d / "f").write_bytes(b"1")
    (tmp_path / f"{TEMP_DIR_PREFIX}file").write_bytes(b"x")
    long_ago = time.time() - SECONDS_PER_TWO_HOURS
    for d in (old, other):
        os.utime(d, (long_ago, long_ago))
    assert clean_stale_staging(tmp_path) == 1
    assert not old.exists()
    assert fresh.exists() and other.exists()
    assert (tmp_path / f"{TEMP_DIR_PREFIX}file").exists()


def test_clean_stale_staging_custom_limit_and_missing_parent(tmp_path: Path) -> None:
    (tmp_path / f"{TEMP_DIR_PREFIX}x").mkdir()
    assert clean_stale_staging(tmp_path / "nope") == 0
    assert clean_stale_staging(tmp_path, timedelta(seconds=-1)) == 1


def make_zip_source(tmp_path: Path) -> tuple[SaveSource, AppPaths]:
    paths = AppPaths.under(tmp_path / "app")
    folder = fill(tmp_path / "z")
    archive = tmp_path / "my saves.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for name in SAVE_FILENAMES:
            z.write(folder / name, name)
    return open_source(archive, paths.work_dir), paths


def test_write_source_zip_end_to_end(tmp_path: Path) -> None:
    src, paths = make_zip_source(tmp_path)
    out = write_source(src, edited_for(src), paths, NOW)
    assert out.is_dir()
    assert out.parent == paths.edited_dir
    assert set(tree_bytes(out)) == set(SAVE_FILENAMES)


def test_write_source_azahar_end_to_end_has_saves(tmp_path: Path) -> None:
    src, paths = make(tmp_path, AZAHAR_PATH)
    out = write_source(src, edited_for(src), paths, NOW)
    assert out.is_dir()
    assert set(tree_bytes(out)) == set(SAVE_FILENAMES)


def test_refused_write_leaves_no_backup(tmp_path: Path) -> None:
    src, paths = make(tmp_path, CHECKPOINT_PATH)
    output_path(src, paths, NOW).mkdir()
    with pytest.raises(OutputExistsError):
        write_source(src, edited_for(src), paths, NOW)
    assert not paths.backups_dir.exists()


def test_put_into_azahar_failure_names_the_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    edited, target, paths = azahar_setup(tmp_path)

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(output.shutil, "copyfile", boom)
    with pytest.raises(SaveIOError) as info:
        put_into_azahar(edited, target, paths, NOW)
    backup = next(paths.backups_dir.glob("*.zip"))
    assert str(backup) in str(info.value)
