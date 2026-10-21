"""Extract ABZB's tablet record table from the upstream constants.py into JSON."""

import ast
import json
import sys
from pathlib import Path

DICT_NAME = "dlc_haven_tablet_hex_dict"
RECORD_HEX_LEN = 168
SOURCE_NOTE = "ABZB, DQ-VII-Tablet-Editor constants.py (GPL-3.0)"
EXPECTED_ARGS = 3


def extract(constants_path: Path) -> list[dict[str, str]]:
    tree = ast.parse(constants_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == DICT_NAME for t in node.targets
        ):
            table = ast.literal_eval(node.value)
            records = [{"name": k, "record_hex": v} for k, v in table.items()]
            for rec in records:
                if len(rec["record_hex"]) != RECORD_HEX_LEN:
                    raise ValueError(f"bad record length for {rec['name']!r}")
            return records
    raise KeyError(DICT_NAME)


def main(argv: list[str]) -> int:
    if len(argv) != EXPECTED_ARGS:
        sys.stderr.write("usage: extract_upstream_records.py constants.py out.json\n")
        return 2
    records = extract(Path(argv[1]))
    out = {"source": SOURCE_NOTE, "records": records}
    Path(argv[2]).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    sys.stdout.write(f"{len(records)} records\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
