# Mitos Flow

Visual AI workflow builder — drag-and-drop canvas for chaining local AI engines into executable automation flows.

## Prerequisites

- **Node.js** 20+ and **npm**
- **Python** 3.12+
- **pip** (Python package manager)

## Clean-clone setup (Windows)

From a fresh clone:

```powershell
# From the repo root
npm install
npm run install:all
npx playwright install chromium
```

This installs root Playwright tooling, frontend packages, the backend Python package (editable), and the Chromium browser used by E2E.

### Start development servers

```powershell
npm run dev
```

| Service  | URL                        |
| --- | --- |
| Frontend | http://localhost:5173      |
| Backend  | http://localhost:8000      |

Press `Ctrl+C` to stop both services.

### Verify the full fake flow

1. Open http://localhost:5173 — header shows **Backend connected**
2. Health: `curl http://localhost:8000/api/health` → `{"status":"ok"}`
3. Follow [playground/README.md](playground/README.md) **Import + fake run** (drop rules + KB, wire Input → Skill → Output, Run)
4. Or run the automated harness: `npm run test:regression`

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `VITE_API_URL` | (empty in Vite dev → same-origin `/api` proxy) | Backend URL for frontend |
| `CORS_ORIGINS` | (localhost regex) | Extra allowed CORS origins (comma-separated) |
| `MITOS_LIBRARY_ROOT` | `.mitos-flow-library` under cwd | Managed Skill/Rules/KB library root (E2E uses a temp dir) |
| `MITOS_OUTPUT_ROOT` | `.mitos-flow-artifacts` under cwd | Approved Artifact Output write root (Phase 25) |
| `MITOS_CURSOR_CLI` | (auto-detect `agent` / `cursor-agent`) | Override Cursor CLI path (E2E points at `e2e/stubs/`) |
| `MITOS_CURSOR_WORKSPACE_ROOT` | cwd | Workspace boundary for Cursor dry-run / spawn |

Create a `frontend/.env.local` to override the API URL:

```
VITE_API_URL=http://localhost:8000
```

## Running tests

```powershell
# Unit / API tests (fast loop — no browser)
npm test

# Backend only
npm run test:backend

# Frontend only
npm run test:frontend

# Playwright E2E (Chromium) — Phase 31 regression suite
# Prefer stopping other `npm run dev` sessions first, or set CI=1
$env:CI = "1"
npx playwright install chromium   # once per machine
npm run test:e2e

# Full regression (unit + e2e) — clean-clone gate
npm run test:regression
```

E2E boots its own stack via `npm run dev:e2e` (backend without `--reload` so `MITOS_LIBRARY_ROOT` / `MITOS_CURSOR_CLI` isolation works on Windows). Cursor is **stubbed** (`e2e/stubs/cursor-agent.cmd` / `.sh`) so CI never spends real tokens.

### Manual Cursor smoke (real CLI — not CI)

Automated tests never spawn a real Cursor agent. One documented manual check:

1. `npm run dev` with a real Cursor CLI on PATH (`agent` / `cursor-agent`) and `agent status` logged in
2. Settings → Cursor CLI status shows **Available**
3. Prefer Settings → Cursor command dry-run preview before a live spawn
4. Follow [playground/README.md](playground/README.md) **Cursor smoke**: import `skills/cursor-smoke` + `rules/cursor-smoke-safety.mdc`, Input = `inputs/cursor-smoke-task.txt`, set Skill runner to Cursor, confirm, Run
5. Activity shows stdout / exit / model; no repo files should be edited

## Project structure

```
mitos-flow/
├── backend/          # FastAPI API (Python)
│   ├── src/mitos_api/
│   └── tests/
├── frontend/         # React UI (Vite + TypeScript)
│   └── src/
├── e2e/              # Playwright regression suite (Phases 20.5 + 31)
├── playground/       # Demo assets for import / manual checks
├── docs/             # Architecture and phase docs
├── MASTER-PLAN.md    # Implementation roadmap
└── package.json      # Root dev scripts
```

## Documentation

- [MASTER-PLAN.md](MASTER-PLAN.md) — full implementation roadmap
- [docs/architecture.md](docs/architecture.md) — frozen v1 contracts
- [docs/implementation-status.md](docs/implementation-status.md) — progress log
- [playground/README.md](playground/README.md) — demo assets and manual smokes
