import os
import shutil
from pathlib import Path

import pytest
from conftest import load_fixture
from test_output import NOW, azahar_setup, edited_for, make, tree_bytes
from test_session import new_session
from test_sources import AZAHAR_PATH, fill

from dq7tt import output
from dq7tt.apppaths import AppPaths
from dq7tt.constants import CHECKSUM_OFFSET, SAVE_FILENAMES, SAVE_SIZE
from dq7tt.errors import AzaharReplaceError, OutputExistsError, SessionError
from dq7tt.output import put_into_azahar, write_source
from dq7tt.savefile import SlotRole
from dq7tt.session import Target
from dq7tt.sources import open_source

EMULATOR_USER = "user"
OTHER_EMULATOR = "other emulator"


def _refused_untouched(edited: Path, target: Path, paths: AppPaths) -> None:
    before = tree_bytes(target)
    with pytest.raises(SessionError, match="not a Dragon Quest VII save|not readable"):
        put_into_azahar(edited, target, paths, NOW)
    assert tree_bytes(target) == before
    assert not paths.backups_dir.exists()


def test_put_into_azahar_refuses_a_folder_of_junk(tmp_path: Path) -> None:
    edited, target, paths = azahar_setup(tmp_path)
    for name in SAVE_FILENAMES[:2]:
        (edited / name).write_bytes(os.urandom(SAVE_SIZE))
    _refused_untouched(edited, target, paths)


def test_put_into_azahar_refuses_one_junk_save_among_good_ones(tmp_path: Path) -> None:
    edited, target, paths = azahar_setup(tmp_path)
    (edited / SAVE_FILENAMES[1]).write_bytes(b"not a save")
    _refused_untouched(edited, target, paths)


def test_put_into_azahar_refuses_a_bad_checksum(tmp_path: Path) -> None:
    edited, target, paths = azahar_setup(tmp_path)
    data = bytearray(load_fixture("us_postgame", 1))
    data[CHECKSUM_OFFSET] ^= 1
    (edited / SAVE_FILENAMES[1]).write_bytes(bytes(data))
    _refused_untouched(edited, target, paths)


def test_out_inside_the_emulator_tree_is_refused(tmp_path: Path) -> None:
    src, paths = make(tmp_path, AZAHAR_PATH)
    elsewhere = tmp_path / EMULATOR_USER / "nand" / "edited"
    with pytest.raises(OutputExistsError):
        write_source(src, edited_for(src), paths, NOW, out_dir=elsewhere)
    assert not elsewhere.exists()
    assert not paths.backups_dir.exists()


def test_out_inside_another_open_emulator_tree_is_refused(tmp_path: Path) -> None:
    session = new_session(tmp_path)
    plain = session.open(fill(tmp_path / "plain" / "saves"))
    session.open(fill(tmp_path / OTHER_EMULATOR / AZAHAR_PATH))
    session.remove(Target(plain, SlotRole.LOG_1), 0)
    inside = tmp_path / OTHER_EMULATOR / EMULATOR_USER / "edited"
    with pytest.raises(OutputExistsError):
        session.write(plain, inside)
    assert not inside.exists()
    assert session.write(plain, tmp_path / "fine").is_dir()


# Putting saves into Azahar is all or nothing


def _fail_replace_of(monkeypatch: pytest.MonkeyPatch, dst: Path) -> None:
    real_replace = os.replace

    def failing(src: object, target: object) -> None:
        if Path(target) == dst:
            raise OSError(13, "Permission denied")
        real_replace(src, target)

    monkeypatch.setattr(output.os, "replace", failing)


def test_put_into_azahar_restores_on_mid_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    edited, target, paths = azahar_setup(tmp_path)
    before = tree_bytes(target)
    _fail_replace_of(monkeypatch, target / SAVE_FILENAMES[1])
    with pytest.raises(AzaharReplaceError) as caught:
        put_into_azahar(edited, target, paths, NOW)
    assert tree_bytes(target) == before
    assert caught.value.restored
    (zip_path,) = paths.backups_dir.glob("*.zip")
    assert caught.value.backup == zip_path


def test_put_into_azahar_leaves_azahar_alone_when_a_copy_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    edited, target, paths = azahar_setup(tmp_path)
    before = tree_bytes(target)
    real_copy = shutil.copyfile
    calls: list[Path] = []

    def failing(src: Path, dst: Path, **kwargs: object) -> object:
        calls.append(Path(dst))
        if len(calls) == 2:
            raise OSError(28, "No space left on device")
        return real_copy(src, dst, **kwargs)

    monkeypatch.setattr(shutil, "copyfile", failing)
    with pytest.raises(AzaharReplaceError) as caught:
        put_into_azahar(edited, target, paths, NOW)
    assert tree_bytes(target) == before  # no temp files left behind either
    assert caught.value.restored


def test_put_into_azahar_says_so_when_it_cannot_put_the_old_save_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    edited, target, paths = azahar_setup(tmp_path)
    _fail_replace_of(monkeypatch, target / SAVE_FILENAMES[1])
    monkeypatch.setattr(output, "_restore_from_backup", lambda *args: False)
    with pytest.raises(AzaharReplaceError, match="Restore it from the backup") as caught:
        put_into_azahar(edited, target, paths, NOW)
    assert not caught.value.restored


def test_write_source_can_skip_the_backup(tmp_path: Path) -> None:
    edited, target, paths = azahar_setup(tmp_path)
    source = open_source(target, paths.work_dir)
    out = write_source(source, {}, paths, NOW, out_dir=tmp_path / "staged", backup=False)
    assert tree_bytes(out) == tree_bytes(target)
    assert not paths.backups_dir.exists()


def test_restore_from_backup_cleans_its_temp_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    edited, target, paths = azahar_setup(tmp_path)
    source = open_source(target, paths.work_dir)
    zip_path = output.backup_source(source, paths, NOW)
    _fail_replace_of(monkeypatch, target / SAVE_FILENAMES[0])
    assert not output._restore_from_backup(zip_path, target, [SAVE_FILENAMES[0]])
    assert not (target / (SAVE_FILENAMES[0] + ".tmp")).exists()
