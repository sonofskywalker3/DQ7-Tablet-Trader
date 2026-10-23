"""What Put into Azahar and Save into Azahar say when the replace fails or the save
cannot be read back afterwards."""

import shutil
from pathlib import Path

import pytest
from model_helpers import (
    confirm,
    new_model,
    no_recycle_bin,  # noqa: F401 (an autouse fixture)
    notices,
)
from test_model_android import android_model, backups, edited_azahar, tree

import dq7tt.session_core as session_module
from dq7tt import output
from dq7tt.constants import SAVE_FILENAMES
from dq7tt.errors import AzaharReplaceError, SaveIOError
from dq7tt.savefile import SaveFile
from dq7tt_gui.model import AppModel
from dq7tt_gui.viewmodels import NoticeKind, PaneSide

LEFT = PaneSide.LEFT
LOG3_AFTER = 22


def written_desktop(tmp_path: Path) -> tuple[AppModel, Path]:
    """A desktop model whose Azahar save is written and waiting to be put in."""
    model = new_model(tmp_path)
    azahar = edited_azahar(tmp_path, model)
    confirm(model.write(LEFT))  # Not now
    assert model.left().can_put_into_azahar
    return model, azahar


def unreadable(_source: object) -> None:
    raise SaveIOError("Could not read Azahar: busy")


def test_desktop_put_failure_names_the_backup_and_offers_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model, azahar = written_desktop(tmp_path)
    original = tree(azahar)
    real_copy = shutil.copyfile
    into_azahar: list[Path] = []

    def failing_copy(src: Path, dst: Path, **kwargs: object) -> object:
        if Path(dst).parent == azahar:
            into_azahar.append(Path(dst))
            if len(into_azahar) == 2:
                raise OSError(28, "No space left on device")
        return real_copy(src, dst, **kwargs)

    monkeypatch.setattr(shutil, "copyfile", failing_copy)
    result = notices(model.put_into_azahar(LEFT, confirmed=True))
    assert tree(azahar) == original
    zip_path = max(backups(tmp_path), key=lambda p: p.stat().st_mtime_ns)
    assert [n.kind for n in result] == [NoticeKind.ERROR]
    assert result[0].text == (
        "Could not put the edited save into Azahar, so its save was left as it was. The save "
        f"from before is backed up in {zip_path.name} in the backups folder. "
        "Try Put into Azahar again."
    )
    assert model.left().can_put_into_azahar


def test_desktop_put_that_cannot_restore_says_to_use_the_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model, _ = written_desktop(tmp_path)
    backup = tmp_path / "backups" / "Azahar-backup.zip"

    def broken(*_args: object) -> Path:
        raise AzaharReplaceError("half way", backup, restored=False)

    monkeypatch.setattr(output, "put_into_azahar", broken)
    result = notices(model.put_into_azahar(LEFT, confirmed=True))
    assert [(n.kind, n.text) for n in result] == [
        (
            NoticeKind.ERROR,
            "Could not put the edited save into Azahar, and its save could not be put back as "
            "it was. Restore it from the backup Azahar-backup.zip in the backups folder.",
        )
    ]


def test_desktop_put_that_cannot_be_read_back_says_it_is_in_azahar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model, azahar = written_desktop(tmp_path)
    monkeypatch.setattr(session_module, "load_saves", unreadable)
    result = notices(model.put_into_azahar(LEFT, confirmed=True))
    assert SaveFile.load(azahar / SAVE_FILENAMES[3]).received.count == LOG3_AFTER
    assert [n.kind for n in result] == [NoticeKind.INFO]
    assert result[0].text.startswith("The edited save is now in Azahar, but it could not be read")
    assert "backups folder" in result[0].text
    assert not model.left().can_put_into_azahar


def test_android_save_that_cannot_be_read_back_says_it_is_in_azahar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = android_model(tmp_path)
    azahar = edited_azahar(tmp_path, model)
    monkeypatch.setattr(session_module, "load_saves", unreadable)
    result = notices(confirm(model.write(LEFT)).on_ok())
    assert SaveFile.load(azahar / SAVE_FILENAMES[3]).received.count == LOG3_AFTER
    assert [n.kind for n in result] == [NoticeKind.INFO]
    assert result[0].text.startswith("Saved into Azahar, but it could not be read")
    assert not model.has_unwritten()
    assert not model.left().can_put_into_azahar
    assert not model.toolbar().can_write
