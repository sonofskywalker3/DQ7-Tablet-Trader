"""The Android build script: kept copies per architecture and its keystore hints."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SECRET = "not-a-real-password"


def build_android() -> ModuleType:
    pytest.importorskip("dotenv")
    spec = importlib.util.spec_from_file_location(
        "build_android", ROOT / "tools" / "build_android.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_each_architecture_keeps_its_own_apk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = build_android()
    monkeypatch.setattr(tool, "APK_KEEP_DIR", tmp_path / "android")
    built = tmp_path / "dq7-tablet-trader.apk"
    built.write_bytes(b"x86")
    test_copy = tool.named_copy(built, "x86_64", release=False)
    built.write_bytes(b"arm")
    release_copy = tool.named_copy(built, "arm64-v8a", release=True)
    assert test_copy.name == "dq7-tablet-trader-x86_64.apk"
    assert release_copy.name == "dq7-tablet-trader-arm64-v8a-release.apk"
    assert test_copy.read_bytes() == b"x86"
    assert release_copy.read_bytes() == b"arm"


def test_make_keystore_with_a_keystore_but_no_passwords_says_what_to_do(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = build_android()
    keystore = tmp_path / "release.jks"
    keystore.write_bytes(b"key")
    env = tmp_path / ".env"
    env.write_text(f"DQ7TT_KEYSTORE={keystore}\nDQ7TT_KEY_PASSWORD={SECRET}\n", encoding="utf-8")
    monkeypatch.setattr(tool, "DEFAULT_KEYSTORE", keystore)
    monkeypatch.setattr(tool, "ENV_FILE", env)
    with pytest.raises(tool.BuildError) as caught:
        tool.make_keystore()
    message = str(caught.value)
    assert "DQ7TT_KEYSTORE_PASSWORD" in message and "DQ7TT_KEY_ALIAS" in message
    assert "already exists" in message and "Do not make a new key" in message
    assert "run --make-keystore first" not in message
    assert SECRET not in message
    assert keystore.read_bytes() == b"key"  # never touched


def test_release_build_without_passwords_points_back_to_the_existing_keystore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = build_android()
    keystore = tmp_path / "release.jks"
    keystore.write_bytes(b"key")
    monkeypatch.setattr(tool, "DEFAULT_KEYSTORE", keystore)
    monkeypatch.setattr(tool, "ENV_FILE", tmp_path / ".env")
    for name in tool.SIGNING_VARS:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(tool.BuildError, match="already exists"):
        tool.signing_values()
    keystore.unlink()
    with pytest.raises(tool.BuildError, match="run --make-keystore first"):
        tool.signing_values()
