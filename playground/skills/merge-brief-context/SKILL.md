---
name: merge-brief-context
description: Merge a brief and a context document into one grounded outline. Use when a Skill has two named inputs (brief + context).
---

# Merge brief + context

You receive two inputs on named ports:

- **brief** — the primary ask / draft
- **context** — background notes, glossary, or constraints

Steps:

1. Treat `brief` as the primary source of the ask.
2. Use `context` only to fill gaps, clarify terms, or list constraints.
3. Produce a short outline with headings:
   - **Ask**
   - **Grounding from context**
   - **Risks / unknowns**
4. If the two sources conflict, prefer `brief` and call out the conflict under unknowns.
5. Do not invent stakeholders, dates, or metrics.
