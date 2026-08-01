"""Stub Cursor CLI: success — echo a marker + first Input line from stdin."""

from __future__ import annotations

import sys


def main() -> int:
    stdin = sys.stdin.read()
    # Prefer the "## Input" section payload for the simple linear fixture.
    payload = "Hello from input"
    for line in stdin.splitlines():
        if line.startswith("Hello") or "Hello from input" in line:
            payload = "Hello from input"
            break
    sys.stdout.write(f"STUB_OK:{payload}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
