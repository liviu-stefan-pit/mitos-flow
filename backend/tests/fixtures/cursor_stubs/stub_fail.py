"""Stub Cursor CLI: non-zero exit with stderr."""

from __future__ import annotations

import sys


def main() -> int:
    sys.stderr.write("STUB_FAIL: intentional failure\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
