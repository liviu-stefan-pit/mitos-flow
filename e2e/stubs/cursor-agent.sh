#!/usr/bin/env sh
# Phase 31 — Cursor CLI stub for Playwright / CI (POSIX).
# Handles capability probe flags and a deterministic success spawn.

case "$1" in
  --version)
    echo "1.2.3"
    exit 0
    ;;
  --help)
    cat <<'EOF'
Usage: agent [options]
  --print
  --output-format <text|json>
  --workspace <path>
  --model <id>
  --list-models
  --trust
  --force
  --api-key <key>
EOF
    exit 0
    ;;
  --list-models)
    echo "composer-2.5"
    echo "composer-2.5-fast"
    exit 0
    ;;
esac

# Default: pretend a successful agent run. Stdin is ignored.
echo "STUB_OK:Hello from input"
exit 0
