# TradeLab

[![CI](https://github.com/cg05dev/tradelab/actions/workflows/ci.yml/badge.svg)](https://github.com/cg05dev/tradelab/actions/workflows/ci.yml)

A modern, browser-first trading journal application for tracking and analyzing cryptocurrency trades with comprehensive risk management, performance analytics, and Hyperliquid integration.

## Features

- **Trade Planning**: Interactive interface for planning trades with real-time risk analysis and live prices
- **Risk Management**: Automatic position sizing based on risk percentage, leverage, and liquidation estimates
- **Multiple Take Profits**: Up to 4 take profit levels with custom allocations
- **Stop Loss Management**: Multiple stop loss levels with allocation tracking
- **Live Analysis**: Real-time trade analysis as you input parameters
- **Performance Tracking**: Win rate, P&L, profit factor, max drawdown, and win/loss counts
- **Trade Management**: Track open and closed trades with detailed history
- **Analytics Dashboard**: Timeframe filtering, equity/drawdown charts, and trade history with filtering, search, sorting, and pagination
- **Hyperliquid Integration**: Execute trades directly on Hyperliquid DEX, with live prices, positions, and available assets pulled from the public API
- **Paper/Live Mode**: Toggle between paper trading (simulation with separate data) and live trading (real execution)
- **TradingView Webhook**: `POST /api/webhook/trade` lets TradingView alerts create trade plans automatically
- **Browser-First**: Modern React application running entirely in the browser
- **Data Persistence**: All trades automatically saved to CSV (separate files for Paper and Live modes)

## Tech Stack

- **Frontend**: React + TypeScript + Vite + Tailwind CSS
- **Routing**: TanStack Router
- **Data Fetching**: TanStack Query
- **Backend**: FastAPI + Python
- **Data**: CSV-based storage (easy to backup and share)

## Getting Started

### Prerequisites

- Python 3.10+ ([Download](https://www.python.org/downloads/))
- Node.js 18+ ([Download](https://nodejs.org/))

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/cg05dev/tradelab.git
   cd tradelab
   ```

2. **Backend Setup:**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Linux/macOS
   # or: venv\Scripts\activate  # On Windows
   pip install -r requirements.txt
   ```

3. **Frontend Setup:**
   ```bash
   cd frontend
   npm install
   ```

4. **(Optional) Hyperliquid Integration:**

   Copy the `.env` example below into `backend/.env` and fill in your credentials (see `HYPERLIQUID_ARCHITECTURE.md` for details):
   ```env
   HYPERLIQUID_ENABLED=true
   HYPERLIQUID_WALLET_ADDRESS=0x...
   HYPERLIQUID_PRIVATE_KEY=0x...
   HYPERLIQUID_USE_TESTNET=true
   ```
   Without it, the app runs fully in paper mode.

### Running the Application

TradeLab runs as a browser-based application with a backend API server.

**Terminal 1 - Start the Backend:**
```bash
cd backend
source venv/bin/activate  # On Linux/macOS
# or: venv\Scripts\activate  # On Windows
python main.py
```

**Terminal 2 - Start the Frontend:**
```bash
cd frontend
npm run dev
```

The application will be available at **http://localhost:3001**

### Development

- Backend API runs on `http://localhost:8000`
- Frontend dev server runs on `http://localhost:3001`
- API requests are proxied through Vite to the backend

### Testing

```bash
cd backend
source venv/bin/activate
pip install pytest
pytest tests/ -v
```

## Project Structure

```
tradelab/
├── backend/
│   ├── main.py                  # FastAPI backend server
│   ├── trade_calculator.py      # Position sizing and risk/reward calculations
│   ├── hyperliquid_client.py    # Hyperliquid DEX API client
│   ├── tests/                   # Pytest test suite
│   ├── requirements.txt         # Python dependencies
│   ├── trades.csv               # Trade data storage (Live mode, generated at runtime)
│   ├── trades_paper.csv         # Trade data storage (Paper mode, generated at runtime)
│   ├── portfolio_config.json    # Portfolio size (Live mode, generated at runtime)
│   ├── portfolio_paper.json     # Portfolio size (Paper mode, generated at runtime)
│   └── mode_config.json         # Current mode persistence (generated at runtime)
├── frontend/
│   ├── src/
│   │   ├── components/          # Reusable React components
│   │   ├── pages/               # Page components
│   │   ├── api/                 # API client functions
│   │   ├── contexts/            # React contexts (trading mode)
│   │   ├── App.tsx              # Main app component
│   │   └── router.tsx           # TanStack Router setup
│   ├── package.json
│   └── vite.config.js
├── .github/workflows/ci.yml     # CI: backend tests + frontend build
├── HYPERLIQUID_ARCHITECTURE.md  # Hyperliquid integration notes
├── LICENSE
└── README.md                    # This file
```

## API Endpoints

- `GET /health` - Health check
- `GET /api/portfolio` - Get portfolio size
- `PUT /api/portfolio` - Update portfolio size
- `POST /api/portfolio/reset` - Reset portfolio to initial size
- `GET /api/mode` - Get current trading mode (paper/live)
- `POST /api/mode` - Update trading mode
- `GET /api/trades` - Get all trades
- `GET /api/trades/open` - Get open trades
- `GET /api/trades/closed` - Get closed trades with filtering (asset, start, end, sort, page, limit, search)
- `GET /api/trades/closed/count` - Get total closed trades count
- `POST /api/trades` - Add new trade
- `POST /api/trades/close` - Close a trade
- `POST /api/trades/partial-close` - Record TP hit
- `POST /api/trades/stop-loss-hit` - Record SL hit
- `DELETE /api/trades/{trade_index}` - Delete a trade
- `DELETE /api/trades/clear` - Clear all trades
- `POST /api/trades/import` - Import trades from CSV
- `GET /api/analytics/overview` - Get analytics overview
- `GET /api/analytics/metrics?timeframe=` - Performance metrics (total_pnl, win_rate, avg_win, avg_loss, profit_factor, max_drawdown, trade/win/loss counts) by timeframe
- `GET /api/analytics/pnl-series?timeframe=` - Cumulative P&L series for charting
- `POST /api/calculate/position-size` - Calculate position size
- `POST /api/calculate/risk-reward` - Calculate risk/reward ratio
- `POST /api/calculate/profit-loss` - Calculate profit/loss
- `POST /api/calculate/trade-details` - Full trade breakdown (position sizing, TPs, SLs, liquidation)
- `POST /api/webhook/trade` - Create a trade plan from a TradingView alert
- `GET /api/hyperliquid/status` - Hyperliquid integration status
- `GET /api/hyperliquid/price/{coin}` - Current mid price for a coin
- `GET /api/hyperliquid/assets` - Available assets and max leverage
- `GET /api/hyperliquid/positions` - Open positions on Hyperliquid
- `GET /api/hyperliquid/ws-price` - WebSocket price streaming
- `POST /api/hyperliquid/order` - Execute order on Hyperliquid
- `POST /api/hyperliquid/close/{coin}` - Close position on Hyperliquid

## Building for Production

**Frontend:**
```bash
cd frontend
npm run build
```

**Backend:**
The FastAPI backend can be deployed using uvicorn or any ASGI server.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
