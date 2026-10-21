import os
from pathlib import Path

import pytest
from conftest import load_fixture
from test_output import NOW, azahar_setup, edited_for, make, tree_bytes
from test_session import new_session
from test_sources import AZAHAR_PATH, fill

from dq7tt.apppaths import AppPaths
from dq7tt.constants import CHECKSUM_OFFSET, SAVE_FILENAMES, SAVE_SIZE
from dq7tt.errors import OutputExistsError, SessionError
from dq7tt.output import put_into_azahar, write_source
from dq7tt.savefile import SlotRole
from dq7tt.session import Target

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
