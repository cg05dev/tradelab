# TradeLab

A modern, browser-first trading journal application for tracking and analyzing cryptocurrency trades with comprehensive risk management, performance analytics, and Hyperliquid integration.

## Features

- **Trade Planning**: Interactive interface for planning trades with real-time risk analysis
- **Risk Management**: Automatic position sizing based on risk percentage and leverage
- **Multiple Take Profits**: Up to 4 take profit levels with custom allocations
- **Stop Loss Management**: Multiple stop loss levels with allocation tracking
- **Live Analysis**: Real-time trade analysis as you input parameters
- **Performance Tracking**: Comprehensive analytics with win rate, P&L, and profit factor
- **Trade Management**: Track open and closed trades with detailed history
- **Hyperliquid Integration**: Execute trades directly on Hyperliquid DEX
- **Paper/Live Mode**: Toggle between paper trading (simulation with separate data) and live trading (real execution)
- **Browser-First**: Modern React application running entirely in the browser
- **Data Persistence**: All trades automatically saved to CSV (separate files for Paper and Live modes)
- **Two-Tab Navigation**: Simplified navigation with Trade and Analytics tabs
- **Analytics Dashboard**: Performance metrics with timeframe filtering, P&L chart, and trade history with filtering/search/pagination

## Tech Stack

- **Frontend**: React + TypeScript + Vite + Tailwind CSS
- **Routing**: TanStack Router
- **Data Fetching**: TanStack Query
- **Backend**: FastAPI + Python
- **Data**: CSV-based storage (easy to backup and share)

## Getting Started

### Prerequisites

- Python 3.8+ ([Download](https://www.python.org/downloads/))
- Node.js 16+ ([Download](https://nodejs.org/))

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
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

## Project Structure

```
tradelab/
├── backend/
│   ├── main.py              # FastAPI backend server
│   ├── requirements.txt     # Python dependencies
│   ├── trades.csv          # Trade data storage (Live mode)
│   ├── trades_paper.csv    # Trade data storage (Paper mode)
│   ├── portfolio_config.json # Portfolio configuration (Live mode)
│   ├── portfolio_paper.json # Portfolio configuration (Paper mode)
│   └── mode_config.json    # Current mode persistence
├── frontend/
│   ├── src/
│   │   ├── components/     # Reusable React components
│   │   ├── pages/          # Page components
│   │   ├── api/            # API client functions
│   │   └── App.jsx         # Main app component
│   ├── package.json
│   └── vite.config.js
└── README.md               # This file
```

## API Endpoints

- `GET /api/portfolio` - Get portfolio size
- `PUT /api/portfolio` - Update portfolio size
- `GET /api/mode` - Get current trading mode (paper/live)
- `PUT /api/mode` - Update trading mode
- `GET /api/trades` - Get all trades
- `GET /api/trades/open` - Get open trades
- `GET /api/trades/closed` - Get closed trades with filtering (asset, start, end, sort, page, limit, search)
- `GET /api/trades/closed/count` - Get total closed trades count
- `POST /api/trades` - Add new trade
- `POST /api/trades/close` - Close a trade
- `POST /api/trades/partial-close` - Record TP hit
- `POST /api/trades/stop-loss-hit` - Record SL hit
- `DELETE /api/trades/{index}` - Delete a trade
- `DELETE /api/trades/clear` - Clear all trades
- `POST /api/trades/import` - Import trades from CSV
- `GET /api/analytics/overview` - Get analytics overview
- `GET /api/analytics/metrics?timeframe=` - Get performance metrics (total_pnl, win_rate, avg_win, avg_loss) by timeframe
- `GET /api/analytics/pnl-series?timeframe=` - Get cumulative P&L series for charting
- `POST /api/calculate/position-size` - Calculate position size
- `POST /api/calculate/risk-reward` - Calculate risk/reward ratio
- `POST /api/calculate/profit-loss` - Calculate profit/loss
- `POST /api/hyperliquid/order` - Execute order on Hyperliquid (blocked in planning mode)
- `POST /api/hyperliquid/close/{coin}` - Close position on Hyperliquid (blocked in planning mode)

## Building for Production

**Frontend:**
```bash
cd frontend
npm run build
```

**Backend:**
The FastAPI backend can be deployed using uvicorn or any ASGI server.

## License

MIT

