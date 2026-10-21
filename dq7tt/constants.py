"""Layout constants for Dragon Quest VII (3DS) saves. Offsets verified on 14 Western saves."""

# Whole-file layout: size of a save and the checksum that covers it.
SAVE_SIZE = 0x5000
CHECKSUM_OFFSET = 0x00
CHECKSUM_START = 0x10
CHECKSUM_BYTES = 4
U32_MASK = 0xFFFFFFFF
U32_BYTES = 4
BYTE_SIGN_BIT = 0x80
BYTE_RANGE = 0x100

# Received tablets (StreetPass / downloaded): fixed-size record array plus a count byte.
RECEIVED_OFFSET = 0x3610
RECEIVED_RECORD_SIZE = 0x54
RECEIVED_SLOTS = 24
RECEIVED_COUNT_OFFSET = 0x3E04
RECEIVED_END = RECEIVED_OFFSET + RECEIVED_SLOTS * RECEIVED_RECORD_SIZE

# Self-made tablets: fixed-size record array plus a count byte.
SELFMADE_OFFSET = 0x32D0
SELFMADE_RECORD_SIZE = 0x34
SELFMADE_SLOTS = 16
SELFMADE_COUNT_OFFSET = 0x3E00
SELFMADE_END = SELFMADE_OFFSET + SELFMADE_SLOTS * SELFMADE_RECORD_SIZE

# Hero name, play time and clear flag.
HERO_NAME_OFFSET = 0x0E30
HERO_NAME_SIZE = 26
PLAYTIME_OFFSET = 0x3250
PLAYTIME_FPS = 30
GAME_CLEARED_OFFSET = 0x3258
GAME_CLEARED_VALUE = 1

# Save files in a game folder, in slot order: the quick save, then the three adventure logs.
SAVE_FILENAMES = ("save000.bin", "save001.bin", "save002.bin", "save003.bin")

# Field offsets inside a received-tablet record.
REC_MAP_ID = 0x0C
REC_CLEAR_1 = 0x0E
REC_CLEAR_2 = 0x32
REC_SERIAL = 0x50
REC_STREETPASS_FIELDS = slice(0x00, 0x0C)
MAP_ID_FORMAT = "<H"
MAX_CLEAR_COUNT = 0xFF

# Chunked sections (header size, alignment, and the two chunks the editor touches).
CHUNK_HEADER_SIZE = 0x0C
CHUNK_ALIGN = 0x10
SURE_OFFSET = 0x32C0
SURE_VERSION = 3
SURE_SIZE = 0xDD8
IMIN_OFFSET = 0x40A0
IMIN_VERSION = 4

# Serials of the story tablets, which cannot be traded away.
STORY_SERIALS = frozenset({0x46, 0x47, 0x48})

# Chunk chain: first chunk, header layout (tag, u16 flags, u16 version, u32 size), and the
# top-level tags every Western save carries, in order (observed on the fixture saves).
CHUNK_CHAIN_START = 0x10
CHUNK_TAG_SIZE = 4
CHUNK_HEADER_FORMAT = "<4sHHI"
SURE_TAG = "SURE"
IMIN_TAG = "IMIN"
EXPECTED_CHUNK_TAGS = (
    "FLAG",
    "STGE",
    "PRTY",
    "FLAG",
    "OPTN",
    "FLAG",
    "STRY",
    "GAME",
    "WLDA",
    "SCRP",
    SURE_TAG,
    IMIN_TAG,
    "SILS",
)
JAPANESE_SAVE_MESSAGE = "This looks like a Japanese save. Japanese saves are not supported yet."
