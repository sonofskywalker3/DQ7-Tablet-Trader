# Changelog

## Unreleased

- Added: open saves from Checkpoint, JKSM, Azahar, folders, single files and zips; scan for saves; tablet bank with folders; backups before every write.
- Fixed (upstream #2): tablets the old editor did not recognise are named or shown as unknown, never as blank slots; the tablet count is always written correctly, so old leftover tablets no longer reappear and the list never gets holes. https://github.com/DSModdingTools/DQ-VII-Tablet-Editor/issues/2
- Fixed (upstream #4): Japanese saves are detected and refused with a clear message instead of being corrupted. https://github.com/DSModdingTools/DQ-VII-Tablet-Editor/issues/4
- Fixed (upstream #1, #3): no spreadsheet step; saves are opened directly and the checksum and tablet count are always written. https://github.com/DSModdingTools/DQ-VII-Tablet-Editor/issues/1 https://github.com/DSModdingTools/DQ-VII-Tablet-Editor/issues/3
