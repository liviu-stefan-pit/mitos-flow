# Release checklist notes (playground KB)

## Before a Cursor smoke run

- Settings page shows Cursor CLI **Available**
- You are logged in (`agent status`)
- Workspace path is inside the approved project root
- Prefer the `cursor-smoke` skill with `cursor-smoke-safety` rule

## Before an artifact save demo (Phase 25+)

- Confirm the output root is a managed folder, not an arbitrary path
- Prefer timestamped copies while experimenting
- Keep sample payloads free of secrets and API keys

## Sample acceptance phrases

Useful strings to search for in Activity traces:

- attached rules listed by name
- knowledge query text
- cited chunk ids like `kb-…:c0`
- fake runner prefix `fake::`
