"""The public format spec must mention every offset the code relies on."""

from pathlib import Path

import pytest

from dq7tt import constants

FORMAT_DOC = Path(__file__).resolve().parent.parent / "docs" / "format.md"
OFFSET_SUFFIX = "_OFFSET"


def _offset_constants() -> dict[str, int]:
    return {
        name: value
        for name, value in vars(constants).items()
        if name.isupper()
        and not name.startswith("_")
        and name.endswith(OFFSET_SUFFIX)
        and isinstance(value, int)
    }


def _hex_literals(value: int) -> set[str]:
    return {f"0x{value:02X}".lower(), f"0x{value:04X}".lower()}


@pytest.mark.parametrize("name", sorted(_offset_constants()))
def test_format_doc_lists_every_offset(name: str) -> None:
    text = FORMAT_DOC.read_text(encoding="utf-8").lower()
    value = _offset_constants()[name]
    assert any(lit in text for lit in _hex_literals(value)), f"{name} missing from format.md"


def test_format_doc_has_no_em_dashes_or_private_links() -> None:
    text = FORMAT_DOC.read_text(encoding="utf-8")
    assert "\u2014" not in text
