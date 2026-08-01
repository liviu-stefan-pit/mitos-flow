# Playground

Local assets for **testing Mitos Flow workflows** and **demoing the product**.

Drop files from here into the Asset library (Phase 17+), wire them on the canvas, and run with the fake runner (or Cursor later).

## Layout

| Path | Purpose |
| --- | --- |
| `skills/` | Cursor-style `SKILL.md` packages for import |
| `rules/` | Cursor-style `.mdc` rule files for import |
| `inputs/` | Sample Input-node payloads (text + JSON) |
| `kb/` | `.txt` / `.md` Knowledge Base snippets |
| `prompts/` | Prompt templates for Phase 27 prompted outputs |

## Skills

| Skill | Good for |
| --- | --- |
| `draft-brief` | Golden fake-run story; first Skill in a chain |
| `polish-summary` | Second Skill in a chain (Draft→Polish) |
| `extract-structured` | JSON output for Phase 26 selectors |
| `merge-brief-context` | Two named inputs (`brief` + `context`) join |
| `rewrite-for-audience` | Extra chain hop / audience rewrite |
| `cursor-smoke` | Tiny Phase 23 real Cursor manual smoke |

## Rules

| Rule | Notes |
| --- | --- |
| `no-invented-facts.mdc` | Always-on grounding (golden story) |
| `prefer-explicit-structure.mdc` | Headings / bullets |
| `typescript-apis.mdc` | Glob-scoped sample |
| `keep-outputs-short.mdc` | Timeline-friendly brevity |
| `cite-kb-chunks.mdc` | KB citation reminder |
| `json-only-when-asked.mdc` | Pair with `extract-structured` |
| `cursor-smoke-safety.mdc` | Read-only Cursor smoke |

## Knowledge bases

| File | Notes |
| --- | --- |
| `product-overview.md` | Primary demo KB (golden story) |
| `architecture-glossary.md` | Multi-section retrieval / top-K |
| `faq.txt` | Plain-text KB import |
| `competitor-notes.md` | Isolation contrast vs product-overview |
| `release-checklist.md` | Manual smoke checklist phrases |

## Inputs

| File | Notes |
| --- | --- |
| `sample-notes.txt` | Classic linear demo |
| `brief-a.txt` / `context-b.txt` | Pair for join Skill ports |
| `cursor-smoke-task.txt` | Tiny real-Cursor prompt |
| `structured-report.json` | Rich JSON brief sample |
| `selector-demo.json` | Phase 26 JSONPath fixture |

## Quick demos

### Import + fake run (Phase 17–20)

1. `npm run dev`
2. Asset library → drop `skills/draft-brief/SKILL.md` → confirm
3. Drop `rules/no-invented-facts.mdc` + `rules/prefer-explicit-structure.mdc`
4. Drop `kb/product-overview.md`
5. Wire Input → Draft → Output; attach rules + KB; Run

### Two-input join

1. Import `merge-brief-context`
2. Two Inputs labeled/ports `brief` and `context`
3. Paste `inputs/brief-a.txt` and `inputs/context-b.txt`
4. Run (fake) and confirm both ports appear in the trace

### KB isolation

1. Import `product-overview.md` and `competitor-notes.md`
2. Attach only product-overview to Skill A
3. Attach only competitor-notes to Skill B
4. Confirm traces do not cross-contaminate

### Cursor smoke (Phase 31 manual — real CLI / tokens; not CI)

Automated E2E stubs Cursor (`e2e/stubs/`). This playground path is the **documented manual** real-CLI smoke:

1. Settings → Cursor CLI **Available** + `agent status` logged in
2. Import `cursor-smoke` + `cursor-smoke-safety.mdc`
3. Input = `inputs/cursor-smoke-task.txt`
4. Prefer dry-run preview (Phase 22) before real spawn

### Selector / prompted (Phase 26–27)

1. Use `extract-structured` or paste `inputs/selector-demo.json`
2. Prompt templates live under `prompts/` (status email, executive digest)

## Notes

- These files are **fixtures for humans and demos**, not runtime dependencies of the app.
- Prefer copying or dragging into the managed library — do not point the app at raw playground paths.
- Keep content small, readable, and free of secrets.
- Existing golden E2E paths (`draft-brief`, `no-invented-facts`, `product-overview`) stay stable; new files are additive.
