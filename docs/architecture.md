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
- Export: zip-slip protection, checksum validation
