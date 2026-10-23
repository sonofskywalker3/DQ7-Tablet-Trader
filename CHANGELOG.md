# Changelog

## Unreleased

- Added: an Android app, made for the AYN Thor's top screen (save on the left, bank on the right; save and bank tabs on smaller screens). Installed from an APK file, not Google Play. At first start it asks for access to your saves and for your Azahar folder, then opens your save. Save into Azahar is one step on Android: it backs up Azahar's save first and puts it back if writing fails. Touch: tap to tick, swipe to scroll, drag sideways to copy, long-press to reorder. Controller: D-pad and A to move and tick, B to close a question or clear ticks (never leaves the app), L and R to switch sides, Y to tick all, Start to save. The bank, backups and edited copies live in a "DQ7 Tablet Trader" folder in internal storage. Opening a single save file or a zip is not offered on Android.
- Added: an app icon for Android, a carved story stone in a gold compass ring.
- Fixed: numbers in the window read as numbers. The text font now draws lining figures, so a 0 no longer looks like an "o" or a 1 like an "I".
- Changed: the window looks like an adventure log. Parchment with engraved bands, dark menu windows with a thin white edge, serif text, a gold pointer for where you are and a gold wash on ticked tablets. Each tablet shows a carved stone for its kind. Copy to and Move to say how full each log is. Fonts: Sorts Mill Goudy and Cinzel (SIL Open Font License).
- Added: a desktop window for Windows. Open or find saves, copy and move tablets between logs, keep a bank, write edited copies (never the original), and put an edited save into Azahar. Packaged as a single exe built with `tools/build_windows.py`; a log file is kept in the app data folder.
- Added: open saves from Checkpoint, JKSM, Azahar, folders, single files and zips; scan for saves; tablet bank with folders; backups before every write.
- Fixed (upstream #2): tablets the old editor did not recognise are named or shown as unknown, never as blank slots; the tablet count is always written correctly, so old leftover tablets no longer reappear and the list never gets holes. https://github.com/DSModdingTools/DQ-VII-Tablet-Editor/issues/2
- Fixed (upstream #4): Japanese saves are detected and refused with a clear message instead of being corrupted. https://github.com/DSModdingTools/DQ-VII-Tablet-Editor/issues/4
- Fixed (upstream #1, #3): no spreadsheet step; saves are opened directly and the checksum and tablet count are always written. https://github.com/DSModdingTools/DQ-VII-Tablet-Editor/issues/1 https://github.com/DSModdingTools/DQ-VII-Tablet-Editor/issues/3
