---
name: cursor-smoke
description: Tiny read-only Cursor smoke skill for Phase 23. Summarize the input in three bullets without editing files.
---

# Cursor smoke

This skill is for a **manual Cursor CLI smoke run**.

1. Read the supplied input only.
2. Reply with exactly three short bullets:
   - **Understood** — what the user wants
   - **Risk** — one concrete risk or gap
   - **Next** — one suggested next step
3. Do **not** edit files, run shell commands, or invent facts.
4. Keep the entire reply under 80 words.
