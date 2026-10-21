# Dragon Quest VII (3DS) save format: Traveller's Tablets

This describes the parts of a Dragon Quest VII 3DS save that matter for editing Traveller's Tablets. It is written for someone who has never seen this project, and for anyone porting the editor (for example to 3DS homebrew).

## What "verified" means here

Everything below was checked against 14 distinct save files from real play: 6 US and 8 PAL (European). They come from one player per region, so any claim that differs by region rests on a single player. There is no Japanese save in the sample set.

- **Verified**: true in all 14 files (or the number stated).
- **Inferred**: consistent with every file, but not proven.
- **Unverified**: taken from another source, or not testable with the samples. Treat as a guess until someone tests it.

All offsets are byte offsets from the start of a `saveNNN.bin` file, written in hex. Numbers are little-endian.

## Credits

- turtle-insect's DQ7 save editor: hero name, playtime, the chunk names and the general (non-tablet) offsets.
- ABZB's DQ VII Tablet Editor: the received-tablet record layout and the table of known tablets.
- The preserved save files shared by DaniPhoFani and Gronya, which made the verification possible.

## 1. Container

| Item | Value | Status |
| --- | --- | --- |
| File size | exactly 0x5000 (20480) bytes per `saveNNN.bin` | Verified |
| Encoding | plaintext: no compression, no encryption | Verified |
| Checksum location | u32 at 0x00 | Verified |
| Checksum rule | sum of bytes from 0x10 to the end of the file, each byte read as a signed 8-bit value, truncated to 32 bits | Verified |
| Bytes 0x04 to 0x0F | not covered by the checksum; look like uninitialised memory; keep them unchanged | Verified |

The last 0x10 bytes are not always zero: us_postgame save000 and save001 hold 0x02 at 0x4FF3 and 0x4FF9, and every PAL save holds 0x01 at 0x4FF0. Only the final byte, 0x4FFF, is zero in every sample, so summing to the end of the file and summing to one byte before it give the same result. The checksum covers those tail bytes either way.

### Slots

A game folder holds `save000.bin` to `save003.bin`. `save000` appears to be the quick (suspend) save and `save001` to `save003` the three adventure logs. This is inferred: the quick save holds the map id of where it was made at 0x0270, every sample log holds 0x04DF (The Haven) there, and the quick save never has the game-cleared flag set. No header byte marks a quick save. What an empty slot looks like is unknown, since every sample slot is populated.

## 2. Chunk chain

From 0x10 the file is a chain of tagged chunks. Each chunk starts with a 12-byte header:

| Header offset | Size | Meaning |
| --- | --- | --- |
| +0x00 | 4 chars | tag |
| +0x04 | u16 | 0 or 1 in real saves (meaning unknown); do not validate it |
| +0x06 | u16 | version |
| +0x08 | u32 | chunk size, counted from the start of the tag |

The next chunk starts at the end of the previous one rounded up to a multiple of 0x10. Zero bytes may sit in between. The chain is identical in all 14 files (US and PAL):

| Offset | Tag | Version | Size | Contents |
| --- | --- | --- | --- | --- |
| 0x0010 | FLAG | 1 | 0x250 | flag bits |
| 0x0260 | STGE | 1 | 0x29C | map and stage state; u16 at 0x0270 is the current map id (meaning inferred) |
| 0x0500 | PRTY | 1 | 0x768 | party: gold, bank, bag |
| 0x0C70 | FLAG | 1 | 0xB98 | wrapper around six DATA chunks |
| 0x0C80 + n * 0x1EC | DATA | 1 | 0x1EC | the six characters; character 0 is the hero |
| 0x1810 | OPTN | 1 | 0x18 | options |
| 0x1830 | FLAG | 1 | 0x1960 | flags, monster book |
| 0x3190 | STRY | 2 | 0xA4 | story progress |
| 0x3240 | GAME | 2 | 0x20 | playtime, owner id, game-cleared flag |
| 0x3260 | WLDA | 1 | 0x30 | not examined |
| 0x3290 | SCRP | 1 | 0x30 | not examined |
| 0x32C0 | SURE | 3 | 0xDD8 | all tablet lists (the name is the Japanese word for StreetPass) |
| 0x40A0 | IMIN | 4 | 0xF28 | Haven residents (the name is the Japanese word for immigrants) |
| 0x4FD0 | SILS | 2 | 0x30 | not examined |

The six DATA chunks are nested inside the 0x0C70 FLAG chunk, so the top-level chain has 13 chunks (FLAG, STGE, PRTY, FLAG, OPTN, FLAG, STRY, GAME, WLDA, SCRP, SURE, IMIN, SILS).

A reader should walk the chain and refuse any file whose tags differ from this list, whose SURE chunk is not version 3 and size 0xDD8 at 0x32C0, or whose IMIN chunk is not version 4 at 0x40A0. That one check rejects unknown layouts, including (probably) Japanese saves.

## 3. General fields

| Offset | Size | Meaning | Status |
| --- | --- | --- | --- |
| 0x00 | u32 | checksum | Verified |
| 0x0270 | u16 | map id where the file was saved (0x04DF = The Haven in every sample log; a log saved in Pilchard Bay holds 0x0194) | Verified value, meaning inferred |
| 0x0E30 | 26 bytes | hero name, UTF-8, NUL padded; a second copy sits at 0x0E4A | Verified |
| 0x3250 | u32 | playtime in frames at 30 frames per second (hours = value / 30 / 3600) | Verified |
| 0x3254 | u32 | owner (console) id; same value as in `system.bin` | Verified (use unverified) |
| 0x3258 | u32 | 1 once the game has been cleared | Verified |

## 4. Tablet lists (inside SURE)

| Offset | Size | Meaning | Status |
| --- | --- | --- | --- |
| 0x32D0 | 16 slots of 0x34 | self-made tablets (made through the Monster Meadows NPC), ending at 0x3610 | Slot size verified from the empty template; contents unverified, every sample has none |
| 0x3610 | 24 slots of 0x54 | received tablets (downloaded, built-in and StreetPass) | Verified |
| 0x3DF0 | 0x10 | zero padding | Verified |
| 0x3E00 | u32 (low byte used) | self-made count | Verified only as 0 for an empty list |
| 0x3E04 | u32 (low byte used) | received count: how many received slots are live | Verified |
| 0x3E08 | u32 | unknown (0xFFFFFFFF before the post-game, other values after) | Meaning unknown |

An earlier community description of "16 slots of 0x54 from 0x3150" is wrong. 0x3150 lies inside a FLAG chunk.

### Received list rules (mirroring the game)

- Only the count at 0x3E04 says which slots are live. Slots 0 to count-1 are always real, contiguous tablets. **Never decide that a slot is live or empty from its contents.**
- The list is **newest first**. A new tablet goes into slot 0 and everything else moves down one slot. The first tablet the story gives (Slimetree Forest) is always last.
- **Stale slots past the count are not cleared.** They hold either repeated copies of one earlier record or all-zero templates. Leave them as they are, but never treat them as tablets.
- **Insert at position p**: move slots p to count-1 down by one, write the record into slot p, add one to the count. The slot at the old count is overwritten. The list holds at most 24 tablets.
- **Remove position p**: move slots p+1 to count-1 up by one, subtract one from the count. The last live slot keeps its old bytes, becoming a stale slot, exactly as the game leaves it.
- After any change, recompute the checksum.

## 5. Received-tablet record (0x54 bytes)

The layout comes from ABZB's work; the status column says what the 14 saves confirm.

| Offset | Size | Meaning | Status |
| --- | --- | --- | --- |
| 0x00 to 0x0B | 6 x u16 | three search monsters, boss monster, header and footer name parts. Zero for downloaded and built-in tablets | Zero verified; meaning unverified |
| 0x0C | u16 | tablet and map id. Not unique: two pairs of tablets share an id. Built-in tablets are below 0x100, Haven downloads 0x10E to 0x152, story downloads 0x1F4 to 0x1F6 | Verified |
| 0x0E | u8 | clear count, first copy | Verified |
| 0x16 | u16 | unknown, constant per tablet | Verified constant |
| 0x18 to 0x27 | 8 x UTF-16 | name of the StreetPass sender; zero for downloads | Unverified (no StreetPass tablets in the samples) |
| 0x28 to 0x2B | 4 x u8 | three monster levels and the boss level | Values verified; meaning from ABZB |
| 0x2C to 0x2F | 4 bytes | profile bytes (hobby, title, personality per ABZB); downloads use 0x3D, 0x3F, 0x40 plus two bytes, built-in tablets use 00 FF FF FF | Values verified; meaning unverified |
| 0x32 | u8 | clear count, second copy; always equals the byte at 0x0E | Verified |
| 0x34 | u16 | unknown (downloads only) | Meaning unknown |
| 0x36 to 0x45 | 8 x UTF-16 | start of the Japanese download message, truncated; present in US and PAL saves alike | Verified |
| 0x46 to 0x49 | 4 x u8 | style byte (0x69 to 0x6E) and profile bytes | Values verified; meaning unknown |
| 0x50 | u8 | download serial, 0x01 to 0x4A; 0 for built-in tablets. The only unique key | Verified |

Naming key: the pair (id at 0x0C, serial at 0x50) names a tablet in the database. Identity in the code is stricter: two records are the same tablet when every byte matches except the two clear-count bytes at 0x0E and 0x32. Across all 14 files, records of the same tablet are byte-identical except for the two clear-count bytes at 0x0E and 0x32, in both regions. That is what makes copying a tablet between saves byte-safe inside the record. To reset a tablet's clear count, set both bytes to 0.

The three story tablets have serials 0x46, 0x47 and 0x48. Their records are minimal. Their scenes probably set story flags outside the record (unverified).

Serials 0x0B to 0x0F, 0x11 to 0x14, 0x16 to 0x18 and 0x1B to 0x1D never appear in the samples. A Japanese save may contain serials no Western save has.

## 6. State outside the record

- **First-clear rewards.** A one-time reward flag exists somewhere outside the record. Deleting and re-downloading a tablet resets the clear count in the record, but the reward stays spent. Resetting a clear count does not bring the reward back. The flag's location is not known.
- **Haven residents (IMIN).** Every downloaded Haven tablet arrives with a resident in the IMIN chunk at 0x40A0 (up to 40 slots of 0x60 bytes from 0x40B4, each holding the serial, tablet id and the full greeting). The three story downloads have no resident. Residents stay after their tablet is deleted. Copying only the tablet record into another save leaves no resident there. Whether the game later objects to a tablet with no matching resident is unverified. The layout of the resident slots is inferred.
- **Region.** US and PAL saves share the same chunk layout and records. No reliable region byte was found, and none is needed.

## 7. Japanese saves

Unsupported, and the layout is unknown. The Japanese tablet record appears to be 8 bytes shorter between 0x10 and 0x27 (name fields of 4 characters rather than 8), which would shift the SURE chunk contents. This is inferred from the field offsets used by Japanese-oriented tools. The Japanese received-record size cannot be reconstructed without a Japanese save. A reader that finds a chain which matches up to SURE but a different SURE position, version or size should report a Japanese save and stop (unverified heuristic).

## 8. system.bin and cardinfo.bin

`system.bin` is 544 bytes and holds the file-select summary for the four slots. It is not edited by this tool.

| Offset | Meaning | Status |
| --- | --- | --- |
| 0x10 | chunk SYTM, version 3, size 0x204 | Verified |
| 0x1C | u32 checksum: sum of bytes 0x20 to 0x1EF, each as a signed 8-bit value | Verified on 4 files |
| 0x24 | owner id, 4 values | Verified |
| 0x34 | progress value, 4 values | Meaning unknown |
| 0x44 | playtime, 4 values | Verified |
| 0x54 | map id, 4 values | Verified |
| 0x64 | game-cleared flag, 4 values | Verified |
| 0x74 | hero name, 4 values, 26-byte stride | Verified |
| 0xDC | last-used slot | Unverified |
| 0xE4 | 12-digit string (possibly a friend code) | Unverified |

Bytes 0x00 to 0x0F and 0x1F0 onward are not checksummed. Editing tablets inside one slot never needs a change to `system.bin`. Copying a whole save into another slot or console leaves the summary stale, which is at least cosmetic and possibly more (unverified). `cardinfo.bin` is 8 opaque bytes, identical within one console; leave it alone.

## 9. Known unknowns

1. The Japanese SURE layout.
2. Whether the game keeps accepting a downloaded tablet that has no IMIN resident.
3. What an empty adventure-log slot looks like.
4. Where the first-clear reward flag lives, and whether story tablets need story flags.
5. Whether the owner id is checked when a save moves between consoles.
6. StreetPass-received and self-made tablet records, which no sample contains.
