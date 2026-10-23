"""The Android profile: one-step Save into Azahar, its labels, and the device wording."""

import shutil
from pathlib import Path

import pytest
from model_helpers import (
    AZAHAR_PATH,
    US_SET,
    confirm,
    fill,
    new_model,
    no_recycle_bin,  # noqa: F401 (an autouse fixture)
    notices,
    us_save,
)
from test_session import ticking_clock

from dq7tt import output
from dq7tt.apppaths import AppPaths
from dq7tt.constants import SAVE_FILENAMES
from dq7tt.savefile import SaveFile, SlotRole
from dq7tt_gui.device_profile import ANDROID_PROFILE, DESKTOP_PROFILE, Platform
from dq7tt_gui.model import AppModel
from dq7tt_gui.viewmodels import NoticeKind, PaneSide

LEFT, RIGHT = PaneSide.LEFT, PaneSide.RIGHT
SAVE_INTO_TEXT = (
    "Close the game in Azahar first. Azahar's current save is backed up before it is replaced."
)
QUICK_TEXT = (
    "This is the quick save (a suspended game). Resuming it may overwrite or ignore changes "
    "made here. Edit it anyway?"
)
LOG3_AFTER = 22


def android_model(tmp_path: Path) -> AppModel:
    return AppModel(
        AppPaths.under(tmp_path / "app"), profile=ANDROID_PROFILE, clock=ticking_clock()
    )


def backups(tmp_path: Path) -> list[Path]:
    folder = tmp_path / "app" / "data" / "backups"
    return sorted(folder.glob("*.zip")) if folder.exists() else []


def work_entries(tmp_path: Path) -> list[Path]:
    folder = tmp_path / "app" / "data" / "work"
    return sorted(folder.iterdir()) if folder.exists() else []


def tree(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}


def edited_azahar(tmp_path: Path, model: AppModel) -> Path:
    azahar = fill(tmp_path / AZAHAR_PATH, US_SET)
    model.open_left(azahar)
    model.pick_log(LEFT, SlotRole.LOG_3)
    model.toggle_row(LEFT, 0)
    model.remove_selected(confirmed=True)
    assert model.has_unwritten()
    return azahar


def test_profiles() -> None:
    assert DESKTOP_PROFILE.platform is Platform.DESKTOP
    assert not DESKTOP_PROFILE.one_step_azahar
    assert DESKTOP_PROFILE.can_open_files
    assert DESKTOP_PROFILE.device_word == "this PC"
    assert ANDROID_PROFILE.platform is Platform.ANDROID
    assert ANDROID_PROFILE.one_step_azahar
    assert not ANDROID_PROFILE.can_open_files
    assert ANDROID_PROFILE.device_word == "this device"


def test_desktop_write_unchanged(tmp_path: Path) -> None:
    model = new_model(tmp_path)
    assert model.profile is DESKTOP_PROFILE
    azahar = edited_azahar(tmp_path, model)
    old = (azahar / SAVE_FILENAMES[3]).read_bytes()
    assert model.toolbar().write_label == "Write changes"
    offer = confirm(model.write(LEFT))
    assert (offer.ok_label, offer.cancel_label) == ("Put into Azahar", "Not now")
    assert (azahar / SAVE_FILENAMES[3]).read_bytes() == old
    notices(offer.on_ok())
    assert len(backups(tmp_path)) == 2


def test_android_write_azahar_asks_once_then_saves_into_azahar(tmp_path: Path) -> None:
    model = android_model(tmp_path)
    azahar = edited_azahar(tmp_path, model)
    original = tree(azahar)
    ask = confirm(model.write(LEFT))
    assert (ask.title, ask.text) == ("Save into Azahar?", SAVE_INTO_TEXT)
    assert (ask.ok_label, ask.cancel_label) == ("Save", "Not now")
    assert ask.notices == ()
    assert tree(azahar) == original  # nothing happens before the yes
    assert backups(tmp_path) == []
    assert model.has_unwritten()
    result = notices(ask.on_ok())
    (zip_path,) = backups(tmp_path)  # one backup per save
    assert [(n.kind, n.text) for n in result] == [
        (
            NoticeKind.INFO,
            f"Saved into Azahar. The save it replaced is backed up in {zip_path.name}.",
        )
    ]
    assert SaveFile.load(azahar / SAVE_FILENAMES[3]).received.count == LOG3_AFTER
    assert tree(azahar) != original
    assert work_entries(tmp_path) == []
    assert not model.has_unwritten()
    assert not model.left().can_put_into_azahar
    assert not model.toolbar().can_write
    assert not (tmp_path / "app" / "edited").exists()


def test_android_write_failure_keeps_azahar_whole_and_offers_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = android_model(tmp_path)
    azahar = edited_azahar(tmp_path, model)
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
    result = notices(confirm(model.write(LEFT)).on_ok())
    assert tree(azahar) == original
    (zip_path,) = backups(tmp_path)
    assert [n.kind for n in result] == [NoticeKind.ERROR]
    assert zip_path.name in result[0].text
    assert "—" not in result[0].text
    assert model.left().can_put_into_azahar
    assert model.toolbar().can_write
    assert model.toolbar().write_label == "Save into Azahar"
    assert model.write_sides() == [LEFT]

    monkeypatch.setattr(shutil, "copyfile", real_copy)
    again = confirm(model.write(LEFT))
    assert again.title == "Save into Azahar?"
    result = notices(again.on_ok())
    assert [n.kind for n in result] == [NoticeKind.INFO]
    assert SaveFile.load(azahar / SAVE_FILENAMES[3]).received.count == LOG3_AFTER
    assert len(backups(tmp_path)) == 2  # one per attempt that reached Azahar
    assert work_entries(tmp_path) == []
    assert not model.left().can_put_into_azahar
    assert not model.toolbar().can_write


def test_android_write_label(tmp_path: Path) -> None:
    model = android_model(tmp_path)
    assert model.toolbar().write_label == "Write changes"
    edited_azahar(tmp_path, model)
    assert model.toolbar().write_label == "Save into Azahar"
    other = android_model(tmp_path / "other")
    other.open_left(us_save(tmp_path / "other"))
    other.toggle_row(LEFT, 0)
    other.remove_selected(confirmed=True)
    assert other.toolbar().write_label == "Write changes"


def test_android_non_azahar_writes_sibling(tmp_path: Path) -> None:
    model = android_model(tmp_path)
    save = us_save(tmp_path)
    model.open_left(save)
    model.toggle_row(LEFT, 0)
    model.remove_selected(confirmed=True)
    before = set(save.parent.iterdir())
    result = notices(model.write(LEFT))
    assert [n.kind for n in result] == [NoticeKind.INFO, NoticeKind.INFO]
    (new,) = set(save.parent.iterdir()) - before
    assert new.is_dir()
    assert not model.has_unwritten()


def test_empty_text_device_word(tmp_path: Path) -> None:
    assert new_model(tmp_path).empty_text() == "Open a save or find saves on this PC"
    assert android_model(tmp_path).empty_text() == "Open a save or find saves on this device"


def test_quick_save_confirm_still_first_on_android(tmp_path: Path) -> None:
    model = android_model(tmp_path)
    azahar = fill(tmp_path / AZAHAR_PATH, US_SET)
    original = tree(azahar)
    model.open_left(azahar)
    model.pick_log(LEFT, SlotRole.QUICK_SAVE)
    model.toggle_row(LEFT, 0)
    ask = confirm(model.remove_selected())
    assert ask.text == QUICK_TEXT
    assert notices(ask.on_ok()) == []
    save_ask = confirm(model.write(LEFT))
    assert save_ask.title == "Save into Azahar?"
    assert tree(azahar) == original


def test_android_save_into_azahar_twice_saves_once(tmp_path: Path) -> None:
    model = android_model(tmp_path)
    edited_azahar(tmp_path, model)
    ask = confirm(model.write(LEFT))
    notices(ask.on_ok())
    result = notices(ask.on_ok())  # a second tap on the same question
    assert [(n.kind, n.text) for n in result] == [
        (NoticeKind.ERROR, "There are no changes to write.")
    ]
    assert len(backups(tmp_path)) == 1


def failed_save_into_azahar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[AppModel, Path, dict[str, bytes]]:
    """An Android model whose Save into Azahar failed on the second file."""
    model = android_model(tmp_path)
    azahar = edited_azahar(tmp_path, model)
    original = tree(azahar)
    real_copy = shutil.copyfile
    calls: list[Path] = []

    def failing_copy(src: Path, dst: Path, **kwargs: object) -> object:
        if Path(dst).parent == azahar:
            calls.append(Path(dst))
            if len(calls) == 2:
                raise OSError(28, "No space left on device")
        return real_copy(src, dst, **kwargs)

    monkeypatch.setattr(shutil, "copyfile", failing_copy)
    result = notices(confirm(model.write(LEFT)).on_ok())
    assert [n.kind for n in result] == [NoticeKind.ERROR]
    monkeypatch.setattr(shutil, "copyfile", real_copy)
    return model, azahar, original


def test_android_failed_save_counts_as_unwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model, _, _ = failed_save_into_azahar(tmp_path, monkeypatch)
    assert model.has_unwritten()
    notices(confirm(model.write(LEFT)).on_ok())
    assert not model.has_unwritten()


def test_android_closing_after_a_failed_save_asks_then_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model, azahar, original = failed_save_into_azahar(tmp_path, monkeypatch)
    assert work_entries(tmp_path) != []
    ask = confirm(model.close_left())
    assert ask.title == "Discard changes?"
    assert work_entries(tmp_path) != []
    assert notices(ask.on_ok()) == []
    assert work_entries(tmp_path) == []
    assert not model.has_unwritten()
    assert tree(azahar) == original


def test_android_opening_over_a_failed_save_asks_then_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model, _, _ = failed_save_into_azahar(tmp_path, monkeypatch)
    ask = confirm(model.open_left(us_save(tmp_path)))
    assert ask.title == "Discard changes?"
    assert notices(ask.on_ok()) == []
    assert work_entries(tmp_path) == []


def test_leftover_staging_folders_are_removed_at_start(tmp_path: Path) -> None:
    work = tmp_path / "app" / "data" / "work"
    leftover = work / "into-azahar-abc123" / "save"
    leftover.mkdir(parents=True)
    (leftover / "save000.bin").write_bytes(b"x")
    other = work / "unpacked zip"
    other.mkdir()
    android_model(tmp_path)
    assert work_entries(tmp_path) == [other]


def test_android_failed_staging_write_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = android_model(tmp_path)
    azahar = edited_azahar(tmp_path, model)
    original = tree(azahar)

    def failing_write(*args: object, **kwargs: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(output, "write_edited", failing_write)
    result = notices(confirm(model.write(LEFT)).on_ok())
    assert [n.kind for n in result] == [NoticeKind.ERROR]
    assert work_entries(tmp_path) == []
    assert model._staging == {}
    assert model.has_unwritten()
    assert tree(azahar) == original
    assert backups(tmp_path) == []


def test_android_label_for_azahar_and_another_save(tmp_path: Path) -> None:
    model = android_model(tmp_path)
    edited_azahar(tmp_path, model)
    model.open_right(us_save(tmp_path))
    model.toggle_row(RIGHT, 0)
    model.remove_selected(confirmed=True)
    assert model.toolbar().write_label == "Write changes to both saves"
    assert model.toolbar().short_label == "Write both"


def test_pane_put_label_names_the_one_step_save_on_android(tmp_path: Path) -> None:
    azahar = fill(tmp_path / AZAHAR_PATH, US_SET)
    android = android_model(tmp_path)
    android.open_left(azahar)
    assert android.left().put_label == "Save into Azahar"
    desktop = new_model(tmp_path / "pc")
    desktop.open_left(azahar)
    assert desktop.left().put_label == "Put into Azahar"


def test_android_find_saves_looks_in_internal_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = tmp_path / "storage"
    fill(storage / "Azahar" / AZAHAR_PATH.removeprefix("user/"), US_SET)
    monkeypatch.setenv("EXTERNAL_STORAGE", str(storage))
    found, problems = android_model(tmp_path).find_saves()
    assert problems == []
    assert [f.path for f in found] == [storage / "Azahar" / AZAHAR_PATH.removeprefix("user/")]
