"""Run the app in a headless Android emulator shaped like the AYN Thor's top screen.

Run from the repo root, for example:

    uv run python tools/android_emulator.py start
    uv run python tools/android_emulator.py install build/android/dq7-tablet-trader-x86_64.apk
    uv run python tools/android_emulator.py launch
    uv run python tools/android_emulator.py screenshot shot.png
    uv run python tools/android_emulator.py key BUTTON_B
    uv run python tools/android_emulator.py tap 960 540
    uv run python tools/android_emulator.py swipe 960 800 960 300 --ms 400
    uv run python tools/android_emulator.py push-saves tests/fixtures/us_postgame
    uv run python tools/android_emulator.py logcat out.txt
    uv run python tools/android_emulator.py app-log app.txt
    uv run python tools/android_emulator.py stop

The emulator never opens a window (`-no-window`); everything goes through adb.
"""

import argparse
import logging
import os
import subprocess
import time
from pathlib import Path

from build_android import sdk_root

logger = logging.getLogger("android_emulator")

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = os.name == "nt"
EXE = ".exe" if WINDOWS else ""
BAT = ".bat" if WINDOWS else ""

AVD_NAME = "dq7tt-thor"
SYSTEM_IMAGE = "system-images;android-33;google_apis;x86_64"
SDK_PACKAGES = ("emulator", "platform-tools", SYSTEM_IMAGE)
# The Thor's top screen, used landscape, at the density the Thor reports (about 832x468 dp).
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
SCREEN_DENSITY = 369
AVD_SETTINGS = {
    "hw.lcd.width": str(SCREEN_WIDTH),
    "hw.lcd.height": str(SCREEN_HEIGHT),
    "hw.lcd.density": str(SCREEN_DENSITY),
    "hw.initialOrientation": "landscape",
    "hw.keyboard": "yes",
    "hw.gamepad": "yes",
    "hw.ramSize": "4096",
    "disk.dataPartition.size": "6G",
}
# A fixed console port gives the emulator a known adb serial. Every adb call names it, so
# nothing here can reach a real phone or handheld that happens to be plugged in.
EMULATOR_PORT = 5554
EMULATOR_SERIAL = f"emulator-{EMULATOR_PORT}"
EMULATOR_FLAGS = ("-no-window", "-no-audio", "-no-snapshot-save", "-port", str(EMULATOR_PORT))
EMULATOR_LOG = ROOT / "build" / "emulator.log"

PACKAGE = "io.github.sonofskywalker3.dq7tablettrader"
LAUNCH_CATEGORY = "android.intent.category.LAUNCHER"
# The app's own log (Python output does not reach logcat). The emulator's google_apis image
# lets adb run as root, which is how this private file is read.
# The app keeps it in Flet's private app storage (FLET_APP_STORAGE_DATA).
APP_LOG = f"/data/data/{PACKAGE}/files/data/logs/dq7tt.log"
BOOT_TIMEOUT_S = 600
POLL_S = 3
STORAGE_TIMEOUT_S = 120
BOOTED = "1"
KEYCODE_PREFIX = "KEYCODE_"
DEFAULT_SWIPE_MS = 300

# Where Azahar keeps the US save (the id0/id1 folders are always 32 zeros).
ZERO_ID = "0" * 32
AZAHAR_SAVE_DIR = (
    f"/sdcard/Azahar/sdmc/Nintendo 3DS/{ZERO_ID}/{ZERO_ID}/title/00040000/0018ef00/data/00000001"
)
SAVE_GLOB = "*.bin"

# Keeps the emulator from opening a console window and from dying with this script.
DETACHED = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if WINDOWS else 0


class EmulatorError(RuntimeError):
    """The emulator or adb did not do what was asked."""


def adb_path() -> Path:
    return sdk_root() / "platform-tools" / f"adb{EXE}"


def emulator_path() -> Path:
    return sdk_root() / "emulator" / f"emulator{EXE}"


def cmdline_tool(name: str) -> Path:
    found = sorted((sdk_root() / "cmdline-tools").glob(f"*/bin/{name}{BAT}"))
    latest = sdk_root() / "cmdline-tools" / "latest" / "bin" / f"{name}{BAT}"
    if latest.is_file():
        return latest
    if not found:
        raise EmulatorError(f"{name} not found; run a first `flet build apk` to install the SDK")
    return found[-1]


def avd_home() -> Path:
    override = os.environ.get("ANDROID_AVD_HOME")
    return Path(override) if override else Path.home() / ".android" / "avd"


def run(cmd: list[str], *, input_text: str | None = None, timeout: float | None = None) -> str:
    """Run a tool, fail loudly on a non-zero exit, return its output."""
    logger.debug("running: %s", " ".join(cmd))
    result = subprocess.run(
        cmd, input=input_text, capture_output=True, text=True, timeout=timeout, check=False
    )
    if result.returncode != 0:
        raise EmulatorError(
            f"{Path(cmd[0]).name} failed: {(result.stderr or result.stdout)[-2000:]}"
        )
    return result.stdout


def adb(*args: str, timeout: float | None = None) -> str:
    """Run adb against the emulator only."""
    return run([str(adb_path()), "-s", EMULATOR_SERIAL, *args], timeout=timeout)


def ensure_sdk_packages() -> None:
    """Install the emulator, platform tools and the Android 13 image if they are missing."""
    missing = [pkg for pkg in SDK_PACKAGES if not (sdk_root() / Path(*pkg.split(";"))).is_dir()]
    if not missing:
        return
    logger.info("installing SDK packages: %s", ", ".join(missing))
    sdkmanager = str(cmdline_tool("sdkmanager"))
    run([sdkmanager, "--licenses"], input_text="y\n" * 20)
    run([sdkmanager, *missing], input_text="y\n" * 20)


def write_avd_settings(config: Path) -> None:
    """Set the Thor screen and hardware keys in the AVD's config.ini."""
    lines = config.read_text(encoding="utf-8").splitlines() if config.exists() else []
    kept = [line for line in lines if line.split("=", 1)[0].strip() not in AVD_SETTINGS]
    kept += [f"{key}={value}" for key, value in AVD_SETTINGS.items()]
    config.write_text("\n".join(kept) + "\n", encoding="utf-8")


def ensure_avd() -> None:
    """Create the dq7tt-thor AVD if it does not exist yet; bring its screen settings up to date."""
    config = avd_home() / f"{AVD_NAME}.avd" / "config.ini"
    if config.exists():
        write_avd_settings(config)
        return
    logger.info("creating AVD %s", AVD_NAME)
    avdmanager = str(cmdline_tool("avdmanager"))
    # avdmanager asks whether to make a custom hardware profile; "no" keeps the defaults.
    run([avdmanager, "create", "avd", "-n", AVD_NAME, "-k", SYSTEM_IMAGE, "--force"],
        input_text="no\n")  # fmt: skip
    write_avd_settings(config)


def accel_check() -> str:
    """The emulator's report on hardware acceleration (hypervisor)."""
    ensure_sdk_packages()
    result = subprocess.run(
        [str(emulator_path()), "-accel-check"], capture_output=True, text=True, check=False
    )
    return (result.stdout + result.stderr).strip()


def booted() -> bool:
    try:
        return adb("shell", "getprop", "sys.boot_completed", timeout=30).strip() == BOOTED
    except (EmulatorError, subprocess.TimeoutExpired):
        return False


def start() -> None:
    """Create the AVD if needed, start it headless and wait until Android has booted."""
    ensure_sdk_packages()
    ensure_avd()
    if booted():
        logger.info("emulator already running")
        return
    EMULATOR_LOG.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(emulator_path()), "-avd", AVD_NAME, *EMULATOR_FLAGS]
    logger.info("starting: %s", " ".join(cmd))
    with EMULATOR_LOG.open("w", encoding="utf-8") as log:
        subprocess.Popen(
            cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            creationflags=DETACHED,
        )  # fmt: skip
    adb("wait-for-device", timeout=BOOT_TIMEOUT_S)
    deadline = time.monotonic() + BOOT_TIMEOUT_S
    while not booted():
        if time.monotonic() > deadline:
            raise EmulatorError(f"emulator did not boot in {BOOT_TIMEOUT_S} s; see {EMULATOR_LOG}")
        time.sleep(POLL_S)
    logger.info("emulator booted")


def install(apk: Path) -> None:
    adb("install", "-r", str(apk), timeout=BOOT_TIMEOUT_S)
    logger.info("installed %s", apk.name)


def launch() -> None:
    adb("shell", "monkey", "-p", PACKAGE, "-c", LAUNCH_CATEGORY, "1")
    logger.info("launched %s", PACKAGE)


def screenshot(out: Path) -> None:
    """Save the screen as a PNG (adb exec-out screencap, no window involved)."""
    result = subprocess.run(
        [str(adb_path()), "-s", EMULATOR_SERIAL, "exec-out", "screencap", "-p"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        raise EmulatorError(f"screencap failed: {result.stderr.decode(errors='replace')}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(result.stdout)
    logger.info("screenshot %s", out)


def key(name: str) -> None:
    """Press a key, e.g. BUTTON_B, DPAD_DOWN or BACK."""
    code = name if name.startswith(KEYCODE_PREFIX) else KEYCODE_PREFIX + name
    adb("shell", "input", "keyevent", code)


def tap(x: int, y: int) -> None:
    adb("shell", "input", "tap", str(x), str(y))


def swipe(x1: int, y1: int, x2: int, y2: int, ms: int = DEFAULT_SWIPE_MS) -> None:
    adb("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(ms))


def push_saves(fixture_dir: Path) -> None:
    """Copy a fixture save into the folder Azahar keeps the US save in."""
    files = sorted(fixture_dir.glob(SAVE_GLOB))
    if not files:
        raise EmulatorError(f"no save files in {fixture_dir}")
    adb("shell", "mkdir", "-p", f"'{AZAHAR_SAVE_DIR}'")
    for file in files:
        _push_when_storage_ready(file, f"{AZAHAR_SAVE_DIR}/{file.name}")
    logger.info("pushed %d files to %s", len(files), AZAHAR_SAVE_DIR)


def _push_when_storage_ready(local: Path, remote: str) -> None:
    """adb push, retried: just after boot, shared storage refuses new files for a while."""
    deadline = time.monotonic() + STORAGE_TIMEOUT_S
    while True:
        try:
            adb("push", str(local), remote)
            return
        except EmulatorError:
            if time.monotonic() > deadline:
                raise
            logger.info("shared storage not ready yet, trying again")
            time.sleep(POLL_S)


def logcat(out: Path) -> None:
    """Save the whole log buffer to a file."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(adb("logcat", "-d"), encoding="utf-8")
    logger.info("logcat %s", out)


def app_log(out: Path) -> None:
    """Save the app's own log file (needs the emulator's root adb)."""
    adb("root")
    adb("wait-for-device", timeout=BOOT_TIMEOUT_S)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(adb("shell", f"cat '{APP_LOG}'"), encoding="utf-8")
    logger.info("app log %s", out)


def stop() -> None:
    adb("emu", "kill")
    logger.info("emulator stopped")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Headless Thor-shaped Android emulator.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("launch")
    sub.add_parser("accel-check")
    sub.add_parser("install").add_argument("apk", type=Path)
    sub.add_parser("screenshot").add_argument("out", type=Path)
    sub.add_parser("logcat").add_argument("out", type=Path)
    sub.add_parser("app-log").add_argument("out", type=Path)
    sub.add_parser("key").add_argument("name")
    sub.add_parser("push-saves").add_argument("fixture_dir", type=Path)
    tap_parser = sub.add_parser("tap")
    tap_parser.add_argument("x", type=int)
    tap_parser.add_argument("y", type=int)
    swipe_parser = sub.add_parser("swipe")
    for name in ("x1", "y1", "x2", "y2"):
        swipe_parser.add_argument(name, type=int)
    swipe_parser.add_argument("--ms", type=int, default=DEFAULT_SWIPE_MS)
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args()
    actions = {
        "start": start,
        "stop": stop,
        "launch": launch,
        "accel-check": lambda: logger.info("%s", accel_check()),
        "install": lambda: install(args.apk),
        "screenshot": lambda: screenshot(args.out),
        "logcat": lambda: logcat(args.out),
        "app-log": lambda: app_log(args.out),
        "key": lambda: key(args.name),
        "push-saves": lambda: push_saves(args.fixture_dir),
        "tap": lambda: tap(args.x, args.y),
        "swipe": lambda: swipe(args.x1, args.y1, args.x2, args.y2, args.ms),
    }
    try:
        actions[args.command]()
    except (EmulatorError, subprocess.TimeoutExpired) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
