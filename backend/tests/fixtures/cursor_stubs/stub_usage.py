"""Stub Cursor CLI: success with trailing JSON usage metadata."""

from __future__ import annotations

import json
import sys


def main() -> int:
    sys.stdout.write("STUB_USAGE:done\n")
    sys.stdout.write(
        json.dumps({"usage": {"input_tokens": 3, "output_tokens": 5}}) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
