# DQ7 Tablet Trader

DQ7 Tablet Trader is a fork of ABZB's DQ VII Tablet Editor (https://github.com/DSModdingTools/DQ-VII-Tablet-Editor), released under the same GPL-3.0 licence.

It is a tablet manager for Dragon Quest VII (3DS) saves, now that the tablet servers are gone: view, move and share Traveller's Tablets between your save files.

Status: in development, not released.

## Download and run

Download `DQ7 Tablet Trader.exe` from the releases page once there is one (there is no release yet) and double-click it. There is nothing to install. The first start takes a few seconds while the app unpacks itself.

Windows or your antivirus may warn about the file, because the exe is not signed with a paid publisher certificate. This is common for small free tools. If you would rather not run an unsigned exe, run the app from source instead (below).

The app writes a small log file to `%LOCALAPPDATA%\DQ7 Tablet Trader\logs`, which helps if you need to report a problem.

## Using the window

**The app never changes your original save.** Every edit is written to a new copy, and a backup is taken first. Your Checkpoint, JKSM or Azahar save stays exactly as it was until you choose to put an edited copy back yourself. On Android, Save into Azahar is that choice: it backs up Azahar's save to the backups folder, then replaces it with the edited copy.

### Open and find saves

- Use Open save to pick a Checkpoint or JKSM backup folder, an Azahar save folder, any folder holding `save000.bin` to `save003.bin`, a single save file, or a zip.
- Use Find saves to scan your Azahar, Citra and Lime3DS data folders and removable drives for Dragon Quest VII saves.
- US and European saves work; Japanese saves are refused for now.
- You can open two saves at once and move tablets between them.

### Select and copy tablets

Each adventure log (1, 2 and 3) and the quick save shows its Traveller's Tablets, each with a carved stone and its kind written in colour: DLC, Story, Resident, StreetPass or Unknown. Select one or more tablets, then copy them to another log, drag them to the other pane, or remove them. In a narrow window, or on a touch screen, use Send to... instead of dragging; the grip at the start of each row still reorders a log. A copied tablet keeps its clear count unless you choose to reset the clears.

- The quick save is collapsed by default, and the first edit to it each session asks you to confirm.
- Removing a Story or Resident tablet, and adding a Story tablet, asks you to confirm first.
- A log cannot go over the game's tablet limit, and the same tablet cannot be added twice. The app tells you instead of changing anything.
- If you close the window, close a save or open another one with edits that are not written yet, the app asks first. Discard is the only way to lose them.

### The bank

The bank is your own shelf of tablets that lives outside any save. Use Bank all tablets in this log (in the More menu in a narrow window) to bank a whole log, bank single tablets with Copy to... or by dragging, and add a banked tablet to a log later. Banked tablets can be sorted into folders and moved between them; a tablet taken from the bank into a log is always a copy, so the bank keeps it. The bank is kept in the app's data folder, so it survives between saves and sessions.

### Writing and where the files go

Press Write changes to save your edits as a new copy. The window tells you where it went.

- Checkpoint, JKSM and plain folders: a new folder next to the one you opened.
- A single save file: a new file next to it.
- Zip files and Azahar saves: a folder under `Documents\DQ7 Tablet Trader\edited`.

Backups taken before each write are kept in the app's data folder (`%LOCALAPPDATA%\DQ7 Tablet Trader\backups`).

**Checkpoint and JKSM:** the edited copy shows up as a new backup in the Checkpoint or JKSM restore list on your 3DS once the folder is on the SD card. Restore that backup to use the edited save.

### Put into Azahar

For an Azahar save, after writing, the app offers Put into Azahar. If you choose Not now, the Put into Azahar button stays on the save's pane (in the More menu in a narrow window) until you make another change. Close Azahar first. The app checks the edited saves, backs up the Azahar save folder, then copies the edited saves in and tells you where the backup is.

Edited saves are unverified on a real 3DS until tested, so keep your backups.

### Not there yet

Dragging a save in from Windows Explorer, and editing self-made or StreetPass tablets, are not available yet.

## Android (AYN Thor)

There is also an Android app, made for the AYN Thor's top screen and Azahar running on the same handheld. It works on other Android devices too, with the save and the bank on tabs instead of side by side.

### Install

Download `DQ7 Tablet Trader 0.1.0.apk` from the releases page once there is one, or copy it to the handheld's Download folder over USB. Open it from the Files app and tap Install. The app is not on Google Play, so the first time Android asks whether the Files app (or your browser) may install apps: allow it, then go back and tap Install again.

### First start

1. **Allow access to your saves.** Android opens its All files access page. Turn DQ7 Tablet Trader on there, then come back to the app. The app needs this to change the save where Azahar keeps it.
2. **Choose your Azahar folder.** This is usually the folder called `Azahar` in internal storage. Picking a folder inside it works as well. The app then opens your Dragon Quest VII save with the bank beside it.

Only folders can be opened on Android: Azahar's folder, or Checkpoint and JKSM backup folders on an SD card. A single save file or a zip is not offered, because Android hands the app a copy of a picked file, so an edit could not go back where the file came from.

### Use it on the top screen

On the Thor, long-press the app in the launcher, choose Screen Launch, then Top Screen. The save fills the left side and the bank the right. On the bottom screen or a phone, the save and the bank are on two tabs.

- **Touch:** tap a tablet to tick it. Swipe up or down to scroll. Drag a tablet sideways to copy it to the other side. Long-press a tablet, then move it, to change its place in the log.
- **Controller:** the D-pad moves the gold pointer. A ticks a tablet or presses a button. B closes a question, or clears the ticks; it never leaves the app. L and R switch between the save and the bank. Y ticks every tablet. Start saves (it asks first).
- If you press Android's Back with changes that are not saved yet, the app asks first.

### Saving into Azahar

**Close the game in Azahar before saving.** On Android, Save into Azahar is one step: after you confirm, the app backs up Azahar's current save, then writes your edited save straight into Azahar's folder. It is all or nothing: if anything goes wrong part way, Azahar's save is put back as it was and the app says so. In the rare case it cannot be put back, the app names the backup to restore from the backups folder. When it is done, start the game in Azahar and load as usual.

### Where the files go

The bank, the backups and edited copies are kept in a folder called `DQ7 Tablet Trader` in internal storage, with `bank`, `backups` and `edited` inside. It stays when the app is uninstalled, and you can copy it to a PC over USB. The app's settings and its log file are kept in the app's own storage.

## Run from source

You need [uv](https://docs.astral.sh/uv/). From the project folder:

```
uv sync
uv run dq7tt-gui
```

To build the exe yourself: `uv run python tools/build_windows.py`. The result is in `dist`.

To build the Android app: `uv run python tools/build_android.py --arch arm64-v8a` (add `--release` for a build signed with your own key, after `--make-keystore` once). The APK is copied to `build/android`, named for its architecture.

## Fixed in this version

- Upstream #1, #3: no spreadsheet step; saves are opened directly and the checksum and tablet count are always written. https://github.com/DSModdingTools/DQ-VII-Tablet-Editor/issues/1 https://github.com/DSModdingTools/DQ-VII-Tablet-Editor/issues/3
- Upstream #2: tablets the old editor did not recognise are named or shown as unknown, never as blank slots; the tablet count is always written correctly, so old leftover tablets no longer reappear and the list never gets holes. https://github.com/DSModdingTools/DQ-VII-Tablet-Editor/issues/2
- Upstream #4: Japanese saves are detected and refused with a clear message instead of being corrupted. https://github.com/DSModdingTools/DQ-VII-Tablet-Editor/issues/4

## Credits

- ABZB: the original editor and the tablet records.
- turtle-insect/DQ7: research on hero name, playtime and save chunks.
- DaniPhoFani and Gronya: the preserved saves used for testing.
- Fonts: Sorts Mill Goudy by Barry Schwartz and Cinzel by the Cinzel Project Authors, both under the SIL Open Font License 1.1. The licence texts ship beside the fonts in `dq7tt_gui/assets/fonts`.
- The window's text uses Sorts Mill Goudy Lining, a copy of Sorts Mill Goudy made by `tools/build_lining_font.py` so that plain digits draw as the font's own lining figures; it keeps the same licence.
- The window's parchment, border bands, compass rose, pointer and tablet stones, and the Android app's icon, are drawn for this app by `tools/build_gui_art.py`; no game art is used.

## Command line (for testing)

The command line never changes the save you point it at. Every edit takes a backup first, then writes a new copy: a sibling folder next to a Checkpoint, JKSM or plain folder input, a sibling file next to a single save file, a folder under the app's `edited` folder for zip and Azahar inputs, or the new folder named by `--out` (never inside the input or an Azahar emulator's folders). Every other file is copied unchanged, and the tool refuses to overwrite anything that already exists. PATH can be a Checkpoint, JKSM or Azahar save folder, any folder holding `save000.bin` to `save003.bin`, a single save file, or a zip. Positions (`--slot`) are numbered from 1, as `list` prints them. Editing the quick save needs `--allow-quick-save`. `--app-dir DIR` goes before the command and moves the bank, backups and edited saves to DIR.

```
dq7tt list PATH
dq7tt add PATH --log {1,2,3,quick} --tablet "Mount Oddna" [--out DIR]
dq7tt copy SRC_PATH --from-log N --slot I DST_PATH --to-log M [--reset-clears] [--out DIR]
dq7tt remove PATH --log N --slot I [--out DIR]
dq7tt scan [ROOT ...]
dq7tt bank list [FOLDER]
dq7tt bank import PATH --log N [--folder F]
dq7tt bank add PATH --log N --file BANKFILE [--out DIR]
dq7tt bank export PATH --log N --slot I [--folder F]
dq7tt azahar put EDITED_DIR AZAHAR_SAVE_DIR
```

- `list` shows each log with its hero, play time, tablet count and tablets.
- `add` puts a tablet that has been verified on a real save at the top of a log.
- `copy` copies one tablet from one log to another, in the same folder or a different one, keeping its clear count unless `--reset-clears` is given.
- `remove` takes one tablet out of a log.
- `scan` prints one line per Dragon Quest VII save found in the given folders (by default the Azahar, Citra and Lime3DS data folders and removable drives).
- `bank list` shows banked tablets, for one bank folder or all of them. `bank import` banks every tablet of a log, `bank export` banks one, and `bank add` puts a banked tablet at the top of a log (BANKFILE is a path, or a name inside the bank).
- `azahar put` checks that EDITED_DIR holds Dragon Quest VII saves the game would accept, backs up the Azahar save folder, then copies the edited saves into it, and prints the backup zip.

Anything that would produce a save the game might reject is refused with a message and exit status 2. Edited saves are unverified on a real 3DS until tested.
