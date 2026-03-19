# TradeLab - Mental Model

Last updated: 2026-03-18

## 1) Core Product Thesis

TradeLab exists to collapse three workflows into one: **trade planning**, **execution**, and **post-trade journaling/analytics**.  
The current product proves this for a single venue (Hyperliquid) in a local desktop app. The target product expands this into a **multi-venue perp routing system** that selects the best venue/route for each trade.

## 2) What TradeLab Is Today (Reality)

TradeLab today is a **desktop-first local app**:

- **Frontend:** React + Vite + Tailwind (inside Electron)
- **Backend:** FastAPI (Python)
- **Storage:** local files (`trades.csv`, `portfolio_config.json`)
- **Execution integration:** Hyperliquid via `hyperliquid-python-sdk`

It is currently a hybrid of:
- A trading journal + risk calculator
- A direct exchange execution bridge (Hyperliquid only)

## 3) End-to-End Runtime Model

1. Electron launches and starts backend `backend/main.py`.
2. React app loads and checks `GET /api/portfolio`.
3. User plans trade (direction, leverage, SL, TP, risk).
4. Frontend computes trade details locally for instant feedback.
5. On execute:
   - `POST /api/trades` writes journal row to CSV.
   - `POST /api/hyperliquid/order` places exchange order + TP/SL logic.
6. Open trades page polls price and calculates unrealized P&L.
7. On close:
   - Optional `POST /api/hyperliquid/close/{coin}`
   - `POST /api/trades/close` updates journal and portfolio.

## 4) Domain Model (Current)

- **Portfolio:** single numeric value in JSON
- **Trade record:** CSV row with entry, SL, TP list, status, size, margin, leverage, P&L fields
- **Exchange state:** fetched live from Hyperliquid (prices, positions, asset metadata)

## 5) What Is Strong Right Now

- Very fast local setup and iteration loop
- Tight UX loop between planning and execution
- Practical risk/position sizing UX for discretionary trading
- Working single-venue execution integration with TP/SL handling

## 6) Structural Limits Blocking the Next Vision

- **Monolithic backend** (`main.py`) mixes API + business logic + persistence + exchange orchestration
- **Single-venue coupling** (Hyperliquid-specific assumptions everywhere)
- **File storage limits** (CSV/JSON not robust for multi-user, audit, or route analytics)
- **Desktop-local assumptions** (`localhost`, Electron-managed processes)
- **No unified route abstraction** for quote/score/execute across venues
- **Security/compliance gap** for browser-scale derivatives product (auth, geofencing, policy controls)

## 7) Migration Mental Model (Target)

TradeLab needs to evolve from:

**"Local desktop trading journal with one execution adapter"**

to:

**"Browser-first routing platform with venue adapters, deterministic scoring, and later ML ranking."**

## 8) Key Product Principles Going Forward

1. **Deterministic router first, ML second** (collect quality data before training)
2. **One-chain focused MVP** before bridge/cross-chain complexity
3. **Venue adapter architecture** (normalized quote/fee/liquidity/funding model)
4. **Execution + journal atomicity** (single orchestration path)
5. **Compliance and geolocation controls treated as core infrastructure**

## 9) Related Notes

- [[TradeLab - Plan Critique and Revised Roadmap]]
- [[TradeLab - Market and Architecture Research (2026-03-18)]]
