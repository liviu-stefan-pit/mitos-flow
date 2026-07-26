# Mitos Flow — Implementation Status

> Running log of completed work. Update after each phase.

**Last updated:** 2026-07-26  
**Current phase:** 9 (next)

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

---

## Known issues

_None._

---

## Next up

- Phase 9: Backend workflow schema
