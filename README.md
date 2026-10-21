# DQ7 Tablet Trader

DQ7 Tablet Trader is a fork of ABZB's DQ VII Tablet Editor (https://github.com/DSModdingTools/DQ-VII-Tablet-Editor), released under the same GPL-3.0 licence.

It is a tablet manager for Dragon Quest VII (3DS) saves, now that the tablet servers are gone: view, move and share Traveller's Tablets between your save files.

Status: in development, not released.

## Fixed in this version

- Upstream #1, #3: no spreadsheet step; saves are opened directly and the checksum and tablet count are always written. https://github.com/DSModdingTools/DQ-VII-Tablet-Editor/issues/1 https://github.com/DSModdingTools/DQ-VII-Tablet-Editor/issues/3
- Upstream #2: tablets the old editor did not recognise are named or shown as unknown, never as blank slots; the tablet count is always written correctly, so old leftover tablets no longer reappear and the list never gets holes. https://github.com/DSModdingTools/DQ-VII-Tablet-Editor/issues/2
- Upstream #4: Japanese saves are detected and refused with a clear message instead of being corrupted. https://github.com/DSModdingTools/DQ-VII-Tablet-Editor/issues/4

## Credits

- ABZB: the original editor and the tablet records.
- turtle-insect/DQ7: research on hero name, playtime and save chunks.
- DaniPhoFani and Gronya: the preserved saves used for testing.

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
