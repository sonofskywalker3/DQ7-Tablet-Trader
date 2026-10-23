"""What differs between the desktop app and the Android app; no window code here."""

from dataclasses import dataclass
from enum import StrEnum


class Platform(StrEnum):
    DESKTOP = "desktop"
    ANDROID = "android"


@dataclass(frozen=True)
class Profile:
    """How the app behaves on one kind of device.

    `one_step_azahar`: writing an Azahar save puts it straight into Azahar behind one confirm.
    `can_open_files`: the device can pick a single save file, not only folders.
    `device_word`: how the app names the device in sentences ("this PC").
    """

    platform: Platform
    one_step_azahar: bool
    can_open_files: bool
    device_word: str


DESKTOP_PROFILE = Profile(Platform.DESKTOP, False, True, "this PC")
ANDROID_PROFILE = Profile(Platform.ANDROID, True, False, "this device")
