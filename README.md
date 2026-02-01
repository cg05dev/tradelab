# TradeLab

A modern, clean trading journal application for tracking and analyzing cryptocurrency trades with comprehensive risk management and performance analytics.

> **🚀 Quick Start**: Clone the repo, run `build_setup_exe.bat`, then double-click `TradeLab-Setup.exe`!

## Features

- **Trade Planning**: Interactive interface for planning trades with real-time risk analysis
- **Risk Management**: Automatic position sizing based on risk percentage and leverage
- **Multiple Take Profits**: Up to 4 take profit levels with custom allocations
- **Stop Loss Management**: Multiple stop loss levels with allocation tracking
- **Live Analysis**: Real-time trade analysis as you input parameters
- **Performance Tracking**: Comprehensive analytics with win rate, P&L, and profit factor
- **Trade Management**: Track open and closed trades with detailed history
- **Data Persistence**: All trades automatically saved to CSV
- **Modern UI**: Clean, minimal interface with smooth animations

## Tech Stack

- **Frontend**: React + Vite + Tailwind CSS
- **Backend**: FastAPI + Python
- **Data**: CSV-based storage (easy to backup and share)

## Getting Started

### Step 1: Clone the Repository

```bash
git clone <repository-url>
cd tradelab
```

### Step 2: Choose Your Setup Method

**Option A: Build Setup Executable (Recommended for End Users)**

1. **Build the setup executable:**
   ```bash
   build_setup_exe.bat
   ```

2. **Copy the executable to project root:**
   - The executable is created in `dist\TradeLab-Setup.exe`
   - Copy it to the project root (same folder as `backend` and `frontend`)

3. **Run the setup:**
   - Double-click `TradeLab-Setup.exe`
   - It will install all dependencies and create a desktop shortcut
   - Wait for setup to complete (~2-3 minutes)

4. **Launch the app:**
   - Double-click the "TradeLab" shortcut on your desktop
   - Or run `start-tradelab-desktop.bat`

**Option B: Manual Setup (For Developers)**

If you prefer to set up manually or don't want to build the .exe:

**Prerequisites:**
- Python 3.8+ ([Download](https://www.python.org/downloads/))
- Node.js 16+ ([Download](https://nodejs.org/))

1. **Backend Setup:**
   ```bash
   cd backend
   python -m venv venv
   venv\Scripts\activate  # On Windows
   pip install -r requirements.txt
   ```

2. **Frontend Setup:**
   ```bash
   cd frontend
   npm install
   ```

3. **Launch the app:**
   ```bash
   # From project root
   start-tradelab-desktop.bat
   ```
   
   Or for development mode:
   ```bash
   # Terminal 1: Start backend
   cd backend
   venv\Scripts\activate
   python main.py
   
   # Terminal 2: Start frontend
   cd frontend
   npm run dev
   ```
   
   The app will be available at `http://localhost:5173` (development) or as a desktop app (using the launcher)

## Project Structure

```
tradelab/
├── backend/
│   ├── main.py              # FastAPI backend server
│   ├── requirements.txt     # Python dependencies
│   ├── trades.csv          # Trade data storage
│   └── portfolio_config.json # Portfolio configuration
├── frontend/
│   ├── src/
│   │   ├── components/     # Reusable React components
│   │   ├── pages/          # Page components
│   │   ├── api/            # API client functions
│   │   └── App.jsx         # Main app component
│   ├── package.json
│   └── vite.config.js
├── start-dev.bat           # Development launcher (Windows)
└── README.md               # This file
```

## API Endpoints

- `GET /api/portfolio` - Get portfolio size
- `PUT /api/portfolio` - Update portfolio size
- `GET /api/trades` - Get all trades
- `GET /api/trades/open` - Get open trades
- `GET /api/trades/closed` - Get closed trades
- `POST /api/trades` - Add new trade
- `POST /api/trades/close` - Close a trade
- `POST /api/trades/partial-close` - Record TP hit
- `POST /api/trades/stop-loss-hit` - Record SL hit
- `DELETE /api/trades/{index}` - Delete a trade
- `DELETE /api/trades/clear` - Clear all trades
- `POST /api/trades/import` - Import trades from CSV
- `GET /api/analytics/overview` - Get analytics overview
- `POST /api/calculate/position-size` - Calculate position size
- `POST /api/calculate/risk-reward` - Calculate risk/reward ratio
- `POST /api/calculate/profit-loss` - Calculate profit/loss

## Development

### Building Setup Executable

To create `TradeLab-Setup.exe`:

1. **Run the build script:**
   ```bash
   build_setup_exe.bat
   ```

2. **Copy the executable:**
   - The executable will be created in `dist\TradeLab-Setup.exe`
   - Copy it to the project root directory (same folder as `backend` and `frontend`)

**Manual build:**
```bash
python -m pip install pyinstaller pywin32
python -m PyInstaller --onefile --name "TradeLab-Setup" --console --icon "frontend\assets\icon.ico" setup.py
```

### Building for Production

**Frontend:**
```bash
cd frontend
npm run build
```

**Backend:**
The FastAPI backend can be deployed using uvicorn or any ASGI server.

## License

MIT

