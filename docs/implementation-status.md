# Mitos Flow — Implementation Status

> Running log of completed work. Update after each phase.

**Last updated:** 2026-08-01  
**Current phase:** 29 (next)

---

## Completed phases

| Phase | Date | Summary |
| --- | --- | --- |
| 0 | 2026-07-26 | Frozen contracts and phase gates |
| 1 | 2026-07-26 | Backend health service |
| 2 | 2026-07-26 | Frontend shell |
| 3 | 2026-07-26 | Unified local development command |
| 4 | 2026-07-26 | Read-only sample canvas |
| 5 | 2026-07-26 | Add, select, move, and delete nodes |
| 6 | 2026-07-26 | Typed edges and connection rules |
| 7 | 2026-07-26 | Node inspector and editable labels |
| 8 | 2026-07-26 | Local draft persistence |
| 9 | 2026-07-26 | Backend workflow schema + validate endpoint |
| 10 | 2026-07-26 | Frontend/backend schema round-trip |
| 11 | 2026-07-26 | Fake runner for one Skill + POST /api/runs |
| 12 | 2026-07-26 | DAG scheduler for linear Skill chains |
| 13 | 2026-07-26 | Branching to multiple passive Artifact Outputs |
| 14 | 2026-07-26 | Named inputs + wait_for_all joins |
| 15 | 2026-07-29 | Live SSE run events + canvas animation/timeline |
| 16 | 2026-07-29 | Cancel, per-node timeout, cleanup, branch failure |
| 17 | 2026-07-29 | Skill/Rules Markdown import into managed local library |
| 18 | 2026-08-01 | Attach Rules to Skills (many-to-many, ordered, traced) |
| 19 | 2026-08-01 | Basic KB resources: import, attach, keyword retrieval + citations |
| 20 | 2026-08-01 | KB retrieval controls: per-attachment top-K/threshold + query in trace |
| 20.5 | 2026-08-01 | Fake-run regression harness: API workflow stories + Playwright smoke |
| 21 | 2026-08-01 | Cursor CLI capability probe + Settings page |
| 22 | 2026-08-01 | Cursor command builder + dry-run preview (no spawn) |
| 23 | 2026-08-01 | Execute one Cursor Skill (spawn + capture; stub failure/timeout) |
| 24 | 2026-08-01 | Per-Skill Fake/Cursor runners for chains and joins |
| 24.5 | 2026-08-01 | Per-Skill Cursor model selection (default composer-2.5) |
| 25 | 2026-08-01 | Artifact Output destinations: preview + managed-file writes |
| 26 | 2026-08-01 | Deterministic selectors: JSONPath + named sections; missing-data policies |
| 27 | 2026-08-01 | Prompted Artifact Output projections (explicit second model call) |
| 28 | 2026-08-01 | Tokens, cost, and run summary (rate table + estimated cost UI) |
| 28.5 | 2026-08-01 | Skill Apply from library + dual resource-in handles |

---

## Phase notes

### Phase 0 — Freeze contracts and phase gates

**Status:** Complete  
**Date:** 2026-07-26

- Created `docs/architecture.md` with frozen v1 contracts (node kinds, edge kinds, join policies, InputEnvelope, output modes, non-goals)
- Created `docs/phases.md` with phase specifications
- Created `docs/implementation-status.md` (this file)
- No application code in this phase

### Phase 1 — Backend health service

**Status:** Complete  
**Date:** 2026-07-26

- `backend/pyproject.toml` with FastAPI, uvicorn, pytest, httpx
- `backend/src/mitos_api/main.py` with `GET /api/health` → `{"status":"ok"}`
- `backend/tests/test_health.py` — 1 test passing
- CORS middleware added (used by Phase 3)

### Phase 2 — Frontend shell

**Status:** Complete  
**Date:** 2026-07-26

- Scaffolded `frontend/` with Vite, React 19, TypeScript, Vitest, React Testing Library
- Header with "Mitos Flow" title
- Empty workspace placeholder
- Backend connection status indicator (checking / connected / disconnected)
- `frontend/src/App.test.tsx` — 4 tests passing

### Phase 3 — Unified local development command

**Status:** Complete  
**Date:** 2026-07-26

- Root `package.json` with `npm run dev` using `concurrently`
- `README.md` with Windows setup instructions
- Dev CORS on backend (`CORS_ORIGINS` env var, defaults to `http://localhost:5173`)
- `VITE_API_URL` environment variable in frontend (defaults to `http://localhost:8000`)
- `npm test` runs both backend and frontend test suites
- Vite `/api` proxy + localhost CORS regex (port-mismatch fix)

### Phase 4 — Read-only sample canvas

**Status:** Complete  
**Date:** 2026-07-26

- Added `@xyflow/react`
- Custom nodes: `InputNode`, `SkillNode`, `ArtifactOutputNode` under `frontend/src/features/graph/nodes/`
- Fixed sample graph: Input → Skill → Artifact Output
- `WorkflowCanvas` is read-only (`nodesDraggable={false}`, `nodesConnectable={false}`, `elementsSelectable={false}`); pan/zoom enabled
- Tests: `WorkflowCanvas.test.tsx` (2) + updated `App.test.tsx` — 6 frontend tests passing

### Phase 5 — Add, select, move, and delete nodes

**Status:** Complete  
**Date:** 2026-07-26

- Removed the fixed Phase 4 sample graph (`sampleGraph.ts`); canvas now starts empty on every load — no persistence yet (Phase 8)
- Added `NodePalette` (`frontend/src/features/graph/NodePalette.tsx`) with one "add" button per node kind: Input, Skill, Knowledge Base, Rules, Artifact Output
- Added `KnowledgeBaseNode` and `RulesNode` custom renderers (all 5 kinds from `docs/architecture.md` now exist under `frontend/src/features/graph/nodes/`)
- Added `nodeKinds.ts` (palette config: kind, React Flow type, ID prefix, display name) and `nodeFactory.ts` (creates a node with a unique ID and staggered position)
- `WorkflowCanvas` now uses `useNodesState`/`useEdgesState`; nodes are draggable, selectable, and deletable via a "Delete selected" button or the Backspace/Delete key
- Node settings remain fixed (no inspector yet — that's Phase 7); edges/connections remain disabled (`nodesConnectable={false}` — that's Phase 6)
- Tests: `WorkflowCanvas.test.tsx` (5 tests: empty start, palette presence, add each kind, delete selected, draggable/selectable classes) + updated `App.test.tsx` — 9 frontend tests passing
- `tsc -b --noEmit` passes

### Phase 6 — Typed edges and connection rules

**Status:** Complete  
**Date:** 2026-07-26

- Added typed handles: `data-out` / `data-in` (slate) and `resource-out` / `resource-in` (amber) on the five node kinds
- Skill exposes data in/out plus a bottom resource-in handle for KB/Rules attachments
- Added `connectionValidator.ts` — pure allow/reject rules for data-flow (Input→Skill, Skill→Skill, Skill→Artifact Output) and resource (KB→Skill, Rules→Skill); rejects self-links, handle mismatches, and invalid pairs with a clear reason string
- Added custom edge renderers: solid `dataFlow`, dashed `resourceAttachment` (`edges.tsx`)
- `WorkflowCanvas` enables `nodesConnectable`; `isValidConnection` + `onConnect` enforce rules; rejected drops show a red banner (`connection-feedback`)
- Delete selected also removes selected edges and edges attached to deleted nodes
- Tests: `connectionValidator.test.ts` — 19 tests covering every source×target pair for both edge kinds, plus self-link / handle / direction cases; total frontend suite 28 passing
- `tsc -b --noEmit` passes

### Phase 7 — Node inspector and editable labels

**Status:** Complete  
**Date:** 2026-07-26

- Added `nodeData.ts` with typed per-kind settings and defaults (label + kind-specific fields)
- Added right-side `NodeInspector`: editable name for all kinds; Input (media type, content); Skill (description, read-only `wait_for_all`); KB/Rules (description); Artifact Output (mode: pass-through / selector / prompted)
- Inspector shows when exactly one node is selected; empty state otherwise
- Updates patch only the selected node's `data` (no cross-mutation)
- Tests: inspector edit + select-switch isolation in `WorkflowCanvas.test.tsx`

### Phase 8 — Local draft persistence

**Status:** Complete  
**Date:** 2026-07-26

- Added versioned draft schema (`draftStorage.ts`, `version: 1`) under localStorage key `mitos-flow.workflow-draft`
- Canvas auto-saves nodes (positions + settings) and edges after hydrate; reload restores the draft
- Corrupt / unsupported / dangling-edge drafts fall back to empty canvas with a warning banner and clear the bad entry
- Palette actions: **New Workflow** and **Reset Draft**, both gated by `window.confirm`, clear canvas + draft
- Tests: `draftStorage.test.ts` (8) + canvas restore / corrupt / confirm flows; frontend suite 43 passing
- `tsc -b --noEmit` passes

### Phase 9 — Backend workflow schema

**Status:** Complete  
**Date:** 2026-07-26

- Added Pydantic models in `backend/src/mitos_api/domain/` (`Workflow`, nodes, edges, ports, metadata, kind-specific settings)
- Added structural validator: duplicate IDs, dangling edges, invalid edge kinds/pairs, self-links, data-flow cycles
- `POST /api/workflows/validate` returns `{ valid, errors, workflow }` (no save, no execute)
- Fixtures: `valid_linear`, `cycle`, `dangling_edge`, `duplicate_ids`, `invalid_edge_kind`
- Backend tests: 12 passing

### Phase 10 — Frontend/backend schema round-trip

**Status:** Complete  
**Date:** 2026-07-26

- Matching TypeScript domain types in `frontend/src/domain/workflow.ts`
- Explicit UI→domain mapper `toDomainWorkflow.ts` (React Flow shapes → shared Workflow JSON)
- `validateApi.ts` client for `POST /api/workflows/validate`
- Palette: **Export JSON** and **Validate with API**; bottom-right panel shows domain JSON + validation result
- Tests: mapper settings preservation, mocked API round-trip, canvas export/validate; frontend suite 47 passing
- `tsc -b --noEmit` passes

### Phase 11 — Fake runner for one Skill

**Status:** Complete  
**Date:** 2026-07-26

- Runner interface (`SkillExecutionRequest` / `SkillExecutionResult` / `Runner` Protocol) under `backend/src/mitos_api/services/runners/`
- Deterministic `FakeRunner`: output format `fake::{skillLabel}::{inputPayload}`
- Synchronous orchestration in `services/runs.py` for exactly Input → Skill → Artifact Output (pass-through)
- Optional KB/Rules nodes are marked `skipped` (not executed yet)
- `POST /api/runs` accepts `{ workflow }` and returns `{ id, status, nodeResults, errors, output, mediaType }`
- Unsupported graphs rejected with `status: "rejected"` + `unsupported_graph` (multi-skill chains, non-pass-through outputs, wrong edge counts)
- Invalid workflows rejected via existing validator (e.g. cycles)
- Fixtures: `simple_linear`, `unsupported_two_skills`, `unsupported_selector_output`
- Backend tests: 20 passing (8 new in `test_runs.py`)
- **Manual check:** `POST /api/runs` with simple linear flow → `output: "fake::Draft::Hello from input"`

### Phase 12 — DAG scheduler for linear chains

**Status:** Complete  
**Date:** 2026-07-26

- Added `services/scheduler.py` with Kahn topological ordering for linear data-flow chains
- `plan_linear_chain` accepts Input → Skill+ → pass-through Artifact Output; rejects branches, joins, non-pass-through outputs
- `execute_run` runs Skills sequentially in topo order; runner failure marks the failed node and skips all downstream Skills + Output
- Fixtures: `linear_chain`, `unsupported_branch`, `unsupported_join`
- Backend tests: 30 passing (`test_scheduler.py` + updated `test_runs.py` for order and failure-stop)
- Frontend suite unchanged: 47 passing (no regressions)
- **Manual check:** `POST /api/runs` with Input→Draft→Polish→Output → order input/skill-1/skill-2/output; `output: "fake::Polish::fake::Draft::Hello from input"`

### Phase 13 — Branching and passive outputs

**Status:** Complete  
**Date:** 2026-07-26

- Extended `plan_linear_chain` to allow the terminal Skill to fan out to one or more pass-through Artifact Outputs
- `LinearChainPlan.output_nodes` (ordered by id); outputs are passive — same immutable upstream payload, zero extra runner calls
- Still rejects joins, Skill→Skill branching, Input branching, and non-pass-through outputs
- Fixture: `three_outputs.json` (Input → Draft → Out A/B/C); `unsupported_branch.json` now covers Skill→Skill branching
- Hardening fixtures/tests: `chain_three_outputs`, mixed Skill+Output branch reject, mixed output-mode fan-out reject, runner-calls==skill-count invariant
- Backend tests: 41 passing; frontend suite unchanged: 47 passing (no regressions)
- **Manual check:** `POST /api/runs` with three_outputs → all three outputs `fake::Draft::Hello from input`; recorder shows one Skill call

### Phase 14 — Multiple named inputs with wait-for-all

**Status:** Complete  
**Date:** 2026-07-26

- Added `InputEnvelope` domain model (`port`, `payload`, `mediaType`, `sourceNodeId`, `order`)
- Scheduler accepts multiple Inputs and Skill joins when each data-in port has at most one edge; still rejects same-port multi-edge (`unsupported_join`)
- `collect_input_envelopes` implements `wait_for_all` over every declared Skill data-in port; envelopes sorted by port name so arrival order cannot change FakeRunner output
- `SkillExecutionRequest.inputs` carries envelopes; FakeRunner multi-input format `fake::{label}::{portA}=…|{portB}=…`
- Missing required port → node state `blocked`, run `failed`, error code `blocked`; downstream Skills/Outputs skipped
- Fixtures: `two_inputs_named`, `two_inputs_named_reversed`, `missing_input_port`
- Backend tests: 51 passing; frontend suite unchanged: 47 passing (no regressions)
- **Manual check:** `POST /api/runs` with two named Inputs → Skill → Output yields `fake::Draft::brief=Hello A|context=Hello B`; missing `context` port blocks the Skill

### Phase 15 — Live run events in the UI

**Status:** Complete  
**Date:** 2026-07-29

- `POST /api/runs` returns immediately with `queued`; background thread executes with optional `options.delayMs`
- `GET /api/runs/{id}` snapshot + `GET /api/runs/{id}/events` SSE stream (`queued` → `running` → `completed`/`failed`)
- In-memory `RunStore` with sequenced event ids; reconnect via `Last-Event-ID` does not duplicate terminal run events
- Frontend: Run workflow button, animated active data edges, node run-state styling, Activity timeline (filters when a node is selected)
- Default live delay 400ms so progress is visible node-by-node
- Backend tests: delayed node-by-node events + SSE reconnect; frontend: runsApi + useWorkflowRun + canvas controls
- **Manual check:** Build a linear chain, click Run workflow, watch nodes/edges/timeline advance live

### Phase 16 — Cancellation and error boundaries

**Status:** Complete  
**Date:** 2026-07-29

- `POST /api/runs/{id}/cancel` sets cancel flag; orchestrator stops before the next Skill/Output starts
- Per-node `options.nodeTimeoutMs` via threaded Skill execute; timed-out Skills get `timeout` state
- Runner `cleanup(skillNodeId)` hook invoked after success, failure, timeout, and cancel-before-execute
- Branch failure reporting: each skipped/cancelled output carries an upstream/branch error message
- UI Cancel run button + stopped banner when status is `cancelled`
- Gate tests: cancel delayed chain → skill-2 never runs; timeout + cleanup + three-output branch skip
- **Manual check:** Start a delayed run, click Cancel mid-run; graph shows stopped/cancelled state and downstream nodes do not complete

---

### Phase 17 — Skill and Rules file import

**Status:** Complete  
**Date:** 2026-07-29

- Managed local library under `MITOS_LIBRARY_ROOT` (default: `.mitos-flow-library/` in cwd) — no raw path access
- Preview + confirm import flow: `POST /api/library/preview`, `POST /api/library/import`, batch import, list/get
- Preserves original Markdown alongside normalized `manifest.json` (name, description, frontmatter, body)
- Parses Cursor-style Skill (`SKILL.md` + name/description) and Rules (`.mdc`) frontmatter via PyYAML SafeLoader
- Malformed / unclosed / invalid YAML frontmatter reported as safe validation errors (no crash)
- Frontend: bottom-left Asset library panel with drag/drop, preview dialog, confirm import, asset list
- Gate tests: one Skill + multiple Rules batch import; malformed frontmatter fixtures
- Backend tests: 73 passing (12 new in `test_library.py`); frontend: 62 passing (9 new library tests)
- **Manual check:** Drop a Cursor `SKILL.md`; preview name/description/body; confirm import; asset appears in library

---

### Phase 18 — Attach Rules to Skills

**Status:** Complete  
**Date:** 2026-08-01

- Resolve Rules → Skill `resourceAttachment` edges before each Skill executes (`collect_attached_rules`)
- Many-to-many: one Rules node → many Skills; many Rules → one Skill; duplicate edges collapsed by Rules node id
- Ordered by Rules node id into `SkillExecutionRequest.rules` and FakeRunner `::rules[…]` suffix
- Run trace: Skill `NodeRunResult.attachedRules` + completed SSE event message/list; Activity timeline renders attached rules
- Rules nodes with content editable in inspector; optional apply-from-library for imported `.mdc` assets
- Unattached Rules stay `skipped`; KB still skipped (Phase 19); attached Rules mark `completed` once
- Gate fixtures/tests: `many_rules_one_skill`, `one_rule_many_skills`, dedupe + orphan skip
- Backend tests: 78 passing (5 new in `test_rules_attach.py`); frontend: 64 passing (Activity timeline + Rules inspector)
- **Manual check:** Attach two Rules to one Skill; run; Activity shows both rules on the Skill completed event

---

### Phase 19 — Basic KB resources without embeddings

**Status:** Complete  
**Date:** 2026-08-01

- Library `knowledgeBase` asset kind: import `.txt` / `.md` into managed `kb/` (preview/confirm, original + manifest)
- Plain `.md` without Skill/Rules cues infers as KB; `.txt` is KB-only
- KB node settings: `content` + optional `libraryAssetId`; inspector apply-from-library
- `collect_attached_knowledge_bases` — many-to-many, ordered by KB node id, duplicate edges collapsed
- Deterministic keyword retrieval (`services/kb/retrieval.py`): paragraph chunking, stopword-aware overlap score, default top-K=5 (Phase 20 will expose per-attachment controls)
- Cited chunks (`CitedChunk` with `chunkId`, `citation`, `score`) on `SkillExecutionRequest` / `NodeRunResult` / SSE events
- FakeRunner appends `::kb[{chunkId}:{citation}={text}|…]`; Activity timeline lists citations
- Attachment isolation: each Skill retrieves only from its attached KBs
- Unattached KB nodes stay `skipped`; attached empty KB completes with zero chunks
- Gate fixtures/tests: `kb_one_skill`, `kb_isolation`, `many_kbs_one_skill`, txt/md import
- Backend tests: 88 passing (9 new in `test_kb_attach.py`); frontend: 65 passing; `tsc -b --noEmit` clean
- **Manual check:** Attach a KB with product text to a Skill; run; Activity / output shows cited chunk(s)

---

### Phase 20 — KB retrieval controls

**Status:** Complete  
**Date:** 2026-08-01

- `ResourceAttachmentSettings` on KB→Skill resource edges: `topK` (default 5) + `threshold` (default 0)
- `AttachedKnowledgeBase` carries per-link controls; retrieval applies them independently per Skill/KB attachment
- Skill inspector lists attached KBs with editable top-K / threshold (writes to edge data; draft-persisted)
- Run trace: `knowledgeQuery` on Skill `NodeRunResult` / SSE events; message includes query, chunk IDs, citations
- Activity timeline renders query + chunk id + citation for retrieved chunks
- Gate: changing one attachment's controls affects only that Skill/KB link (shared KB → two Skills with different top-K)
- Gate fixtures/tests: `kb_retrieval_controls`, `kb_per_attachment_topk`, threshold filter, query-in-trace
- Backend tests: 94 passing (6 new in `test_kb_retrieval_controls.py`); frontend: 67 passing; `tsc -b --noEmit` clean
- **Manual check:** Attach KB to Skill; lower top-K in Skill inspector; run; Activity shows fewer cited chunks

---

### Phase 20.5 — Fake-run regression harness

**Status:** Complete  
**Date:** 2026-08-01

- API stories in `backend/tests/test_fake_run_story.py`: golden playground import→attach→run→trace; cancel mid-chain; Draft→Polish nested `fake::` composition
- Playwright scaffold at repo-root `e2e/` (Chromium only): `fake-run-golden.spec.ts`, `cancel-mid-run.spec.ts`
- Isolated library root via `MITOS_LIBRARY_ROOT` + `npm run dev:e2e` (uvicorn without `--reload` so Windows env override sticks)
- Graph topology seeded via localStorage draft in E2E (avoids flaky drag/connect under UI overlays); Asset library import still exercised through the UI
- Root scripts: `test:e2e`, `test:regression` (unit suite stays separate from browsers)
- Phase 31 will extend this harness (export/import + Cursor stub), not invent E2E from scratch
- Backend tests: 97 passing; `npm run test:e2e` green on Windows Chromium
- **Manual check:** `npx playwright install chromium` → `npm run test:e2e` green

---

### Phase 21 — Cursor capability probe

**Status:** Complete  
**Date:** 2026-08-01

- Read-only probe service (`services/cursor/probe.py`): locate `agent` / `cursor-agent` (or `MITOS_CURSOR_CLI` / `CURSOR_CLI_PATH`), run `--version` + `--help` only — no user prompts
- Feature flags discovered from help text markers only (no concept-doc assumptions)
- Statuses: `absent` / `available` / `unsupported_version` / `error`; minimum version floor `0.1.0`
- `GET /api/cursor/capability` returns `CursorCapabilityReport`
- Settings page (header nav): shows status, version, executable, message, help-discovered features; Refresh re-probes
- Gate tests: absent / available / unsupported-version (unit + API); Settings + App UI coverage
- Backend tests: 108 passing (11 new in `test_cursor_capability.py`); frontend: 74 passing; `tsc -b --noEmit` clean
- **Manual check:** Open Settings → Cursor CLI status section shows probe result

---

### Phase 22 — Cursor command builder and dry run

**Status:** Complete  
**Date:** 2026-08-01

- Command builder (`services/cursor/command_builder.py`): Skill request → argv + stdin **without spawning**
- Flags included only when advertised by the Phase 21 feature probe; prompt body on stdin (Windows cmdline length safety)
- Workspace boundary via `MITOS_CURSOR_WORKSPACE_ROOT` (default: cwd); path traversal / outside-root rejected
- Secret redaction for `--api-key` (value and `=` form); Windows quoting via `list2cmdline` / per-arg helper
- Timeout carried on the built command / preview (`timeoutMs`, default 120000)
- `POST /api/cursor/dry-run` returns redacted `commandDisplay` + stdin preview; `spawned` always false; confirmation gate
- Settings: **Cursor command dry-run** section — Preview command → redacted display → Confirm preview
- Gate tests: argument construction, Windows quoting, secret redaction, path checks (unit + API)
- Backend tests: 124 passing (16 new in `test_cursor_dry_run.py`); frontend: 76 passing; `tsc -b --noEmit` clean
- **Manual check:** Settings → enter optional API key → Preview command → confirm `***` redaction and Confirm preview

---

### Phase 23 — Execute one Cursor Skill

**Status:** Complete  
**Date:** 2026-08-01

- `CursorRunner` spawns Phase 22 built argv+stdin; captures stdout, stderr, exit code, elapsed ms, best-effort usage metadata
- Windows process-tree kill on timeout (`taskkill /T`) so `.cmd` wrappers do not hang
- `POST /api/runs` accepts `options.runner: "cursor"` + `options.cursor` (requires `confirmed: true`)
- Capture fields on `NodeRunResult` / SSE events; Activity timeline shows elapsed/exit/tokens when present
- Canvas palette: Fake / Cursor runner radios; Cursor run confirms then probes capability before spawn
- Gate fixture: `cursor_simple_linear.json`; stub executables under `tests/fixtures/cursor_stubs/`
- Gate tests: success + usage capture; API failure + timeout with stubs; confirmation required
- Backend tests: 135 passing (11 new in `test_cursor_execute.py`); frontend: 76+; `tsc -b --noEmit` clean
- **Manual check:** Build Input → Skill → Output; select Cursor; confirm; run successfully against real Cursor CLI

---

### Phase 24 — Cursor execution for chains and joins

**Status:** Complete  
**Date:** 2026-08-01

- Per-Skill `settings.runner` (`fake` | `cursor`, default `fake`); scheduler/topo/join semantics unchanged
- Mixed runs: FakeRunner + CursorRunner resolved together; each Skill picks its runner
- Phase 23 compat: `options.runner="cursor"` still forces Cursor for every Skill
- Confirmation still required when any Skill needs Cursor (`options.cursor.confirmed`)
- Inspector: Fake/Cursor radios per Skill; canvas badge; Run button labels when Cursor Skills present
- Gate fixtures: `cursor_two_skill_chain.json` (Cursor→Fake), `cursor_two_input_join.json`
- Gate tests: chain + join complete with stubs; confirmation reject for per-node Cursor
- Backend tests: 140 passing (5 new in `test_cursor_chains.py`); frontend: 77 passing; `tsc -b --noEmit` clean
- **Manual check:** Multi-node flow with Cursor on one Skill only; Fake on the other; run completes

---

### Phase 24.5 — Per-Skill Cursor model selection

**Status:** Complete  
**Date:** 2026-08-01

- `SkillNodeSettings.model` defaults to `composer-2.5`; meaningful when `runner=cursor`
- `GET /api/cursor/models` runs `agent --list-models` (read-only); filters out `auto`; hard-appends Composer default
- Cursor spawn always includes `--model <id>` (Skill setting → run-level fallback → `composer-2.5`)
- Per-Skill model on `SkillExecutionRequest` so mixed models work with one shared CursorRunner
- Trace: Skill completed message + `NodeRunResult.model` / SSE `model` for Activity timeline
- Inspector: Cursor model `<select>` when runner=Cursor; hidden for Fake; warning when CLI list fails
- Canvas badge shows model id under Cursor runner badge
- Gate fixtures/tests: parse filters auto; default argv `--model composer-2.5`; two Skills different models
- Backend tests: 148 passing (8 new in `test_cursor_models.py`); frontend: 79 passing; `tsc -b --noEmit` clean
- **Manual check:** Cursor Skill with default Composer; Activity shows `model composer-2.5`; change model and re-run

---

### Phase 25 — Artifact Output destinations

**Status:** Complete  
**Date:** 2026-08-01

- Artifact Output settings: `destination` (`preview` | `managedFile`), `filePath`, `writeMode` (`overwrite` | `timestamped`)
- Managed writes under `MITOS_OUTPUT_ROOT` (default `.mitos-flow-artifacts/`); path traversal / absolute paths rejected
- Atomic file replacement via same-directory temp + `os.replace`
- Preview destination: node/run output matches upstream Skill bytes; no disk write
- Run trace + Activity timeline surface `artifactPath` / `bytesWritten` when a file is saved
- Inspector: destination picker; file path + write mode when managed-file; canvas Preview/File badge
- Gate tests: path traversal, overwrite replace, timestamped non-clobber, preview byte match, API write
- Backend tests: 159 passing (11 new in `test_artifact_destinations.py`); frontend: 81 passing; `tsc -b --noEmit` clean
- **Manual check:** Set Output → managed file + overwrite path; run; open file under output root and verify contents

---

### Phase 26 — Deterministic selectors

**Status:** Complete  
**Date:** 2026-08-01

- Artifact Output `mode=selector` with `selectorKind` (`jsonPath` | `namedSection`), `selectorExpression`, `missingDataPolicy`
- Minimal in-tree JSONPath (`$.a.b`, `$.a[0]`, `$['key']`) + Markdown ATX named-section extraction
- Missing-data policies: `skip` / `empty` / `warning` / `fail` — each has a fixture
- Scheduler accepts pass-through + selector fan-out; prompted still rejected (Phase 27)
- Selectors project upstream Skill bytes with **zero extra runner calls**
- Inspector: selector kind/expression/missing-data fields; canvas mode badge
- Gate fixtures: `selector_jsonpath`, `selector_named_section`, `selector_mixed_fanout`, `selector_miss_{skip,empty,warning,fail}`
- Backend tests: 179 passing (20 new in `test_artifact_selectors.py`); frontend: 83 passing; `tsc` covered via Vitest
- **Manual check:** Set Output → selector + JSONPath `$.output.headline` on JSON Skill output; run; preview shows extracted field

---

### Phase 27 — Prompted output projections

**Status:** Complete  
**Date:** 2026-08-01

- Artifact Output `mode=prompted` with first-class `promptTemplate` (required) + own `runner` / `model`
- Explicit second runner call per prompted output (own timeout via `nodeTimeoutMs`, usage/model on result + SSE)
- Prompt never buried in destination/file-save path; Activity timeline surfaces `promptTemplate`
- Scheduler accepts pass-through + selector + prompted fan-out from one terminal Skill
- Fake format: `fake::prompted::{label}::{promptTemplate}::{upstream}` (always differs from pass-through)
- Inspector: prompt template textarea + Fake/Cursor runner (+ model picker); canvas Prompted + runner badges
- Gate fixtures/tests: `prompted_simple`, `prompted_three_outputs` — Skill → 3 outputs → **2** runner calls
- Backend tests: 185 passing (6 new in `test_artifact_prompted.py`); frontend: 85 passing; `tsc` covered via Vitest
- **Manual check:** Set Output → prompted + prompt template; run; preview differs from pass-through of same Skill data

---

### Phase 28 — Tokens, cost, and run summary

**Status:** Complete  
**Date:** 2026-08-01

- Normalized runner usage (`normalize_usage`) fills `totalTokens` from input+output; never invents counts
- Versioned local rate table (`RATE_TABLE_VERSION=1`): `composer-2.5`, `composer-2.5-fast`, `fake` ($0)
- `RunSummary` on `RunResponse` + terminal SSE events: token totals + `estimatedCostUsd` (null → UI "unknown")
- Always `costIsEstimate=true` + disclaimer: estimates are never presented as exact charges
- FakeRunner emits deterministic synthetic usage (`source=fake`) so local runs exercise the summary UI
- Activity timeline **Run summary** panel: input/output/total tokens + `est. $…` / `unknown` + disclaimer
- Gate tests: calculation + unknown cases + UI never labels cost as exact (`test_run_summary.py`, ActivityTimeline)
- Backend tests: 199 passing (14 new); frontend: 88 passing
- **Manual check:** Run a Fake linear flow; Activity shows Run summary with token counts and estimated cost (`est. $0.00` for fake)

---

### Phase 28.5 — Skill Apply from library + dual resource handles

**Status:** Complete  
**Date:** 2026-08-01

- Skill settings: `content` + `libraryAssetId` (mirror Rules/KB)
- Inspector **Apply from library** (`inspector-skill-library`) loads skill assets; applies name/description/body
- Manual edit of description/content clears `libraryAssetId`
- Cursor `assemble_prompt` includes applied body under `## Instructions`
- Dual Skill resource-in handles: bottom `resource-in` + top `resource-in-top` (layout aliases; collectors unchanged)
- Gate tests: `test_skill_library.py`, NodeInspector apply + connection validator top handle
- Backend tests: 203 passing; frontend: 93 passing
- **Manual check:** Import `extract-structured` → Apply on Skill; connect KB via top + Rules via bottom; run

---

## Known issues

_None._

---

## Next up

- Phase 29: Reference-mode workflow export/import
