---
name: extract-structured
description: Turn notes into a structured JSON brief. Use when downstream selectors need Goal, Constraints, and OpenQuestions fields.
---

# Extract structured

1. Read the input notes carefully.
2. Emit **only** a JSON object (no markdown fences) with this shape:

```json
{
  "goal": "one sentence",
  "audience": "who it is for",
  "constraints": ["bullet", "bullet"],
  "openQuestions": ["bullet"],
  "sections": {
    "summary": "2-3 sentences",
    "nextSteps": ["step 1", "step 2"]
  }
}
```

3. Do not invent facts. If a field is unknown, use an empty string or empty array.
4. Keep strings short and concrete.
