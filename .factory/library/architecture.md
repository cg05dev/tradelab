# Architecture

Architectural decisions, patterns discovered, and structural notes.

**What belongs here:** Key patterns, module boundaries, data flow, architectural decisions made during mission.
**What does NOT belong here:** Environment details (use `environment.md`), service configs (use `services.yaml`).

---

## Current Architecture (Browser-Only)

- **Frontend**: React + Vite + Tailwind, JSX (not TypeScript), no formal routing, no query caching.
- **Backend**: FastAPI with CSV-based trade journal and Hyperliquid SDK integration.
- **Deployment**: Local browser-only (Electron removed).

## Target Architecture

- **Frontend**: React + Vite + TypeScript + TanStack Router + TanStack Query + Tailwind + shadcn/ui.
- **Backend**: FastAPI with mode support (planning/live) and existing Hyperliquid integration.
- **Deployment**: Local browser-only (backend:8000 + frontend:3001).

## Key Patterns

- API client should centralize origin handling; no hardcoded `localhost:8000` in individual modules.
- Mode is a backend concept; frontend reflects mode status but does not enforce it.
- Planning mode = simulation/journal-only; live mode = real Hyperliquid execution.

## Module Boundaries

- `frontend/src/api/` - API client modules
- `frontend/src/components/` - UI components
- `frontend/src/routes/` - Route components (post-migration)
- `backend/` - FastAPI app with Hyperliquid client
