"""Plain sentences for core refusals that would otherwise show file-system wording."""

from dq7tt.errors import BankFileError, BankProblem, TabletTraderError

NOT_IN_LIST = "That tablet is not in this list."
NO_LOG = "That adventure log is not in this save."
DISCARD_TITLE = "Discard changes?"
EMPTY_FORMAT = "Open a save or find saves on {device}"
BANK_MOVE_TO_LOG = (
    "Tablets in the bank are copied into an adventure log, never moved. Use Copy to... instead."
)
BANK_READ = "Could not read the bank folder. Check it still exists and you can open it."
BANK_WRITE = "Could not write to the bank folder. Check it still exists and you can open it."
FILE_TROUBLE = (
    "A file could not be read or written. Check the folder still exists and you can open it."
)
BAD_BANK_FILE = "A tablet file in the bank could not be used. It may be damaged or hand-edited."
UNREADABLE_FILE = "A tablet file in the bank could not be read. Check you can open it."
FOLDER_CHARS = "Folder names can't contain / \\ : * ? \" < > |."
NAME_FIELD = "{name}"
FOLDER_FALLBACK = "That name can't be used for a bank folder. Pick another name."
# Sentences for a refused bank folder name; {name} is the folder name typed.
FOLDER_SENTENCES: dict[BankProblem, str] = {
    BankProblem.EXISTS: "A bank folder called {name} already exists.",
    BankProblem.MISSING: "There is no bank folder named {name}.",
    BankProblem.EMPTY: "Type a name for the folder first.",
    BankProblem.HIDDEN: "Folder names can't start with a dot.",
    BankProblem.BAD_CHARACTERS: FOLDER_CHARS,
    BankProblem.TRAILING: "Folder names can't end with a space or a dot.",
    BankProblem.RESERVED: "{name} is a name Windows keeps for itself. Pick another name.",
}
# Sentences for a refused bank file.
FILE_SENTENCES: dict[BankProblem, str] = {
    BankProblem.UNREADABLE: UNREADABLE_FILE,
}


def bank_problem(exc: BankFileError, folder: str | None = None) -> str:
    """The plain sentence for a refused bank file or folder.

    `folder` is the folder name the user typed, when the refusal is about a folder name; an
    unrecognised folder refusal then gets a folder sentence rather than a file one.
    """
    reason = exc.reason
    if reason in FOLDER_SENTENCES:
        sentence = FOLDER_SENTENCES[reason]
        if folder is None and NAME_FIELD in sentence:
            return FOLDER_FALLBACK
        return sentence.format(name=folder)
    if reason in FILE_SENTENCES:
        return FILE_SENTENCES[reason]
    return FOLDER_FALLBACK if folder is not None else BAD_BANK_FILE


def not_banked(name: str, exc: TabletTraderError) -> str:
    """Why one tablet of a batch did not reach the bank."""
    why = bank_problem(exc) if isinstance(exc, BankFileError) else str(exc)
    return f"{name} was not copied to the bank. {why}"


def already_in(name: str, where: str) -> str:
    return f"{name} is already in {where}."


def stayed_in(name: str, where: str, log_name: str) -> str:
    return f"{name} is already in {where}, so it stayed in {log_name}."


REMOVED_CODE = "REMOVED_SPECIAL"
# The core reports a removal after the fact; a question before it speaks of what will happen.
REMOVED_DONE = (
    " was removed. It came from the story or a Haven resident and may be hard to get back."
)
REMOVED_ASK = (
    "{name} will be removed. It came from the story or a Haven resident "
    "and may be hard to get back."
)


def confirm_text(code: str, message: str) -> str:
    """A core warning as a confirm asks it: removals in the future tense."""
    if code == REMOVED_CODE and message.endswith(REMOVED_DONE):
        return REMOVED_ASK.format(name=message.removesuffix(REMOVED_DONE))
    return message
