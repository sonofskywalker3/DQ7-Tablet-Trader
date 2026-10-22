"""Shared setup for the window model tests: fixture saves in temporary folder trees."""

from pathlib import Path

import pytest
import send2trash
from test_session import CHECKPOINT_PATH, OTHER_CHECKPOINT_PATH, ticking_clock
from test_sources import AZAHAR_PATH, fill

from dq7tt.apppaths import AppPaths
from dq7tt_gui.model import AppModel
from dq7tt_gui.viewmodels import Confirm, Notice, NoticeKind

US_SET = "us_postgame"
PAL_SET = "pal_superkiefer"
JKSM_PATH = "sd/JKSM/User Saves/DRAGON QUEST VII/20261020-101500"
__all__ = ["AZAHAR_PATH", "CHECKPOINT_PATH", "OTHER_CHECKPOINT_PATH", "fill"]


@pytest.fixture(autouse=True)
def no_recycle_bin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bank deletes in these tests remove the file instead of filling the recycle bin."""
    monkeypatch.setattr(send2trash, "send2trash", lambda p: Path(p).unlink())


def new_model(tmp_path: Path) -> AppModel:
    return AppModel(AppPaths.under(tmp_path / "app"), clock=ticking_clock())


def us_save(tmp_path: Path) -> Path:
    return fill(tmp_path / CHECKPOINT_PATH, US_SET)


def pal_save(tmp_path: Path) -> Path:
    return fill(tmp_path / OTHER_CHECKPOINT_PATH, PAL_SET)


def notices(result: object) -> list[Notice]:
    assert isinstance(result, list), result
    return result


def confirm(result: object) -> Confirm:
    assert isinstance(result, Confirm), result
    return result


def kinds(result: object) -> list[NoticeKind]:
    return [n.kind for n in notices(result)]


def errors(result: object) -> list[str]:
    return [n.text for n in notices(result) if n.kind is NoticeKind.ERROR]


def snapshot(model: AppModel) -> tuple[object, ...]:
    """Everything the window shows; equal snapshots mean nothing visible changed."""
    return (
        model.left(),
        model.right(),
        model.toolbar(),
        model.action_bar(),
        model.destinations(),
        model.has_unwritten(),
    )
