# Mitos Flow — Phase Specifications

> Detailed phase specs mirroring MASTER-PLAN.md. Created in Phase 0.

**Last updated:** 2026-07-26

For the authoritative checklist and milestone tracker, see [MASTER-PLAN.md](../MASTER-PLAN.md).

---

## Foundation (Phases 0–3)

### Phase 0 — Freeze contracts and phase gates

**Deliverables:**
- `docs/architecture.md` — node kinds, edge kinds, join policies, InputEnvelope, output modes, v1 non-goals
- `docs/phases.md` — this file
- `docs/implementation-status.md` — running implementation log

**Gate:** Docs have no unresolved choices for Phases 1–5; no application code yet.

**Manual check:** Another reader can implement Phase 1 from docs alone.

---

### Phase 1 — Backend health service

**Deliverables:**
- `backend/pyproject.toml`
- `backend/src/mitos_api/main.py`
- `backend/tests/test_health.py`

**Scope:**
- `GET /api/health` → `{"status":"ok"}`
- No other routes

**Gate:** `pytest` passes; endpoint responds locally.

**Manual check:** `curl http://localhost:8000/api/health` returns OK.

---

### Phase 2 — Frontend shell

**Deliverables:**
- `frontend/` scaffolded with Vite, React, TypeScript, Vitest, React Testing Library
- Mitos header, empty workspace, backend connection status indicator
- No graph canvas yet

**Gate:** Component test passes; page shows backend connected when backend is running.

**Manual check:** Browser shows green/connected status against running backend.

---

### Phase 3 — Unified local development command

**Deliverables:**
- Root `package.json` with `npm run dev` starting frontend + backend
- `README.md` with Windows setup instructions
- Dev CORS on backend
- `VITE_API_URL` environment variable support in frontend

**Gate:** One command starts both services; refresh and shutdown are clean.

**Manual check:** `npm run dev` starts frontend + backend together.

---

## Graph editor (Phases 4–8)

_Specs in MASTER-PLAN.md. Not started._

---

## Shared workflow model (Phases 9–10)

_Specs in MASTER-PLAN.md. Not started._

---

## Deterministic execution (Phases 11–16)

_Specs in MASTER-PLAN.md. Not started._

---

## Reusable local assets (Phases 17–20)

_Specs in MASTER-PLAN.md. Not started._

---

## Cursor CLI adapter (Phases 21–24)

_Specs in MASTER-PLAN.md. Not started._

---

## Artifact outputs & observability (Phases 25–28)

_Specs in MASTER-PLAN.md. Not started._

---

## Portability & hardening (Phases 29–31)

_Specs in MASTER-PLAN.md. Not started._
