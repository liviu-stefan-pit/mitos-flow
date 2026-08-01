# Playground

Local assets for **testing Mitos Flow workflows** and **demoing the product**.

Drop files from here into the Asset library (Phase 17+), wire them on the canvas, and run with the fake runner (or Cursor later).

## Layout

| Path | Purpose |
| --- | --- |
| `skills/` | Cursor-style `SKILL.md` packages for import |
| `rules/` | Cursor-style `.mdc` rule files for import |
| `inputs/` | Sample input payloads for Input nodes |
| `kb/` | Plain-text / Markdown snippets for later KB import (Phase 19+) |

## Quick demo (Phase 17)

1. Start the app: `npm run dev`
2. Open the **Asset library** (bottom-left)
3. Drop `skills/draft-brief/SKILL.md`
4. Preview → **Confirm import**
5. Drop one or more files from `rules/`
6. Confirm they appear in the library list

## Notes

- These files are **fixtures for humans and demos**, not runtime dependencies of the app.
- Prefer copying or dragging into the managed library — do not point the app at raw playground paths.
- Keep content small, readable, and free of secrets.
