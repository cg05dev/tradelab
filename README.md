# TradeLab

[![CI](https://github.com/cg05dev/tradelab/actions/workflows/ci.yml/badge.svg)](https://github.com/cg05dev/tradelab/actions/workflows/ci.yml)

A self-hosted trading journal and risk planner for crypto perpetuals, with Hyperliquid integration.
You plan a trade by how much of the account you're willing to lose; TradeLab sizes the position,
places the orders, and keeps the journal in step with what actually fills on the exchange.

## Features

- **Risk-first planning**: choose the risk %, entry, leverage, up to 4 take profits and multiple stop
  losses; TradeLab sizes the position so the loss at the stop, fees and slippage included, is exactly
  that risk. Live prices and liquidation estimates update as you type.
- **Hyperliquid trading**: connect an account from Settings with a browser wallet (or by address), then
  trade through an API wallet that can place orders but can't withdraw.
- **A journal that follows the exchange**: take profits and stops that fill on Hyperliquid, even while
  TradeLab is closed, are applied to the journal with their real prices, fees and P&L.
- **Paper trading on real prices**: paper trades are filled against Hyperliquid mainnet prices, with
  the same fees and stop slippage as live, so paper results are a realistic preview.
- **Analytics**: win rate, P&L, profit factor, max drawdown, equity and drawdown charts by timeframe, and
  a searchable, sortable trade history.
- **Paper and live kept apart**: separate journals and balances; the live balance is always the
  connected account's value. Testnet accounts are badged so a test order is never mistaken for a real one.
- **TradingView webhook**: alerts can create sized trades automatically (secret-protected).

## Tech Stack

- **Frontend**: React, TypeScript, Vite, Tailwind CSS, TanStack Router and Query, Recharts
- **Backend**: FastAPI (Python 3.10+), SQLite, the Hyperliquid Python SDK
- **Secrets**: the OS keychain, via `keyring`

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+

### Installation

```bash
git clone https://github.com/cg05dev/tradelab.git
cd tradelab

# Backend
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### Running

```bash
# Terminal 1: the API on http://localhost:8000
cd backend && source venv/bin/activate && python main.py

# Terminal 2: the app on http://localhost:3001 (proxies /api to the backend)
cd frontend && npm run dev
```

On first start, choose **Connect a Hyperliquid account** or **Start paper trading**.

### Connecting Hyperliquid

Open **Settings**:

- **Connect wallet** (or type your address) on mainnet or testnet. This is read-only: from then on the
  live portfolio is the account's value. Live mode needs a connected account.
- **Enable trading**: your browser wallet signs one free message approving a "TradeLab" API wallet,
  which can place and cancel orders but can't withdraw. Or paste the key of an API wallet you created
  on Hyperliquid (More → API). TradeLab refuses your main wallet's key.

The API wallet key is stored in your system keychain (macOS Keychain, Windows Credential Manager, or
Secret Service/KWallet on Linux), never in the database. For extra safety, connect a sub-account that
holds only what you want to trade.

## Configuration

Everything is optional. Put settings in `backend/.env`:

| Variable | Default | Purpose |
|---|---|---|
| `TRADELAB_WEBHOOK_SECRET` | *(unset: webhook off)* | Shared secret for `POST /api/webhook/trade` |
| `TRADELAB_CORS_ORIGINS` | the Vite dev server | Comma-separated origins allowed to call the API |
| `TRADELAB_FILL_SYNC_SECONDS` | `15` | How often live trades are checked against Hyperliquid fills (`0` turns it off) |
| `TRADELAB_PAPER_SIM_SECONDS` | `5` | How often open paper trades are checked against mainnet prices (`0` turns it off) |
| `TRADELAB_DB_FILE` | `backend/tradelab.db` | Location of the SQLite database |
| `TRADELAB_LOG_LEVEL` | `INFO` | `DEBUG` logs order and exchange diagnostics |

On a machine without a keychain (e.g. a headless server), the Hyperliquid connection can be configured
here instead, using an **API wallet** key, never your main wallet's. When set, these take precedence and
Settings shows the connection as read-only:

```env
HYPERLIQUID_ENABLED=true
HYPERLIQUID_WALLET_ADDRESS=0x...   # your account
HYPERLIQUID_PRIVATE_KEY=0x...      # the API wallet's key
HYPERLIQUID_USE_TESTNET=true
```

### TradingView webhook

TradingView alerts can't send custom headers, so put the secret in the alert's JSON body:

```json
{"secret": "some-long-random-string", "asset": "BTC", "direction": "long", "entry": 64000, "sl": 62500, "tp1": 68000, "tp1_alloc": 100, "mode": "paper"}
```

Other callers can send it as an `X-Webhook-Secret` header instead. The API only answers requests
addressed to localhost, so to reach it from TradingView, expose just this path through a tunnel.

## Development

```bash
# Backend: lint and tests
cd backend
pip install -r requirements-dev.txt
ruff check .
pytest

# Frontend: lint, type-check and build
cd frontend
npm run lint
npm run typecheck
npm run build
```

CI runs all of these on every pull request. Tests run against a temporary data directory and an in-memory
keychain with the Hyperliquid client mocked out, so they never touch real money or your data.

### Project Structure

```
tradelab/
├── backend/
│   ├── main.py                # App setup: local-only guard, CORS, routers, background jobs
│   ├── routers/               # One APIRouter per area: trades, analytics, calculations, portfolio,
│   │                          #   mode, hyperliquid, connection, webhook, system
│   ├── storage.py             # SQLite persistence (and the one-time import of old CSV journals)
│   ├── connection.py          # Connected account (SQLite) and API wallet key (OS keychain)
│   ├── hyperliquid_client.py  # Hyperliquid API client: prices, account value, orders, fills, fees
│   ├── fill_sync.py           # Applies Hyperliquid fills to the live journal
│   ├── paper_sim.py           # Fills paper trades against mainnet prices
│   ├── fees.py                # Fee rates and the cost of a stopped-out trade
│   ├── risk.py                # Liquidation estimate
│   ├── models.py              # Shared Pydantic request models
│   └── tests/                 # Pytest suite
├── frontend/src/
│   ├── pages/                 # Trade planner, open trades, analytics, settings
│   ├── components/            # Layout, portfolio header, mode toggle, welcome screen
│   ├── api/                   # Typed API client functions
│   ├── contexts/              # Trading mode
│   ├── trading.ts             # Liquidation estimate (same as backend/risk.py)
│   ├── wallet.ts              # Browser wallet (EIP-1193) helpers
│   └── router.tsx             # Routes and the first-run welcome gate
└── .github/workflows/ci.yml   # CI: backend lint and tests, frontend lint, type-check and build
```

## Design Decisions

- **Risk-first position sizing.** You choose how much of the account to risk, not how big the position
  is. Position notional = risk amount ÷ (distance to the stop + fees + slippage), where the costs are two
  taker fees (entry and stop) and 0.05% of stop slippage. With no stop, the position is sized against the
  estimated liquidation price, `entry × (1 ∓ (1/leverage − 1.25%))`, using Hyperliquid's maintenance
  margin for BTC. Fee rates are your account's (tier and referral discount included) when one is
  connected, otherwise Hyperliquid's base rates.
- **The backend is the safety gate for real money.** The UI hides live actions in paper mode, but the
  API doesn't trust that: order and close endpoints refuse to run unless the persisted mode is `live`,
  and the check fails closed for any other value. Orders are sized from a price the server fetches
  itself, not the price the browser sent.
- **Market orders as IOC limits.** Hyperliquid has no true market order, so entries are
  immediate-or-cancel limits with a 0.2% buffer. Take profits are reduce-only resting limits and stop
  losses are trigger orders, both sized from what actually filled. If any of them is rejected the order
  still returns (the position is open) with `status: "partial"` and a warning per missing order, which
  the UI keeps on screen.
- **Journal what filled, not what was planned.** A live trade is written to the journal only after the
  entry fills, at the fill's average price and size, so a rejected order never leaves a phantom trade.
- **The live journal follows the exchange.** Every 15 seconds the backend reads the account's fills and
  applies them to open live trades: partial take profits, and the real exit price, hold time and P&L
  after fees once a trade is fully closed. Fills of orders TradeLab placed are credited to their own
  trade; others (closes on Hyperliquid's site) are matched by coin, direction and time, oldest trade
  first. Applied fills are recorded, so nothing counts twice.
- **Paper trades fill like live ones.** The simulator checks open paper trades against mainnet mid
  prices, and against one-minute candles so a wick between checks still triggers an exit. Losses are
  checked before profits when both are reached, stops fill with slippage (or at the market price on a
  gap), take profits pay the maker fee, and positions can be liquidated.
- **The live portfolio is the account's value.** Live sizing uses the connected account's equity on
  Hyperliquid; there is no typed-in live balance. Standard accounts read it from the perp balance.
  Unified and portfolio-margin accounts keep USDC in the spot balance, which already includes unrealized
  P&L, so it's read from there (other collateral tokens aren't counted). It's cached for 3 seconds and
  shown as stale if Hyperliquid can't be reached. With no account, or no value fetched yet, live sizing
  is refused rather than guessed.
- **Allocations are fractions.** In the API and the database a take profit or stop loss allocation is
  a fraction of the position (`0.5` = half). Anything outside 0–1 is rejected, so a percentage sent by
  mistake fails loudly instead of sizing an order 50× too large. (The webhook's `tpN_alloc` fields are
  percentages and are converted.)
- **Trade through an API wallet, never the main key.** Enabling trading creates an API wallet in the
  backend and has the browser wallet sign its approval (EIP-712), so the main key never leaves the
  wallet; the backend checks who signed before submitting it. A pasted key must be an approved API
  wallet of the connected account, and a main wallet key is refused. Keys live only in the OS keychain.
- **Only this computer can call the API.** The backend refuses requests not addressed to localhost or
  carrying proxy headers, which blocks DNS rebinding and keeps a tunnel from exposing anything but the
  webhook. Requests that change anything must carry an `X-TradeLab-Client` header, which other websites
  can't add without passing CORS.
- **SQLite, not a database server.** It's a single-user local app, so an embedded database fits: one
  file, nothing to run, part of Python's standard library. Each write is a transaction, and closing a
  trade updates the trade and the paper balance together. Trade ids are scoped to their mode, so an id
  from the paper journal can never touch a live trade.
- **Webhook auth that works with TradingView.** The shared secret travels in the JSON body and is
  compared in constant time. The endpoint is off until a secret is configured.

## API

All endpoints except `/health` and the webhook are local-only, and writes need the `X-TradeLab-Client`
header. Most take an optional `?mode=paper|live` (default: the current mode).

| Area | Endpoints |
|---|---|
| System | `GET /health` |
| Mode | `GET /api/mode`, `POST /api/mode` (`{"mode": "paper" \| "live"}`) |
| Portfolio | `GET /api/portfolio` returns the balance and its `source`: `manual` (paper), `hyperliquid` (live) or `none` (live, no account). `PUT /api/portfolio` sets and `POST /api/portfolio/reset` clears the paper balance. |
| Trades | `GET /api/trades`, `GET /api/trades/open`, `GET /api/trades/closed` (filters: `asset`, `start`, `end`, `search`, `sort`, `page`, `limit`), `POST /api/trades`, `POST /api/trades/close`, `DELETE /api/trades/{id}` |
| Analytics | `GET /api/analytics/metrics?timeframe=`, `GET /api/analytics/pnl-series?timeframe=` |
| Sizing | `POST /api/calculate/position-size` |
| Connection | `GET`, `PUT`, `DELETE /api/connection`; `POST`, `DELETE /api/connection/api-wallet`; `POST /api/connection/api-wallet/prepare` and `/approve` (browser wallet approval) |
| Hyperliquid | `GET /api/hyperliquid/price/{coin}`, `GET /api/hyperliquid/assets`, `GET /api/hyperliquid/fees`, `POST /api/hyperliquid/order`, `POST /api/hyperliquid/close/{coin}` (`{}` closes all, `{"size": 0.02}` that many coin units), `POST /api/hyperliquid/sync` (apply new fills now) |
| Webhook | `POST /api/webhook/trade` |

FastAPI serves interactive documentation of every endpoint at http://localhost:8000/docs.

## License

MIT. See [LICENSE](LICENSE).
