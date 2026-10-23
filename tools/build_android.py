"""Build the Android APK with `flet build apk`.

Run from the repo root:

    uv run python tools/build_android.py --arch x86_64              # emulator test build
    uv run python tools/build_android.py --arch arm64-v8a --release # signed build for the Thor
    uv run python tools/build_android.py --make-keystore            # once, before the first release

`flet build` always writes build/apk/dq7-tablet-trader.apk and empties that folder first, so
each build is also copied to build/android/ under a name that says its architecture (and
"-release" for a signed build). An x86_64 test build never replaces the Thor's APK.

The release signing key lives outside the repo (DEFAULT_KEYSTORE). Its passwords are kept in
the repo's .env, which git ignores. They reach `flet build` through environment variables, so
they never show up on a command line.
"""

import argparse
import logging
import os
import secrets
import shutil
import subprocess
from pathlib import Path

from dotenv import dotenv_values, set_key

logger = logging.getLogger("build_android")

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
APK_DIR = ROOT / "build" / "apk"
APK_GLOB = "*.apk"
# Kept between builds: one file per architecture and kind (see named_copy).
APK_KEEP_DIR = ROOT / "build" / "android"
APK_STEM = "dq7-tablet-trader"
RELEASE_SUFFIX = "-release"
# `flet build` would bundle the newest Python it knows (3.14); the app is developed and tested
# on the version in .python-version, so the APK carries that one too.
PYTHON_VERSION_FILE = ROOT / ".python-version"

ARCHES = ("x86_64", "arm64-v8a")
RELEASE_ARCH = "arm64-v8a"

KEYSTORE_VAR = "DQ7TT_KEYSTORE"
KEYSTORE_PASSWORD_VAR = "DQ7TT_KEYSTORE_PASSWORD"
KEY_ALIAS_VAR = "DQ7TT_KEY_ALIAS"
KEY_PASSWORD_VAR = "DQ7TT_KEY_PASSWORD"
SIGNING_VARS = (KEYSTORE_VAR, KEYSTORE_PASSWORD_VAR, KEY_ALIAS_VAR, KEY_PASSWORD_VAR)

# Where `flet build` reads the signing options from (see `flet build --help`).
FLET_SIGNING_ENV = {
    KEYSTORE_VAR: "FLET_ANDROID_SIGNING_KEY_STORE",
    KEYSTORE_PASSWORD_VAR: "FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD",
    KEY_ALIAS_VAR: "FLET_ANDROID_SIGNING_KEY_ALIAS",
    KEY_PASSWORD_VAR: "FLET_ANDROID_SIGNING_KEY_PASSWORD",
}

DEFAULT_KEYSTORE = Path.home() / ".dq7tt-android" / "release.jks"
DEFAULT_KEY_ALIAS = "dq7tablettrader"
KEY_ALGORITHM = "RSA"
KEY_SIZE = "4096"
KEY_VALIDITY_DAYS = "10000"
KEY_DNAME = "CN=DQ7 Tablet Trader, O=DQ7 Tablet Trader"
PASSWORD_BYTES = 32
# keytool reads passwords from these variables (its `:env` option), not from its arguments.
KEYTOOL_STORE_PASS_ENV = "DQ7TT_KEYTOOL_STOREPASS"
KEYTOOL_KEY_PASS_ENV = "DQ7TT_KEYTOOL_KEYPASS"

JAVA_ROOT = Path.home() / "java"
SDK_ROOT_VARS = ("ANDROID_HOME", "ANDROID_SDK_ROOT")
# Same search order as `flet build`: the variables, then Android Studio's folder, then its own.
SDK_ROOTS = (
    Path.home() / "AppData" / "Local" / "Android" / "Sdk",
    Path.home() / "Android" / "sdk",
)
KEYTOOL = "keytool.exe" if os.name == "nt" else "keytool"
APKSIGNER = "apksigner.bat" if os.name == "nt" else "apksigner"


class BuildError(RuntimeError):
    """The APK could not be built, signed or checked."""


def missing_values_hint(keystore: Path, missing: list[str]) -> str:
    """What to do when .env lacks signing values. Names the variables, never their values."""
    names = ", ".join(missing)
    if not keystore.exists():
        return f"{names} not set in {ENV_FILE}; run --make-keystore first"
    return (
        f"{names} not set in {ENV_FILE}, but the keystore {keystore} already exists. "
        f"Copy its passwords back into {ENV_FILE} (the names are in .env.example) from "
        "wherever you saved them. Do not make a new key: an APK signed with a different key "
        "will not install over one signed with this key. Only if those passwords are lost "
        "for good, move the old keystore somewhere else and run --make-keystore again; "
        "the app then has to be uninstalled before the new build will install."
    )


def signing_values() -> dict[str, str]:
    """The four signing variables from .env (the process environment wins)."""
    file_values = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    values: dict[str, str] = {}
    missing: list[str] = []
    for name in SIGNING_VARS:
        value = os.environ.get(name) or file_values.get(name)
        if value:
            values[name] = value
        else:
            missing.append(name)
    if missing:
        raise BuildError(missing_values_hint(DEFAULT_KEYSTORE, missing))
    if not Path(values[KEYSTORE_VAR]).is_file():
        raise BuildError(f"keystore not found: {values[KEYSTORE_VAR]}")
    return values


def find_keytool() -> Path:
    """keytool from JAVA_HOME, the JDK `flet build` installed, or PATH."""
    candidates: list[Path] = []
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidates.append(Path(java_home) / "bin" / KEYTOOL)
    if JAVA_ROOT.is_dir():
        candidates += sorted(JAVA_ROOT.glob(f"*/bin/{KEYTOOL}"), reverse=True)
    on_path = shutil.which(KEYTOOL)
    if on_path:
        candidates.append(Path(on_path))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise BuildError("keytool not found: install a JDK or run a first `flet build apk`")


def sdk_root() -> Path:
    """The Android SDK `flet build` uses."""
    for name in SDK_ROOT_VARS:
        value = os.environ.get(name)
        if value and Path(value).is_dir():
            return Path(value)
    for root in SDK_ROOTS:
        if root.is_dir():
            return root
    return SDK_ROOTS[-1]


def find_apksigner() -> Path:
    """apksigner from the newest Android build-tools."""
    found = sorted((sdk_root() / "build-tools").glob(f"*/{APKSIGNER}"), reverse=True)
    if not found:
        raise BuildError(f"apksigner not found under {sdk_root() / 'build-tools'}")
    return found[0]


def make_keystore() -> Path:
    """Create the release keystore and record its passwords in .env.

    Never overwrites: an existing keystore is left alone and returned as it is, provided .env
    still holds what a release build needs; otherwise the error says how to put it back.
    """
    keystore = DEFAULT_KEYSTORE
    if keystore.exists():
        file_values = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
        missing = [name for name in SIGNING_VARS if not file_values.get(name)]
        if missing:
            raise BuildError(missing_values_hint(keystore, missing))
        logger.info("keystore already exists, leaving it alone: %s", keystore)
        return keystore
    keystore.parent.mkdir(parents=True, exist_ok=True)
    # PKCS12 keystores use one password for the store and the key.
    password = secrets.token_urlsafe(PASSWORD_BYTES)
    env = {**os.environ, KEYTOOL_STORE_PASS_ENV: password, KEYTOOL_KEY_PASS_ENV: password}
    cmd = [
        str(find_keytool()), "-genkeypair",
        "-keystore", str(keystore), "-storetype", "PKCS12",
        "-alias", DEFAULT_KEY_ALIAS,
        "-keyalg", KEY_ALGORITHM, "-keysize", KEY_SIZE, "-validity", KEY_VALIDITY_DAYS,
        "-dname", KEY_DNAME,
        "-storepass:env", KEYTOOL_STORE_PASS_ENV, "-keypass:env", KEYTOOL_KEY_PASS_ENV,
    ]  # fmt: skip
    result = subprocess.run(cmd, env=env, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise BuildError(f"keytool failed: {result.stderr.strip()}")
    ENV_FILE.touch(exist_ok=True)
    for name, value in (
        (KEYSTORE_VAR, str(keystore)),
        (KEYSTORE_PASSWORD_VAR, password),
        (KEY_ALIAS_VAR, DEFAULT_KEY_ALIAS),
        (KEY_PASSWORD_VAR, password),
    ):
        set_key(ENV_FILE, name, value, quote_mode="never")
    logger.info("made keystore %s; passwords written to %s", keystore, ENV_FILE)
    return keystore


def python_version() -> str:
    """The Python version the app is developed on, e.g. "3.12"."""
    try:
        return PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise BuildError(f"cannot read {PYTHON_VERSION_FILE}: {exc}") from exc


def build_command(arch: str) -> list[str]:
    return [
        "uv", "run", "flet", "build", "apk",
        "--arch", arch, "--python-version", python_version(), "--yes",
    ]  # fmt: skip


def built_apk() -> Path:
    """The APK this build produced (`flet build` empties the output folder first)."""
    apks = list(APK_DIR.glob(APK_GLOB))
    if not apks:
        raise BuildError(f"no APK in {APK_DIR}")
    return max(apks, key=lambda p: p.stat().st_mtime)


def named_copy(apk: Path, arch: str, release: bool) -> Path:
    """Copy the built APK to build/android/ under a name with its architecture and kind."""
    suffix = RELEASE_SUFFIX if release else ""
    APK_KEEP_DIR.mkdir(parents=True, exist_ok=True)
    target = APK_KEEP_DIR / f"{APK_STEM}-{arch}{suffix}.apk"
    shutil.copy2(apk, target)
    return target


def verify(apk: Path) -> None:
    """Check the APK's signature with apksigner."""
    cmd = [str(find_apksigner()), "verify", "--verbose", str(apk)]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise BuildError(f"apksigner verify failed: {result.stderr.strip() or result.stdout}")
    logger.info("apksigner verify passed:\n%s", result.stdout.strip())


def build(arch: str, release: bool) -> Path:
    """Run `flet build apk` for one architecture and return the kept copy's path.

    A release build is signed with the keystore named in .env and then checked with
    apksigner. A test build is signed with the debug key `flet build` uses by default.
    """
    if arch not in ARCHES:
        raise BuildError(f"arch must be one of {', '.join(ARCHES)}")
    env = dict(os.environ)
    for name in FLET_SIGNING_ENV.values():
        env.pop(name, None)
    if release:
        for name, value in signing_values().items():
            env[FLET_SIGNING_ENV[name]] = value
    APK_DIR.mkdir(parents=True, exist_ok=True)
    cmd = build_command(arch)
    logger.info("running: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT, env=env, check=False)
    if result.returncode != 0:
        raise BuildError(f"flet build apk failed with exit code {result.returncode}")
    apk = built_apk()
    if release:
        verify(apk)
    return named_copy(apk, arch, release)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Build the DQ7 Tablet Trader APK.")
    parser.add_argument("--arch", choices=ARCHES, default=RELEASE_ARCH)
    parser.add_argument("--release", action="store_true", help="sign with the release key")
    parser.add_argument(
        "--make-keystore", action="store_true", help="create the release key if missing, then stop"
    )
    args = parser.parse_args()
    try:
        if args.make_keystore:
            make_keystore()
            return 0
        apk = build(args.arch, args.release)
    except BuildError as exc:
        logger.error("%s", exc)
        return 1
    logger.info("APK: %s (%.1f MB)", apk, apk.stat().st_size / 1_000_000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
