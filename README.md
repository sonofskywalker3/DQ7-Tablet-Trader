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

The command line never changes the folder you point it at. Every edit writes a new folder next to it (or at `--out`), with every other file copied unchanged, and refuses to overwrite anything that already exists. Positions (`--slot`) are numbered from 1, as `list` prints them. Editing the quick save needs `--allow-quick-save`.

```
dq7tt list PATH
dq7tt add PATH --log {1,2,3,quick} --tablet "Mount Oddna" [--out DIR]
dq7tt copy SRC_PATH --from-log N --slot I DST_PATH --to-log M [--reset-clears] [--out DIR]
dq7tt remove PATH --log N --slot I [--out DIR]
```

- `list` shows each log with its hero, play time, tablet count and tablets.
- `add` puts a tablet that has been verified on a real save at the top of a log.
- `copy` copies one tablet from one log to another, in the same folder or a different one, keeping its clear count unless `--reset-clears` is given.
- `remove` takes one tablet out of a log.

Anything that would produce a save the game might reject is refused with a message and exit status 2. Edited saves are unverified on a real 3DS until tested.
