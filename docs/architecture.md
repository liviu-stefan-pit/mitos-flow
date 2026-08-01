# Mitos Flow — Architecture

> Frozen contracts for v1. Created in Phase 0. Do not change without updating MASTER-PLAN.md.

**Last updated:** 2026-08-01

---

## System overview

Mitos Flow is a visual AI workflow builder: a drag-and-drop canvas where users chain local AI engines (starting with Cursor CLI) into executable automation flows.

```
React UI (Vite)  ──HTTP/SSE──▶  FastAPI API  ──▶  Workflow Service
                                                    │
                                    ┌───────────────┼───────────────┐
                                    ▼               ▼               ▼
                              DAG Scheduler   Fake Runner    Cursor CLI Adapter
                                    │               │               │
                                    └───────────────┴───────────────┘
                                                    │
                                              Artifact Store
```

### Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, Vitest, React Testing Library |
| Backend | Python 3.12+, FastAPI, Pydantic, pytest |
| Dev orchestration | npm root scripts (concurrently) |
| Runner (later) | Fake deterministic runner first; Cursor CLI adapter after scheduler is stable |

---

## Node kinds

| Kind | ID prefix | Role | Data-flow ports | Resource ports |
| --- | --- | --- | --- | --- |
| **Input** | `input-` | Data source for the workflow | Out (default) | — |
| **Skill** | `skill-` | Executable step (fake or Cursor CLI) | In (named), Out | Resource in (KB, Rules) |
| **Knowledge Base** | `kb-` | Reusable context documents | — | Out (resource attachment) |
| **Rules** | `rules-` | Behavioral constraints | — | Out (resource attachment) |
| **Artifact Output** | `output-` | Sink / projection of upstream data | In | Resource in (prompt template, later) |

All node kinds are required in the graph editor palette (Phase 5+).

---

## Edge kinds

| Kind | Visual | Direction | Allowed connections |
| --- | --- | --- | --- |
| **Data-flow** | Solid line | Source out → target in | Input→Skill, Skill→Skill, Skill→Artifact Output |
| **Resource attachment** | Dashed line | Resource out → resource in | KB→Skill, Rules→Skill, (later) Prompt→Artifact Output |

### Connection rules (v1)

- Self-links are rejected.
- Cycles are rejected (v1 DAG only).
- Data-flow edges connect output handles to input handles only.
- Resource edges connect resource-output handles to resource-input handles only.
- A Skill may have multiple named input ports; each port accepts at most one data-flow edge.
- KB and Rules attachments are many-to-many with Skills.

---

## Join policies

| Policy | v1 support | Behavior |
| --- | --- | --- |
| `wait_for_all` | **Yes (only policy in v1)** | Skill runs once every required named input port has received an `InputEnvelope` |
| `first_available` | No (deferred) | — |
| `any` | No (deferred) | — |

---

## InputEnvelope

Used when multiple named inputs feed a Skill (Phase 14+). Each envelope carries one input payload with provenance.

```json
{
  "port": "brief",
  "payload": "...",
  "mediaType": "text/plain",
  "sourceNodeId": "input-b",
  "order": 1
}
```

| Field | Type | Description |
| --- | --- | --- |
| `port` | string | Named input port on the target Skill |
| `payload` | string | Raw content |
| `mediaType` | string | MIME type (e.g. `text/plain`, `application/json`) |
| `sourceNodeId` | string | ID of the upstream node that produced this envelope |
| `order` | integer | Arrival sequence (for trace display; does not affect join logic) |

---

## Artifact Output modes

One **Artifact Output** node replaces separate Save and Output nodes.

| Mode | Model call? | Behavior |
| --- | --- | --- |
| **Pass-through** | No | Emit complete upstream result unchanged |
| **Selector** | No | Extract field/section via JSONPath or named text heading |
| **Prompted projection** | Yes | New artifact from upstream data + attached prompt template |

---

## Execution model

1. User triggers a run via `POST /api/runs`.
2. Workflow Service validates the graph (DAG, no dangling edges, valid edge kinds).
3. Deterministic DAG scheduler topologically orders nodes.
4. Scheduler dispatches each Skill to its configured runner (per-node Fake or Cursor; Phase 24).
5. Cursor Skills always receive an explicit `--model` (per-Skill preferred model, default `composer-2.5`; Phase 24.5).
6. Events stream to the UI via SSE (`queued` → `running` → `completed` / `failed`).
7. Artifact Output nodes write results to the artifact store or pass-through preview.

### Runner strategy

1. **Fake runner** (Phases 11–16): Deterministic, no external dependencies. Returns predictable output for testing.
2. **Cursor CLI adapter** (Phases 21–24): Spawns Cursor CLI with built command; captures stdout/stderr/exit/usage.
3. **Per-Skill models** (Phase 24.5): Each Cursor Skill picks a model from `agent --list-models` (excludes `auto`); default is `composer-2.5`.

---

## API surface (planned)

| Endpoint | Phase | Method | Purpose |
| --- | --- | --- | --- |
| `/api/health` | 1 | GET | Health check |
| `/api/workflows/validate` | 9 | POST | Validate workflow JSON |
| `/api/runs` | 11/15 | POST | Start a run (returns queued; live via SSE) |
| `/api/runs/{id}` | 15 | GET | Run snapshot + event log |
| `/api/runs/{id}/events` | 15 | GET (SSE) | Live run events |
| `/api/runs/{id}/cancel` | 16 | POST | Cancel an in-flight run |
| `/api/cursor/capability` | 21 | GET | Cursor CLI capability probe |
| `/api/cursor/dry-run` | 22 | POST | Build redacted Cursor command preview (no spawn) |
| `/api/cursor/models` | 24.5 | GET | List Cursor models (`agent --list-models`); default `composer-2.5` |
| `/api/runs` | 23–24 | POST | Cursor via `options.runner=cursor` (whole-run) or per-Skill `settings.runner=cursor` |
| `/api/workflows/export` | 29–30 | POST | Export `.flow` zip (`reference` / `snapshot` / `embedded`) |
| `/api/workflows/export/preview` | 30 | POST | Inventory preview (member paths, sizes, size/sensitivity warnings) |
| `/api/workflows/import` | 29–30 | POST | Import `.flow` zip (validate paths/sizes/checksums/mode; restore assets) |

### Artifact Output destinations (Phase 25)

| Destination | Behavior |
| --- | --- |
| `preview` | Passive: upstream bytes stay on the node/run result; no disk write |
| `managedFile` | Write under `MITOS_OUTPUT_ROOT` (default `.mitos-flow-artifacts`) |

Managed-file write modes:

| Mode | Behavior |
| --- | --- |
| `overwrite` | Atomic replace of the relative `filePath` |
| `timestamped` | Write `name-YYYYMMDDTHHMMSSZ.ext` beside the named path |

Path traversal and absolute paths are rejected. Replacement uses same-directory temp + `os.replace`.

### Deterministic selectors (Phase 26)

Selector Artifact Outputs project upstream Skill bytes **without** a runner/model call.

| Selector kind | Expression | Behavior |
| --- | --- | --- |
| `jsonPath` | Minimal JSONPath (`$.a.b`, `$.a[0]`, `$['key']`) | Extract field/value from JSON upstream |
| `namedSection` | Markdown ATX heading text | Extract body under matching heading |

Missing-data policies when the selector matches nothing:

| Policy | Behavior |
| --- | --- |
| `skip` | Mark this output branch skipped; run may still complete |
| `empty` | Deliver an empty artifact |
| `warning` | Deliver a `WARNING: …` text artifact |
| `fail` | Fail this output branch (and the run) |

Pass-through, selector, and prompted modes may fan out together from one terminal Skill. Prompted projections are an explicit second runner/model call (Phase 27).

### Prompted projections (Phase 27)

Prompted Artifact Outputs run a **second** model call with their own runner, model, timeout, and usage — never buried inside destination/file save.

| Setting | Behavior |
| --- | --- |
| `promptTemplate` | Required first-class prompt text applied to upstream Skill bytes |
| `runner` | `fake` or `cursor` for this projection only |
| `model` | Cursor model when `runner=cursor` (default `composer-2.5`) |

Fake prompted format: `fake::prompted::{label}::{promptTemplate}::{upstreamPayload}`.

Gate shape: one Skill → pass-through + selector + prompted → **two** runner calls (Skill + prompted).

### Tokens, cost, and run summary (Phase 28)

Runner usage is normalized (`inputTokens` / `outputTokens` / `totalTokens`) and aggregated into a `RunSummary` on the run snapshot and terminal SSE event.

Estimated cost uses a **versioned local rate table** (not live billing). When usage or pricing is unavailable, fields are null and the UI shows **unknown**. The UI always labels cost as an **estimate** — never as an exact charge.

### Skill Apply from library + dual resource handles (Phase 28.5)

Skill nodes mirror Rules/KB **Apply from library**: `content` (SKILL.md body) + `libraryAssetId`. Applied body is included in Cursor prompt assembly under `## Instructions`.

Skills expose two amber resource-in handles — **top** (`resource-in-top`) and **bottom** (`resource-in`) — layout aliases only; attachment resolution is unchanged.

### Workflow packages (Phases 29–30)

Versioned ``.flow`` zip archives port a workflow graph between local instances.

| Constant | Value |
| --- | --- |
| `FLOW_FORMAT_VERSION` | `1` |
| `packagingMode` | `reference` · `snapshot` · `embedded` |

| Mode | Manifests | Skill/Rules `original.*` | KB `original.*` |
| --- | --- | --- | --- |
| `reference` | yes | no | no |
| `snapshot` | yes | yes | no |
| `embedded` | yes | yes | yes |

Archive layout:

```
archive.flow  (ZIP)
├── format.json       # formatVersion, packagingMode, createdAt, app
├── workflow.json     # full domain Workflow (inlined node content + libraryAssetId)
├── checksums.json    # sha256 of every member except itself
└── assets/
    ├── skills/<id>/manifest.json  [+ original.md when snapshot/embedded]
    ├── rules/<id>/manifest.json   [+ original.mdc|md when snapshot/embedded]
    └── kb/<id>/manifest.json      [+ original.txt|md when embedded only]
```

**Reference mode** includes library **manifests** for referenced `libraryAssetId`s but **never** embeds `original.*` source docs (especially KB). Graph nodes already carry inlined `content`, so the workflow remains runnable after import.

**Snapshot mode** opt-in embeds Skill/Rules originals (exact managed library bytes) while KB stays reference-only.

**Embedded mode** also embeds KB source documents. Export preview (`POST /api/workflows/export/preview`) returns an inventory of member paths, per-asset sizes, and warnings (`sensitivity_embedded_kb`, `large_asset`, `large_package`) so callers can confirm before exporting. Bundle member paths must match the preview.

Import validates member paths (zip-slip), sizes, format version, packaging-mode original rules, and checksums **before** writing anything; missing referenced assets on export become warnings.

### Regression suite (Phase 31)

Extends the Phase 20.5 harness:

- API stories: fake-run + `.flow` portability (export → wipe → import → re-run), three-output matrix, Cursor stub
- Playwright: export/import round-trip, chain + run summary, Cursor stubbed via `e2e/stubs/` (no real tokens in CI)
- One documented **manual** Cursor smoke (playground `cursor-smoke`) — never required for automated gates

---

## Frontend architecture

```
frontend/src/
  app/           # Root layout, providers
  features/
    graph/       # Canvas, nodes, edges (Phase 4+)
    health/      # Backend connection status (Phase 2)
  lib/           # API client, env helpers
```

Environment variable: `VITE_API_URL` (defaults to `http://localhost:8000`).

---

## Backend architecture

```
backend/src/mitos_api/
  main.py        # FastAPI app, CORS, routes
  domain/        # Pydantic models (Phase 9+)
  services/      # Workflow, scheduler, runners (Phase 11+)
```

---

## v1 non-goals

Do not implement until Phase 31 baseline is stable:

- PDF / Office document conversion
- Vector embeddings and `sqlite-vec`
- Concurrent node scheduling
- Graph cycles
- Live external triggers
- Collaborative editing
- Native filesystem pickers (beyond managed library)
- GitHub Copilot CLI
- Automatic dependency installation
- Desktop packaging (Tauri / Electron)
- `first_available` / `any` join policies
- Hidden chain-of-thought in run traces

---

## Security boundaries (later phases)

- Cursor CLI: workspace boundary checks, secret redaction in command preview
- Artifact writes: constrained to approved output root; atomic file replacement
- Import: managed local library only (no raw path access)
- Export/import (Phase 29): zip-slip protection, checksum validation, size limits; reference mode omits source docs
