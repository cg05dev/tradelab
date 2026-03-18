# Environment

Environment variables, external dependencies, and setup notes.

**What belongs here:** Required env vars, external API keys/services, dependency quirks, platform-specific notes.
**What does NOT belong here:** Service ports/commands (use `.factory/services.yaml`).

---

## Frontend Environment Variables

- `VITE_API_URL` - Optional override for backend API origin. If unset, frontend uses default local path (assumes backend on localhost:8000).

## Backend Configuration

- `portfolio_config.json` - Persists portfolio size and mode.
- Hyperliquid credentials are read from environment or config (see `backend/hyperliquid_client.py`).

## Python Dependencies

- See `backend/requirements.txt`.
- FastAPI, uvicorn, python-dotenv, and Hyperliquid SDK are primary dependencies.

## Node Dependencies

- See `frontend/package.json`.
- React, Vite, Tailwind CSS are primary dependencies.
- TanStack Router/Query to be added during migration.

## Platform Notes

- Project runs on WSL2 (Linux).
- No Docker currently; local execution only.
