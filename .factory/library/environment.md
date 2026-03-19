# Environment

Environment variables, external dependencies, and setup notes.

## Backend (.env)

Located at `backend/.env`:
- `HYPERLIQUID_WALLET_ADDRESS` - Wallet for Hyperliquid API
- `HYPERLIQUID_PRIVATE_KEY` - Private key for signing requests

## Frontend

No environment variables required. Vite dev server proxies API requests.

## Data Files

- `backend/trades.csv` - Trade journal (CSV format)
- `backend/portfolio_config.json` - Portfolio size and mode state

## Running the App

```bash
# Backend (already running on port 8000)
cd backend && source venv/bin/activate && python main.py

# Frontend (already running on port 3001)
cd frontend && npm run dev
```

## Mode System

- `GET /api/mode` - Returns current mode: "planning" or "live"
- `POST /api/mode` - Set mode: `{"mode": "live"}`
- Planning mode: Blocks Hyperliquid order execution
- Live mode: Enables real trading
