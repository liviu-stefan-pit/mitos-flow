# Mitos Flow

Visual AI workflow builder — drag-and-drop canvas for chaining local AI engines into executable automation flows.

## Prerequisites

- **Node.js** 20+ and **npm**
- **Python** 3.12+
- **pip** (Python package manager)

## Quick start (Windows)

### 1. Install dependencies

```powershell
# From the repo root
npm install
npm run install:all
```

This installs root dev tools (`concurrently`, Playwright), frontend npm packages, and the backend Python package in editable mode.

### 2. Start development servers

```powershell
npm run dev
```

This starts both services concurrently:

| Service  | URL                        |
| -------- | -------------------------- |
| Frontend | http://localhost:5173      |
| Backend  | http://localhost:8000      |

Press `Ctrl+C` to stop both services.

### 3. Verify

- Open http://localhost:5173 in your browser
- The header should show **Backend connected** (green indicator)
- Health check: `curl http://localhost:8000/api/health` → `{"status":"ok"}`

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `VITE_API_URL` | (empty in Vite dev → same-origin `/api` proxy) | Backend URL for frontend |
| `CORS_ORIGINS` | (localhost regex) | Extra allowed CORS origins (comma-separated) |
| `MITOS_LIBRARY_ROOT` | `.mitos-flow-library` under cwd | Managed Skill/Rules/KB library root (E2E uses a temp dir) |
| `MITOS_OUTPUT_ROOT` | `.mitos-flow-artifacts` under cwd | Approved Artifact Output write root (Phase 25) |

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

# Playwright E2E (Chromium) — Phase 20.5 fake-run harness
npx playwright install chromium
npm run test:e2e

# Full regression (unit + e2e)
npm run test:regression
```

E2E boots its own stack via `npm run dev:e2e` (backend without `--reload` so `MITOS_LIBRARY_ROOT` isolation works on Windows). Prefer stopping other `npm run dev` sessions before `test:e2e`, or set `CI=1` so Playwright does not reuse an existing server.

## Project structure

```
mitos-flow/
├── backend/          # FastAPI API (Python)
│   ├── src/mitos_api/
│   └── tests/
├── frontend/         # React UI (Vite + TypeScript)
│   └── src/
├── e2e/              # Playwright fake-run regression harness (Phase 20.5)
├── playground/       # Demo assets for import / manual checks
├── docs/             # Architecture and phase docs
├── MASTER-PLAN.md    # Implementation roadmap
└── package.json      # Root dev scripts
```

## Documentation

- [MASTER-PLAN.md](MASTER-PLAN.md) — full implementation roadmap
- [docs/architecture.md](docs/architecture.md) — frozen v1 contracts
- [docs/implementation-status.md](docs/implementation-status.md) — progress log