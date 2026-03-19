"""
FastAPI Backend for TradeLab
Handles all trading journal logic and data persistence
"""

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
import pandas as pd
import json
from datetime import datetime
import os
import math
import io
import traceback
import asyncio
import time
from threading import Thread

# Import Hyperliquid client
try:
    from hyperliquid_client import hl_client
except ImportError:
    hl_client = None

# Import Trade Calculator
from trade_calculator import trade_calc, TradeCalculator

app = FastAPI(title="TradeLab API")

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins in development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class TakeProfit(BaseModel):
    price: float
    allocation: float

class StopLoss(BaseModel):
    price: float
    allocation: float

class TradeData(BaseModel):
    asset: str
    direction: str
    entry_price: float
    stop_loss: float
    position_size: float
    take_profits: List[TakeProfit]
    stop_losses: List[StopLoss]
    thesis: Optional[str] = None
    margin: Optional[float] = None
    leverage: Optional[int] = None

class PositionSizeRequest(BaseModel):
    entry_price: float
    stop_loss: float
    leverage: float
    direction: str
    risk_percentage: Optional[float] = None

class CloseTradeRequest(BaseModel):
    trade_index: int
    exit_price: float

class PartialCloseRequest(BaseModel):
    trade_index: int
    tp_price: float
    tp_allocation: float
    tp_index: int

class StopLossHitRequest(BaseModel):
    trade_index: int
    sl_price: float
    sl_allocation: float
    sl_index: int

class UpdatePortfolioRequest(BaseModel):
    portfolio_size: float

# Configuration
BASE_DIR = os.path.dirname(__file__)
MODE_FILE = os.path.join(BASE_DIR, 'mode_config.json')
DATA_FILES = {
    'live': {
        'trades': os.path.join(BASE_DIR, 'trades.csv'),
        'portfolio': os.path.join(BASE_DIR, 'portfolio_config.json'),
    },
    'paper': {
        'trades': os.path.join(BASE_DIR, 'trades_paper.csv'),
        'portfolio': os.path.join(BASE_DIR, 'portfolio_paper.json'),
    },
}
DEFAULT_MODE = 'live'
RISK_PCT = 0.02

JOURNAL_COLUMNS = [
    'Date', 'Asset', 'Direction', 'Entry', 'SL', 'TPs', 'SLs', 'Position_Size',
    'Confirmations', 'Thesis', 'Status', 'Exit_Price', 'P&L', 'Hold_Time',
    'TP_Hit', 'TP_Price', 'SL_Hit', 'SL_Price', 'Hit_TPs', 'Margin', 'Leverage'
]

def _normalize_mode(mode: Optional[str] = None):
    if mode in DATA_FILES:
        return mode
    return load_mode() if mode is None else DEFAULT_MODE


def _get_mode_file(mode: Optional[str] = None):
    current_mode = _normalize_mode(mode)
    return DATA_FILES[current_mode]

def _ensure_paper_files_exist():
    paper_files = DATA_FILES['paper']
    if not os.path.exists(paper_files['trades']):
        pd.DataFrame(columns=JOURNAL_COLUMNS).to_csv(paper_files['trades'], index=False)
    if not os.path.exists(paper_files['portfolio']):
        with open(paper_files['portfolio'], 'w') as f:
            json.dump({'portfolio_size': 0}, f)

def load_trades(mode: Optional[str] = None):
    """Load trades from CSV for the selected mode"""
    try:
        files = _get_mode_file(mode)
        if mode == 'paper':
            _ensure_paper_files_exist()
        if os.path.exists(files['trades']):
            df = pd.read_csv(files['trades'])
            if 'Hit_TPs' not in df.columns:
                df['Hit_TPs'] = [json.dumps([]) for _ in range(len(df))]
            if 'SLs' not in df.columns:
                df['SLs'] = [json.dumps([]) for _ in range(len(df))]
            return df
        return pd.DataFrame(columns=JOURNAL_COLUMNS)
    except Exception:
        return pd.DataFrame(columns=JOURNAL_COLUMNS)

def save_trades(df, mode: Optional[str] = None):
    """Save trades to CSV for the selected mode"""
    files = _get_mode_file(mode)
    if mode == 'paper':
        _ensure_paper_files_exist()
    df.to_csv(files['trades'], index=False)

def load_portfolio_size(mode: Optional[str] = None):
    """Load portfolio size from config for the selected mode"""
    try:
        files = _get_mode_file(mode)
        if mode == 'paper':
            _ensure_paper_files_exist()
        if os.path.exists(files['portfolio']):
            with open(files['portfolio'], 'r') as f:
                config = json.load(f)
                return config.get('portfolio_size', 0)
        return 0
    except Exception:
        return 0

def save_portfolio_size(size, mode: Optional[str] = None):
    """Save portfolio size to config for the selected mode"""
    files = _get_mode_file(mode)
    if mode == 'paper':
        _ensure_paper_files_exist()
    with open(files['portfolio'], 'w') as f:
        json.dump({'portfolio_size': size}, f)

def load_mode():
    """Load trading mode from dedicated mode config, defaults to live."""
    try:
        if os.path.exists(MODE_FILE):
            with open(MODE_FILE, 'r') as f:
                config = json.load(f)
                mode = _normalize_mode_value(config.get('mode', DEFAULT_MODE)) or DEFAULT_MODE
                if mode not in DATA_FILES:
                    mode = DEFAULT_MODE
                if config.get('mode') != mode:
                    with open(MODE_FILE, 'w') as wf:
                        json.dump({'mode': mode}, wf)
                return mode
        with open(MODE_FILE, 'w') as f:
            json.dump({'mode': DEFAULT_MODE}, f)
        return DEFAULT_MODE
    except Exception as e:
        print(f"[WARNING] Error loading mode: {e}, defaulting to live")
        try:
            with open(MODE_FILE, 'w') as f:
                json.dump({'mode': DEFAULT_MODE}, f)
        except Exception:
            pass
        return DEFAULT_MODE

def save_mode(mode):
    """Save trading mode to dedicated config"""
    try:
        with open(MODE_FILE, 'w') as f:
            json.dump({'mode': mode}, f)
    except Exception as e:
        print(f"[ERROR] Error saving mode: {e}")

def apply_timeframe_filter(df, timeframe):
    timeframe = (timeframe or 'all').lower()
    if df.empty or 'Date' not in df.columns:
        return df
    now = pd.Timestamp.now(tz=None)
    if timeframe == 'all':
        return df
    if timeframe == '7d':
        return df[df['Date'] >= now - pd.Timedelta(days=7)]
    if timeframe == '30d':
        return df[df['Date'] >= now - pd.Timedelta(days=30)]
    if timeframe == '90d':
        return df[df['Date'] >= now - pd.Timedelta(days=90)]
    if timeframe == 'ytd':
        start = pd.Timestamp(year=now.year, month=1, day=1)
        return df[df['Date'] >= start]
    if timeframe == '1y':
        return df[df['Date'] >= now - pd.Timedelta(days=365)]
    return df

def clean_trade_data(df):
    """Clean DataFrame by replacing NaN, inf, -inf with None and converting to dict"""
    # Replace NaN, inf, -inf with None for JSON serialization
    df = df.replace([float('inf'), float('-inf')], None)
    df = df.where(pd.notnull(df), None)
    
    # Convert to dict and clean up None values
    trades_list = df.to_dict('records')
    
    # Convert None to appropriate defaults for numeric fields
    for trade in trades_list:
        for key, value in trade.items():
            # Skip _index field - it's a special field for tracking the original DataFrame index
            if key == '_index':
                continue
            if value is None or (isinstance(value, float) and (pd.isna(value) or math.isinf(value))):
                if key in ['Entry', 'SL', 'Position_Size', 'Exit_Price', 'P&L']:
                    trade[key] = 0.0
                elif key in ['TP_Hit', 'SL_Hit']:
                    trade[key] = False
                else:
                    trade[key] = None
    
    return trades_list

# API Routes

@app.get("/")
def read_root():
    return {"message": "TradeLab API"}

@app.get("/health")
def health_check():
    """Health check endpoint for faster startup detection"""
    return {"status": "ok"}

@app.post("/api/shutdown")
def shutdown():
    """Shutdown endpoint (called when frontend closes)"""
    # Note: This is informational - actual shutdown should be done via the launcher
    return {"message": "Shutdown signal received"}

@app.post("/api/portfolio/reset")
def reset_portfolio():
    """Reset portfolio configuration file"""
    try:
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)
            return {"message": "Portfolio reset successfully"}
        return {"message": "Portfolio file does not exist"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resetting portfolio: {str(e)}")

@app.get("/api/portfolio")
def get_portfolio(mode: Optional[str] = None):
    """Get current portfolio size"""
    return {"portfolio_size": load_portfolio_size(mode)}

@app.put("/api/portfolio")
def update_portfolio(request: UpdatePortfolioRequest, mode: Optional[str] = None):
    """Update portfolio size"""
    if request.portfolio_size < 0:
        raise HTTPException(status_code=400, detail="Portfolio size cannot be negative")
    save_portfolio_size(request.portfolio_size, mode)
    return {"portfolio_size": request.portfolio_size, "message": "Portfolio size updated"}

class ModeUpdateRequest(BaseModel):
    mode: str


def _normalize_mode_value(mode: str) -> str:
    aliases = {
        'planning': 'paper',
        'paper': 'paper',
        'live': 'live',
    }
    return aliases.get((mode or '').lower(), '')

@app.get("/api/mode")
def get_mode():
    """Get current trading mode"""
    return {"mode": load_mode()}

@app.post("/api/mode")
def update_mode(request: ModeUpdateRequest):
    """Update trading mode"""
    normalized_mode = _normalize_mode_value(request.mode)
    if not normalized_mode:
        raise HTTPException(
            status_code=400, 
            detail="Invalid mode '%s'. Valid modes are: paper, live" % request.mode
        )
    save_mode(normalized_mode)
    return {"mode": normalized_mode, "message": f"Mode updated to '{normalized_mode}'"}

@app.get("/api/trades")
def get_trades(mode: Optional[str] = None):
    """Get all trades"""
    try:
        current_mode = mode or load_mode()
        df = load_trades(current_mode)
        if df.empty:
            return {"trades": []}
        
        trades_list = clean_trade_data(df)
        return {"trades": trades_list}
    except Exception as e:
        print(f"Error in get_trades: {e}")
        traceback.print_exc()
        return {"trades": []}

@app.get("/api/trades/open")
def get_open_trades(mode: Optional[str] = None):
    """Get open trades only"""
    try:
        current_mode = mode or load_mode()
        df = load_trades(current_mode)
        if df.empty:
            return {"trades": []}
        if 'Status' not in df.columns:
            return {"trades": []}
        open_trades = df[df['Status'] == 'Open']
        
        # Clean trade data (handles NaN, inf, -inf)
        trades_list = clean_trade_data(open_trades)
        # Add the original DataFrame index to each trade
        for idx, trade in enumerate(trades_list):
            # Get the actual row index from the filtered DataFrame
            original_index = open_trades.index[idx]
            trade['_index'] = int(original_index)
        
        return {"trades": trades_list}
    except Exception as e:
        print(f"Error in get_open_trades: {e}")
        traceback.print_exc()
        return {"trades": []}

@app.get("/api/trades/closed")
def get_closed_trades(asset=None, start=None, end=None, sort=None, page=None, limit=None, search=None, mode: Optional[str] = None):
    """Get closed trades with optional filtering, sorting, and pagination"""
    try:
        df = load_trades(normalized_mode)
        if df.empty or 'Status' not in df.columns:
            return {"trades": []}

        closed_trades = df[df['Status'] == 'Closed'].copy()

        
        if asset:
            closed_trades = closed_trades[closed_trades['Asset'].astype(str).str.contains(asset, case=False, na=False)]

        if start:
            start_dt = pd.to_datetime(start, errors='coerce')
            if pd.notna(start_dt):
                closed_trades = closed_trades[pd.to_datetime(closed_trades['Date'], errors='coerce') >= start_dt]

        if end:
            end_dt = pd.to_datetime(end, errors='coerce')
            if pd.notna(end_dt):
                closed_trades = closed_trades[pd.to_datetime(closed_trades['Date'], errors='coerce') <= end_dt]

        if search:
            search_lower = search.lower()
            mask = closed_trades['Asset'].astype(str).str.lower().str.contains(search_lower, na=False)
            if 'Thesis' in closed_trades.columns:
                mask = mask | closed_trades['Thesis'].astype(str).str.lower().str.contains(search_lower, na=False)
            closed_trades = closed_trades[mask]

        if sort == 'pnl_desc':
            closed_trades = closed_trades.sort_values(by='P&L', ascending=False)
        elif sort == 'pnl_asc':
            closed_trades = closed_trades.sort_values(by='P&L', ascending=True)
        elif sort == 'date_desc':
            closed_trades = closed_trades.sort_values(by='Date', ascending=False)
        elif sort == 'date_asc':
            closed_trades = closed_trades.sort_values(by='Date', ascending=True)
        else:
            closed_trades = closed_trades.sort_values(by='Date', ascending=False)

        total_count = len(closed_trades)
        if page is not None or limit is not None:
            try:
                page_num = max(int(page or 1), 1)
            except Exception:
                page_num = 1
            try:
                limit_num = max(int(limit or 25), 1)
            except Exception:
                limit_num = 25
            start_idx = (page_num - 1) * limit_num
            end_idx = start_idx + limit_num
            closed_trades = closed_trades.iloc[start_idx:end_idx]

        trades_list = clean_trade_data(closed_trades)
        for idx, trade in enumerate(trades_list):
            trade['_index'] = int(closed_trades.index[idx])

        return {"trades": trades_list, "count": total_count}
    except Exception as e:
        print(f"Error in get_closed_trades: {e}")
        traceback.print_exc()
        return {"trades": [], "count": 0}

@app.get("/api/trades/closed/count")
def get_closed_trades_count(mode: Optional[str] = None):
    try:
        current_mode = mode or load_mode()
        df = load_trades(current_mode)
        if df.empty or 'Status' not in df.columns:
            return {"count": 0}
        return {"count": int((df['Status'] == 'Closed').sum())}
    except Exception as e:
        print(f"Error in get_closed_trades_count: {e}")
        traceback.print_exc()
        return {"count": 0}

@app.get("/api/analytics/metrics")
def get_analytics_metrics(timeframe: str = 'all', mode: Optional[str] = None):
    try:
        current_mode = mode or load_mode()
        df = load_trades(current_mode)
        if df.empty or 'Status' not in df.columns:
            return {"total_pnl": 0, "win_rate": 0, "avg_win": 0, "avg_loss": 0}
        closed = df[df['Status'] == 'Closed'].copy()
        if closed.empty:
            return {"total_pnl": 0, "win_rate": 0, "avg_win": 0, "avg_loss": 0}
        closed['Date'] = pd.to_datetime(closed['Date'], errors='coerce')
        closed = apply_timeframe_filter(closed, timeframe)
        pnl_series = pd.to_numeric(closed['P&L'], errors='coerce').fillna(0)
        total_pnl = float(pnl_series.sum())
        wins = pnl_series[pnl_series > 0]
        losses = pnl_series[pnl_series < 0]
        win_rate = float(len(wins) / len(pnl_series) * 100) if len(pnl_series) else 0
        avg_win = float(wins.mean()) if len(wins) else 0
        avg_loss = float(losses.mean()) if len(losses) else 0
        return {"total_pnl": total_pnl, "win_rate": win_rate, "avg_win": avg_win, "avg_loss": avg_loss}
    except Exception as e:
        print(f"Error in get_analytics_metrics: {e}")
        traceback.print_exc()
        return {"total_pnl": 0, "win_rate": 0, "avg_win": 0, "avg_loss": 0}

@app.get("/api/analytics/pnl-series")
def get_pnl_series(timeframe: str = 'all', mode: Optional[str] = None):
    try:
        current_mode = mode or load_mode()
        df = load_trades(current_mode)
        if df.empty or 'Status' not in df.columns:
            return []
        closed = df[df['Status'] == 'Closed'].copy()
        if closed.empty:
            return []
        closed['Date'] = pd.to_datetime(closed['Date'], errors='coerce')
        closed = apply_timeframe_filter(closed, timeframe)
        if closed.empty:
            return []
        closed = closed.sort_values('Date')
        closed['P&L'] = pd.to_numeric(closed['P&L'], errors='coerce').fillna(0)
        closed['cumulative_pnl'] = closed['P&L'].cumsum()
        return [
            {'date': row['Date'].strftime('%Y-%m-%d') if pd.notna(row['Date']) else None, 'cumulative_pnl': float(row['cumulative_pnl'])}
            for _, row in closed.iterrows()
        ]
    except Exception as e:
        print(f"Error in get_pnl_series: {e}")
        traceback.print_exc()
        return []

@app.post("/api/trades")
def add_trade(trade_data: TradeData, mode: Optional[str] = None):
    """Add a new trade"""
    try:
        current_mode = mode or load_mode()
        # Validation
        if trade_data.entry_price <= 0:
            raise HTTPException(status_code=400, detail="Entry price must be greater than 0")
        
        if trade_data.direction.lower() not in ['long', 'short']:
            raise HTTPException(status_code=400, detail="Direction must be 'long' or 'short'")
        
        # Validate stop loss
        if trade_data.stop_loss > 0:
            if trade_data.direction.lower() == 'long' and trade_data.stop_loss >= trade_data.entry_price:
                raise HTTPException(status_code=400, detail="Stop loss must be below entry price for long positions")
            if trade_data.direction.lower() == 'short' and trade_data.stop_loss <= trade_data.entry_price:
                raise HTTPException(status_code=400, detail="Stop loss must be above entry price for short positions")
        
        # Validate take profits
        for tp in trade_data.take_profits:
            if tp.price > 0:
                if trade_data.direction.lower() == 'long' and tp.price <= trade_data.entry_price:
                    raise HTTPException(status_code=400, detail=f"Take profit {tp.price} must be above entry price for long positions")
                if trade_data.direction.lower() == 'short' and tp.price >= trade_data.entry_price:
                    raise HTTPException(status_code=400, detail=f"Take profit {tp.price} must be below entry price for short positions")
        
        df = load_trades(current_mode)
        
        new_trade = {
            'Date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'Asset': trade_data.asset.strip(),
            'Direction': trade_data.direction.lower(),
            'Entry': float(trade_data.entry_price),
            'SL': float(trade_data.stop_loss) if trade_data.stop_loss > 0 else 0.0,
            'TPs': json.dumps([tp.dict() for tp in trade_data.take_profits]),
            'SLs': json.dumps([sl.dict() for sl in trade_data.stop_losses]),
            'Position_Size': float(trade_data.position_size),
            'Thesis': str(trade_data.thesis) if trade_data.thesis else '',
            'Status': 'Open',
            'Exit_Price': None,
            'P&L': 0.0,
            'Hold_Time': None,
            'TP_Hit': False,
            'TP_Price': None,
            'SL_Hit': False,
            'SL_Price': None,
            'Hit_TPs': json.dumps([]),
            'Margin': float(trade_data.margin) if trade_data.margin is not None else float(trade_data.position_size) / int(trade_data.leverage) if trade_data.leverage else 0.0,
            'Leverage': int(trade_data.leverage) if trade_data.leverage else 1
        }
        
        df = pd.concat([df, pd.DataFrame([new_trade])], ignore_index=True)
        save_trades(df, current_mode)
        
        return {"message": "Trade added successfully", "trade_index": len(df) - 1}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trades/close")
def close_trade(request: CloseTradeRequest, mode: Optional[str] = None):
    """Close a trade"""
    current_mode = mode or load_mode()
    df = load_trades(current_mode)
    
    # Use loc for actual DataFrame index (not positional)
    if request.trade_index not in df.index:
        raise HTTPException(status_code=400, detail=f"Invalid trade index: {request.trade_index}. Valid indices: {list(df.index)}")
    
    trade = df.loc[request.trade_index]
    
    if trade['Status'] != 'Open':
        raise HTTPException(status_code=400, detail="Trade is already closed")
    
    # Calculate P&L
    entry_price = trade['Entry']
    direction = trade['Direction']
    
    if direction == 'long':
        pnl = (request.exit_price - entry_price) / entry_price * trade['Position_Size']
    else:
        pnl = (entry_price - request.exit_price) / entry_price * trade['Position_Size']
    
    # Calculate hold time
    entry_date = pd.to_datetime(trade['Date'])
    exit_date = datetime.now()
    hold_time = (exit_date - entry_date).total_seconds() / 3600
    
    # Update trade
    df.at[request.trade_index, 'Status'] = 'Closed'
    df.at[request.trade_index, 'Exit_Price'] = request.exit_price
    df.at[request.trade_index, 'P&L'] = pnl
    df.at[request.trade_index, 'Hold_Time'] = f"{hold_time:.1f}h"
    
    # Update portfolio size
    portfolio_size = load_portfolio_size(current_mode)
    new_portfolio_size = portfolio_size + pnl
    save_portfolio_size(new_portfolio_size, current_mode)
    
    save_trades(df, current_mode)
    
    return {
        "message": "Trade closed successfully",
        "pnl": pnl,
        "new_portfolio_size": new_portfolio_size
    }

@app.post("/api/trades/partial-close")
def partial_close_trade(request: PartialCloseRequest, mode: Optional[str] = None):
    """Partially close a trade at TP"""
    current_mode = mode or load_mode()
    df = load_trades(current_mode)
    
    # Use loc for actual DataFrame index (not positional)
    if request.trade_index not in df.index:
        raise HTTPException(status_code=400, detail=f"Invalid trade index: {request.trade_index}. Valid indices: {list(df.index)}")
    
    trade = df.loc[request.trade_index]
    
    if trade['Status'] != 'Open':
        raise HTTPException(status_code=400, detail="Trade is already closed")
    
    # Calculate P&L for allocated portion
    entry_price = trade['Entry']
    direction = trade['Direction']
    total_position_size = trade['Position_Size']
    allocated_position_size = total_position_size * request.tp_allocation
    
    if direction == 'long':
        pnl = (request.tp_price - entry_price) / entry_price * allocated_position_size
    else:
        pnl = (entry_price - request.tp_price) / entry_price * allocated_position_size
    
    # Update portfolio size
    portfolio_size = load_portfolio_size(current_mode)
    new_portfolio_size = portfolio_size + pnl
    save_portfolio_size(new_portfolio_size, current_mode)
    
    # Update position size
    remaining_position_size = total_position_size - allocated_position_size
    
    df.at[request.trade_index, 'Position_Size'] = remaining_position_size
    df.at[request.trade_index, 'TP_Hit'] = True
    df.at[request.trade_index, 'TP_Price'] = request.tp_price
    
    # Track hit TPs
    hit_tps = json.loads(trade['Hit_TPs']) if trade['Hit_TPs'] else []
    hit_tps.append(request.tp_index)
    df.at[request.trade_index, 'Hit_TPs'] = json.dumps(hit_tps)
    
    # Update cumulative P&L
    current_pnl = trade['P&L'] if pd.notna(trade['P&L']) else 0.0
    df.at[request.trade_index, 'P&L'] = current_pnl + pnl
    
    # Check if should fully close
    all_tps = json.loads(trade['TPs']) if trade['TPs'] else []
    is_last_tp = (request.tp_index == len(all_tps) - 1) or (len(all_tps) == 1)
    
    if is_last_tp or remaining_position_size < total_position_size * 0.01:
        # Close completely
        if direction == 'long':
            remaining_pnl = (request.tp_price - entry_price) / entry_price * remaining_position_size
        else:
            remaining_pnl = (entry_price - request.tp_price) / entry_price * remaining_position_size
        
        entry_date = pd.to_datetime(trade['Date'])
        exit_date = datetime.now()
        hold_time = (exit_date - entry_date).total_seconds() / 3600
        
        df.at[request.trade_index, 'Status'] = 'Closed'
        df.at[request.trade_index, 'Exit_Price'] = request.tp_price
        df.at[request.trade_index, 'P&L'] = current_pnl + pnl + remaining_pnl
        df.at[request.trade_index, 'Hold_Time'] = f"{hold_time:.1f}h"
        
        # Update portfolio with remaining P&L
        portfolio_size = load_portfolio_size(current_mode)
        new_portfolio_size = portfolio_size + remaining_pnl
        save_portfolio_size(new_portfolio_size, current_mode)
    
    save_trades(df, current_mode)
    
    return {
        "message": "TP hit - trade partially closed" if remaining_position_size > 0 else "TP hit - trade fully closed",
        "pnl": pnl,
        "remaining_position_size": remaining_position_size,
        "new_portfolio_size": new_portfolio_size
    }

@app.post("/api/trades/stop-loss-hit")
def stop_loss_hit(request: StopLossHitRequest, mode: Optional[str] = None):
    """Handle stop loss hit - closes trade (or allocated portion)"""
    current_mode = mode or load_mode()
    df = load_trades(current_mode)
    
    # Use loc for actual DataFrame index (not positional)
    if request.trade_index not in df.index:
        raise HTTPException(status_code=400, detail=f"Invalid trade index: {request.trade_index}. Valid indices: {list(df.index)}")
    
    trade = df.loc[request.trade_index]
    
    if trade['Status'] != 'Open':
        raise HTTPException(status_code=400, detail="Trade is already closed")
    
    # Calculate P&L for allocated portion
    entry_price = trade['Entry']
    direction = trade['Direction']
    total_position_size = trade['Position_Size']
    allocated_position_size = total_position_size * request.sl_allocation
    
    if direction == 'long':
        pnl = (request.sl_price - entry_price) / entry_price * allocated_position_size
    else:
        pnl = (entry_price - request.sl_price) / entry_price * allocated_position_size
    
    # Update portfolio size
    portfolio_size = load_portfolio_size(current_mode)
    new_portfolio_size = portfolio_size + pnl
    save_portfolio_size(new_portfolio_size, current_mode)
    
    # Update position size
    remaining_position_size = total_position_size - allocated_position_size
    
    df.at[request.trade_index, 'Position_Size'] = remaining_position_size
    df.at[request.trade_index, 'SL_Hit'] = True
    df.at[request.trade_index, 'SL_Price'] = request.sl_price
    
    # Update cumulative P&L
    current_pnl = trade['P&L'] if pd.notna(trade['P&L']) else 0.0
    df.at[request.trade_index, 'P&L'] = current_pnl + pnl
    
    # Check if should fully close
    all_sls = json.loads(trade['SLs']) if trade['SLs'] else []
    is_last_sl = (request.sl_index == len(all_sls) - 1) or (len(all_sls) == 1)
    
    # If this is the only SL or last SL, or if remaining position is very small, close completely
    if is_last_sl or remaining_position_size < total_position_size * 0.01:
        # Close completely
        if direction == 'long':
            remaining_pnl = (request.sl_price - entry_price) / entry_price * remaining_position_size
        else:
            remaining_pnl = (entry_price - request.sl_price) / entry_price * remaining_position_size
        
        entry_date = pd.to_datetime(trade['Date'])
        exit_date = datetime.now()
        hold_time = (exit_date - entry_date).total_seconds() / 3600
        
        df.at[request.trade_index, 'Status'] = 'Closed'
        df.at[request.trade_index, 'Exit_Price'] = request.sl_price
        df.at[request.trade_index, 'P&L'] = current_pnl + pnl + remaining_pnl
        df.at[request.trade_index, 'Hold_Time'] = f"{hold_time:.1f}h"
        
        # Update portfolio with remaining P&L
        portfolio_size = load_portfolio_size(current_mode)
        new_portfolio_size = portfolio_size + remaining_pnl
        save_portfolio_size(new_portfolio_size, current_mode)
    
    save_trades(df, current_mode)
    
    return {
        "message": "SL hit - trade partially closed" if remaining_position_size > 0 else "SL hit - trade fully closed",
        "pnl": pnl,
        "remaining_position_size": remaining_position_size,
        "new_portfolio_size": new_portfolio_size
    }

@app.delete("/api/trades/clear")
def clear_all_trades(mode: Optional[str] = None):
    """Clear all trades from the CSV file"""
    try:
        current_mode = mode or load_mode()
        # Create empty DataFrame with the correct columns
        empty_df = pd.DataFrame(columns=JOURNAL_COLUMNS)
        save_trades(empty_df, current_mode)
        
        # Reset portfolio size to 0 or keep it - user's choice
        # For now, we'll keep the portfolio size
        
        return {
            "message": "All trades cleared successfully",
            "trades_count": 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing trades: {str(e)}")

@app.delete("/api/trades/{trade_index}")
def delete_trade(trade_index: int, mode: Optional[str] = None):
    """Delete a trade by index"""
    current_mode = mode or load_mode()
    df = load_trades(current_mode)
    
    if trade_index >= len(df) or trade_index < 0:
        raise HTTPException(status_code=400, detail="Invalid trade index")
    
    # Delete the trade by dropping the row
    df = df.drop(df.index[trade_index]).reset_index(drop=True)
    save_trades(df, current_mode)
    
    return {
        "message": "Trade deleted successfully",
        "trade_index": trade_index
    }

@app.post("/api/trades/import")
async def import_trades(file: UploadFile = File(...), mode: Optional[str] = None):
    """Import trades from a CSV file"""
    try:
        current_mode = mode or load_mode()
        # Check file extension
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="File must be a CSV file")
        
        # Read file content
        contents = await file.read()
        
        # Try to read CSV
        try:
            # Try different encodings
            try:
                df = pd.read_csv(io.BytesIO(contents), encoding='utf-8')
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(contents), encoding='latin-1')
            
            # Validate required columns exist
            required_columns = ['Date', 'Asset', 'Direction', 'Entry', 'Position_Size', 'Status']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                raise HTTPException(
                    status_code=400, 
                    detail=f"CSV file is missing required columns: {', '.join(missing_columns)}"
                )
            
            # Ensure all required columns exist, add missing ones with defaults
            for col in JOURNAL_COLUMNS:
                if col not in df.columns:
                    if col in ['TPs', 'SLs', 'Hit_TPs']:
                        df[col] = [json.dumps([]) for _ in range(len(df))]
                    elif col in ['TP_Hit', 'SL_Hit']:
                        df[col] = False
                    elif col in ['Entry', 'SL', 'Position_Size', 'Exit_Price', 'P&L']:
                        df[col] = 0.0
                    else:
                        df[col] = None
            
            # Reorder columns to match expected format
            df = df[JOURNAL_COLUMNS]
            
            # Save the imported trades
            save_trades(df, current_mode)
            
            # Count trades
            total_trades = len(df)
            open_trades = len(df[df['Status'] == 'Open']) if 'Status' in df.columns else 0
            closed_trades = total_trades - open_trades
            
            return {
                "message": "Trades imported successfully",
                "total_trades": total_trades,
                "open_trades": open_trades,
                "closed_trades": closed_trades
            }
            
        except pd.errors.EmptyDataError:
            raise HTTPException(status_code=400, detail="CSV file is empty")
        except pd.errors.ParserError as e:
            raise HTTPException(status_code=400, detail=f"Error parsing CSV file: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error importing trades: {str(e)}")

@app.post("/api/calculate/position-size")
def calculate_position_size(request: PositionSizeRequest, mode: Optional[str] = None):
    """Calculate position size based on risk (matching original logic)"""
    current_mode = mode or load_mode()
    portfolio_size = load_portfolio_size(current_mode)
    risk_pct = request.risk_percentage / 100 if request.risk_percentage else RISK_PCT
    risk_amount = portfolio_size * risk_pct
    
    if request.entry_price == 0:
        return {
            "position_size_dollars": 0,
            "position_size_units": 0,
            "margin_required": 0,
            "risk_amount": 0,
            "message": "Please enter an entry price"
        }
    
    # If no stop loss, calculate based on liquidation price
    if request.stop_loss == 0 or request.stop_loss is None:
        # Calculate liquidation price based on leverage
        # For long: liquidation = entry * (1 - 1/leverage)
        # For short: liquidation = entry * (1 + 1/leverage)
        if request.direction.lower() == 'long':
            liquidation_price = request.entry_price * (1 - 1 / request.leverage)
        else:
            liquidation_price = request.entry_price * (1 + 1 / request.leverage)
        
        # Calculate price difference to liquidation
        price_diff = abs(request.entry_price - liquidation_price)
        if price_diff == 0:
            return {
                "position_size_dollars": 0,
                "position_size_units": 0,
                "margin_required": 0,
                "risk_amount": 0,
                "message": "Invalid leverage"
            }
        
        # Calculate liquidation percentage
        liquidation_percentage = price_diff / request.entry_price
        
        # Calculate position size (notional value in dollars)
        # This is: risk_amount / liquidation_percentage
        position_size_dollars = risk_amount / liquidation_percentage
        
        # Calculate position size in coin units
        position_size_units = position_size_dollars / request.entry_price
        
        # Calculate margin required (position size / leverage)
        margin_required = position_size_dollars / request.leverage
        
        # Verify: position_size should equal margin_required × leverage
        verified_position_size = margin_required * request.leverage
        
        return {
            "position_size_dollars": position_size_dollars,
            "position_size_units": position_size_units,
            "margin_required": margin_required,
            "risk_amount": risk_amount,
            "sl_percentage": liquidation_percentage * 100,
            "liquidation_price": liquidation_price,
            "verification": f"${margin_required:,.2f} margin × {request.leverage}x = ${verified_position_size:,.2f} position",
            "message": f"Margin: ${margin_required:,.2f} | Position: {position_size_units:.6f} units"
        }
    
    # Traditional stop loss calculation
    price_diff = abs(request.entry_price - request.stop_loss)
    if price_diff == 0:
        return {
            "position_size_dollars": 0,
            "position_size_units": 0,
            "margin_required": 0,
            "risk_amount": 0,
            "message": "Stop loss cannot equal entry price"
        }
    
    # Calculate stop loss percentage
    sl_percentage = price_diff / request.entry_price
    
    # Calculate position size (notional value in dollars)
    # This is: risk_amount / sl_percentage
    position_size_dollars = risk_amount / sl_percentage
    
    # Calculate position size in coin units
    position_size_units = position_size_dollars / request.entry_price
    
    # Calculate margin required (position size / leverage)
    margin_required = position_size_dollars / request.leverage
    
    # Verify: position_size should equal margin_required × leverage
    verified_position_size = margin_required * request.leverage
    
    return {
        "position_size_dollars": position_size_dollars,
        "position_size_units": position_size_units,
        "margin_required": margin_required,
        "risk_amount": risk_amount,
        "sl_percentage": sl_percentage * 100,
        "verification": f"${margin_required:,.2f} margin × {request.leverage}x = ${verified_position_size:,.2f} position",
        "message": f"Margin: ${margin_required:,.2f} | Position: {position_size_units:.6f} units"
    }

class RiskRewardRequest(BaseModel):
    entry_price: float
    stop_loss: float
    take_profits: List[TakeProfit]
    direction: str

@app.post("/api/calculate/risk-reward")
def calculate_risk_reward(request: RiskRewardRequest):
    """Calculate risk/reward ratio using trade calculator"""
    if not request.take_profits or len(request.take_profits) == 0:
        return {"rr_ratio": 0, "message": "No take profits set"}
    
    try:
        # Convert TakeProfit objects to dicts for calculator
        tp_dicts = [{"price": tp.price, "allocation": tp.allocation} for tp in request.take_profits]
        
        rr_ratio = trade_calc.calculate_rr_ratio(
            entry_price=request.entry_price,
            stop_loss=request.stop_loss,
            take_profits=tp_dicts,
            direction=request.direction
        )
        
        return {
            "rr_ratio": rr_ratio, 
            "message": f"Risk/Reward: 1:{rr_ratio:.2f}" if rr_ratio > 0 else "Invalid setup"
        }
    except Exception as e:
        return {"rr_ratio": 0, "message": f"Calculation error: {str(e)}"}

class ProfitLossRequest(BaseModel):
    entry_price: float
    stop_loss: float
    position_size: float
    take_profits: List[TakeProfit]
    stop_losses: List[StopLoss]
    direction: str
    leverage: Optional[float] = None

@app.post("/api/calculate/profit-loss")
def calculate_profit_loss(request: ProfitLossRequest):
    """Calculate profit and loss amounts for TPs and SLs based on position size"""
    if request.position_size <= 0:
        return {
            "take_profits": [],
            "stop_losses": [],
            "message": "Invalid position size"
        }
    
    # Calculate total allocations
    total_tp_allocation = sum(tp.allocation for tp in request.take_profits)
    total_sl_allocation = sum(sl.allocation for sl in request.stop_losses)
    
    # Calculate profit amounts for take profits
    tp_results = []
    for i, tp in enumerate(request.take_profits):
        if tp.price > 0:
            # Calculate profit per unit
            if request.direction == 'long':
                profit_per_unit = tp.price - request.entry_price
            else:
                profit_per_unit = request.entry_price - tp.price
            
            # Normalize allocation if total doesn't equal 100%
            if total_tp_allocation > 0:
                normalized_allocation = tp.allocation / total_tp_allocation
            else:
                normalized_allocation = tp.allocation
            
            # Calculate allocated position size
            allocated_position_size = request.position_size * normalized_allocation
            
            # Calculate position units
            position_units = allocated_position_size / request.entry_price
            
            # Calculate profit amount
            profit_amount = position_units * profit_per_unit
            
            tp_results.append({
                "index": i,
                "price": tp.price,
                "allocation": tp.allocation,
                "profit_amount": profit_amount,
                "normalized_allocation": normalized_allocation
            })
    
    # Calculate loss amounts for stop losses
    sl_results = []
    for i, sl in enumerate(request.stop_losses):
        if sl.price > 0:
            # Calculate loss per unit
            if request.direction == 'long':
                loss_per_unit = request.entry_price - sl.price
            else:
                loss_per_unit = sl.price - request.entry_price
            
            # Normalize allocation if total doesn't equal 100%
            if total_sl_allocation > 0:
                normalized_allocation = sl.allocation / total_sl_allocation
            else:
                normalized_allocation = sl.allocation
            
            # Calculate allocated position size
            allocated_position_size = request.position_size * normalized_allocation
            
            # Calculate position units
            position_units = allocated_position_size / request.entry_price
            
            # Calculate loss amount
            loss_amount = position_units * loss_per_unit
            
            sl_results.append({
                "index": i,
                "price": sl.price,
                "allocation": sl.allocation,
                "loss_amount": loss_amount,
                "normalized_allocation": normalized_allocation
            })
    
    # If no stop losses are set, add liquidation loss (equal to margin)
    if len(sl_results) == 0 and request.stop_loss == 0 and request.leverage and request.leverage > 0:
        margin = request.position_size / request.leverage
        sl_results.append({
            "index": 0,
            "price": 0,  # Liquidation price (not set)
            "allocation": 1.0,
            "loss_amount": margin,
            "normalized_allocation": 1.0,
            "is_liquidation": True
            })
    
    return {
        "take_profits": tp_results,
        "stop_losses": sl_results,
        "message": ""
    }

class TradeDetailsRequest(BaseModel):
    """Request model for comprehensive trade calculation"""
    portfolio_size: float
    risk_percentage: float
    entry_price: float
    stop_loss: float
    take_profits: List[TakeProfit]
    leverage: float
    direction: str
    market_volume_24h: Optional[float] = 0
    is_maker: Optional[bool] = False

@app.post("/api/calculate/trade-details")
def calculate_trade_details(request: TradeDetailsRequest):
    """Calculate comprehensive trade details including fees and slippage"""
    try:
        # Convert TakeProfit objects to dicts
        tp_dicts = [{"price": tp.price, "allocation": tp.allocation} for tp in request.take_profits]
        
        # Calculate complete trade details
        details = trade_calc.calculate_complete_trade(
            portfolio_size=request.portfolio_size,
            risk_percentage=request.risk_percentage,
            entry_price=request.entry_price,
            stop_loss=request.stop_loss,
            take_profits=tp_dicts,
            leverage=request.leverage,
            direction=request.direction,
            market_volume_24h=request.market_volume_24h or 0,
            is_maker=request.is_maker or False
        )
        
        return {
            "position_size_dollars": details.position_size_dollars,
            "position_size_units": details.position_size_units,
            "margin_required": details.margin_required,
            "leverage": details.leverage,
            "risk_amount": details.risk_amount,
            "risk_percentage": details.risk_percentage,
            "max_loss_amount": details.max_loss_amount,
            "entry_price": details.entry_price,
            "stop_loss": details.stop_loss,
            "liquidation_price": details.liquidation_price,
            "sl_distance_pct": details.sl_distance_pct * 100,
            "slippage_pct": details.slippage_pct * 100,
            "slippage_amount": details.slippage_amount,
            "effective_entry": details.effective_entry,
            "entry_fee": details.entry_fee,
            "exit_fee": details.exit_fee,
            "total_fees": details.total_fees,
            "rr_ratio": details.rr_ratio,
            "tp_levels": details.tp_levels,
            "breakeven_price": details.breakeven_price,
            "breakeven_distance_pct": details.breakeven_distance_pct * 100,
            "message": f"R/R: 1:{details.rr_ratio:.2f} | Breakeven: ${details.breakeven_price:.2f}"
        }
    except Exception as e:
        return {
            "error": str(e),
            "message": f"Calculation error: {str(e)}"
        }

@app.get("/api/analytics/overview")
def get_analytics_overview(mode: Optional[str] = None):
    """Get trading analytics overview"""
    try:
        df = load_trades(normalized_mode)
        if df.empty:
            return {
                "total_trades": 0,
                "open_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0,
                "total_pnl": 0
            }
        
        if 'Status' not in df.columns:
            return {
                "total_trades": len(df),
                "open_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0,
                "total_pnl": 0
            }
        
        closed_trades = df[df['Status'] == 'Closed']
        open_trades_count = len(df[df['Status'] == 'Open'])
        
        total_trades = len(df)
        
        if len(closed_trades) > 0:
            if 'P&L' in closed_trades.columns:
                winning_trades = len(closed_trades[closed_trades['P&L'] > 0])
                losing_trades = len(closed_trades[closed_trades['P&L'] < 0])
                win_rate = (winning_trades / len(closed_trades)) * 100
                total_pnl = closed_trades['P&L'].sum()
            else:
                winning_trades = 0
                losing_trades = 0
                win_rate = 0
                total_pnl = 0
        else:
            winning_trades = 0
            losing_trades = 0
            win_rate = 0
            total_pnl = 0
        
        return {
            "total_trades": total_trades,
            "open_trades": open_trades_count,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "total_pnl": total_pnl
        }
    except Exception as e:
        print(f"Error in get_analytics_overview: {e}")
        traceback.print_exc()
        return {
            "total_trades": 0,
            "open_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0,
            "total_pnl": 0
        }

# ==================== Mode Execution Blocking ====================

def check_execution_allowed():
    """Check if execution is allowed based on current mode. Raises 403 if blocked."""
    mode = load_mode()
    if mode == "planning":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "mode_blocked",
                "mode": "planning",
                "reason": "Execution endpoints are blocked in planning mode. Switch to live mode to execute trades."
            }
        )


# ==================== Hyperliquid Exchange Integration ====================

@app.get("/api/hyperliquid/status")
def get_hyperliquid_status():
    """Get Hyperliquid integration status"""
    if not hl_client:
        return {"enabled": False, "connected": False, "message": "Hyperliquid client not available"}
    
    return {
        "enabled": hl_client.enabled,
        "connected": hl_client.info_client is not None,
        "testnet": hl_client.use_testnet if hl_client.enabled else None,
        "wallet_address": hl_client.wallet_address if hl_client.enabled else None
    }

@app.get("/api/hyperliquid/price/{coin}")
def get_hyperliquid_price(coin: str):
    """Get current price for a coin"""
    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="Hyperliquid integration not enabled")
    
    price = hl_client.get_current_price(coin.upper())
    if price is None:
        raise HTTPException(status_code=404, detail=f"Price not available for {coin}")
    
    return {"coin": coin.upper(), "price": price, "timestamp": datetime.now().isoformat()}

@app.get("/api/hyperliquid/positions")
def get_hyperliquid_positions(coin: Optional[str] = None):
    """Get open positions from Hyperliquid"""
    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="Hyperliquid integration not enabled")
    
    if not hl_client.wallet_address:
        raise HTTPException(status_code=400, detail="Wallet address not configured")
    
    positions = hl_client.get_positions(coin.upper() if coin else None)
    return {"positions": positions, "count": len(positions)}

@app.get("/api/hyperliquid/assets")
def get_hyperliquid_assets():
    """Get available assets and their max leverage from Hyperliquid"""
    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="Hyperliquid integration not enabled")
    
    asset_data = hl_client.get_asset_metadata()
    if asset_data is None:
        raise HTTPException(status_code=500, detail="Failed to fetch asset metadata")
    
    # Format for frontend
    assets = []
    for name, data in asset_data.items():
        assets.append({
            "symbol": name,
            "max_leverage": data["max_leverage"],
            "sz_decimals": data["sz_decimals"],
            "only_isolated": data["only_isolated"]
        })
    
    return {"assets": assets, "count": len(assets)}

class HyperliquidOrderRequest(BaseModel):
    coin: str
    is_buy: bool
    margin_amount: float  # Margin in USD
    leverage: int
    entry_price: float
    take_profits: Optional[List[Dict]] = []  # List of {price: float, allocation: float}
    stop_losses: Optional[List[Dict]] = []    # List of {price: float, allocation: float}
    is_isolated: bool = True

@app.post("/api/hyperliquid/order")
def place_hyperliquid_order(request: HyperliquidOrderRequest):
    """Place a market order on Hyperliquid with built-in TP/SL"""
    # Check if execution is allowed in current mode
    check_execution_allowed()
    
    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="Hyperliquid integration not enabled")
    
    if not hl_client.exchange_client:
        raise HTTPException(status_code=400, detail="Exchange client not configured - check wallet credentials")
    
    try:
        # Get current real-time price from Hyperliquid
        current_price = hl_client.get_current_price(request.coin)
        if current_price is None:
            raise HTTPException(status_code=400, detail="Could not fetch current market price. Please try again.")
        
        print(f"[DEBUG] Using real-time price: {current_price} (frontend sent: {request.entry_price})")
        
        # Get asset metadata for szDecimals
        asset_data = hl_client.get_asset_metadata()
        sz_decimals = 5  # Default for most assets
        if asset_data and request.coin in asset_data:
            sz_decimals = asset_data[request.coin].get('sz_decimals', 5)
        
        # Calculate position size in coin units using real-time price
        # Position Size = (Margin × Leverage) / Current Price
        position_size_units = (request.margin_amount * request.leverage) / current_price
        
        # Round to the correct number of decimals for this asset
        position_size_units = round(position_size_units, sz_decimals)
        
        print(f"Order: {request.coin} | Size: {position_size_units} | Leverage: {request.leverage}x | Margin: ${request.margin_amount:.2f}")
        
        # Place market order
        # For market orders, we use the current price as limitPx with a small buffer
        print(f"[DEBUG] is_buy={request.is_buy}, direction={'BUY' if request.is_buy else 'SELL'}")
        limit_px = current_price * (1.002 if request.is_buy else 0.998)  # 0.2% buffer for market execution
        
        # Round price to valid tick size (whole dollars for BTC)
        limit_px = round(limit_px, 0)
        
        print(f"Sending order: {request.coin} @ {limit_px} (size: {position_size_units})")
        
        # Prepare order type
        order_type = {"limit": {"tif": "Ioc"}}  # Immediate-or-Cancel for market-like execution
        
        # Get first TP and SL prices from request
        tp_price = None
        sl_price = None
        
        print(f"[DEBUG] Received TPs: {request.take_profits}")
        print(f"[DEBUG] Received SLs: {request.stop_losses}")
        
        if request.take_profits and len(request.take_profits) > 0:
            tp_price = round(request.take_profits[0].get("price", 0), 0)
            print(f"[DEBUG] TP price extracted: {tp_price}")
            if tp_price <= 0:
                tp_price = None
        
        if request.stop_losses and len(request.stop_losses) > 0:
            sl_price = round(request.stop_losses[0].get("price", 0), 0)
            print(f"[DEBUG] SL price extracted: {sl_price}")
            if sl_price <= 0:
                sl_price = None
        
        # Set leverage BEFORE placing the order (per-coin setting)
        # Note: is_cross=True for cross margin, is_cross=False for isolated
        try:
            is_cross = not request.is_isolated  # is_isolated=True means NOT cross
            hl_client.exchange_client.update_leverage(request.leverage, request.coin, is_cross)
            margin_mode = "Cross" if is_cross else "Isolated"
            print(f"[DEBUG] Set leverage to {request.leverage}x ({margin_mode}) for {request.coin}")
        except Exception as e:
            print(f"[WARNING] Could not set leverage: {e}")
        
        # Place the main order
        result = hl_client.exchange_client.order(
            name=request.coin,
            is_buy=request.is_buy,
            sz=position_size_units,
            limit_px=limit_px,
            order_type=order_type,
            reduce_only=False,
            cloid=None
        )
        
        print(f"[DEBUG] Order result: {result}")
        
        # Check for errors in the response
        if result and result.get("status") == "ok":
            statuses = result.get("response", {}).get("data", {}).get("statuses", [])
            if statuses and len(statuses) > 0:
                if "error" in statuses[0]:
                    error_msg = statuses[0]["error"]
                    raise HTTPException(status_code=400, detail=f"Order failed: {error_msg}")
        
        # Check if order was successful
        if result and result.get("status") == "ok":
            # Place Take Profit orders
            if request.take_profits and len(request.take_profits) > 0:
                print(f"[DEBUG] Placing {len(request.take_profits)} Take Profit order(s)")
                for tp in request.take_profits:
                    try:
                        tp_price = round(tp.get("price", 0), 0)
                        allocation = tp.get("allocation", 0)
                        if tp_price <= 0 or allocation <= 0:
                            print(f"[WARNING] Skipping TP order - invalid price: {tp_price}, allocation: {allocation}")
                            continue
                        
                        tp_size = round(position_size_units * allocation, sz_decimals)
                        if tp_size <= 0:
                            print(f"[WARNING] TP size too small: {tp_size}, skipping")
                            continue
                        
                        tp_result = hl_client.exchange_client.order(
                            name=request.coin,
                            is_buy=not request.is_buy,
                            sz=tp_size,
                            limit_px=tp_price,
                            order_type={"limit": {"tif": "Gtc"}},
                            reduce_only=True,
                            cloid=None
                        )
                        print(f"[DEBUG] TP order result: {tp_result}")
                    except Exception as e:
                        print(f"[WARNING] Failed to place TP order: {e}")
            
            # Place Stop Loss orders using Hyperliquid trigger orders
            if request.stop_losses and len(request.stop_losses) > 0:
                print(f"[DEBUG] Placing {len(request.stop_losses)} Stop Loss trigger order(s)")
                for sl in request.stop_losses:
                    try:
                        sl_price = round(sl.get("price", 0), 0)
                        allocation = sl.get("allocation", 1.0)
                        if sl_price <= 0 or allocation <= 0:
                            print(f"[WARNING] Skipping SL - invalid price: {sl_price}, allocation: {allocation}")
                            continue
                        
                        # Calculate size to close
                        sl_size = round(position_size_units * allocation, sz_decimals)
                        if sl_size <= 0:
                            print(f"[WARNING] SL size too small: {sl_size}, skipping")
                            continue
                        
                        # Place stop order using the new method
                        sl_result = hl_client.place_stop_order(
                            coin=request.coin,
                            is_buy=request.is_buy,
                            size=sl_size,
                            trigger_price=sl_price,
                            is_long_position=request.is_buy  # is_buy=True means long
                        )
                        print(f"[DEBUG] SL order result: {sl_result}")
                    except Exception as e:
                        print(f"[WARNING] Failed to place SL order: {e}")
            
            return {
                "status": "success",
                "order_id": result.get("response", {}).get("data", {}).get("statuses", [{}])[0].get("resting", {}).get("oid", "unknown"),
                "position_size": position_size_units,
                "margin_used": request.margin_amount,
                "leverage": request.leverage,
                "message": f"Order placed: {position_size_units:.6f} {request.coin} at {request.leverage}x leverage"
            }
        else:
            error_msg = result.get("response", "Unknown error") if result else "No response"
            raise HTTPException(status_code=400, detail=f"Order failed: {error_msg}")
            
    except Exception as e:
        print(f"[ERROR] Error placing order: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error placing order: {str(e)}")

# ==================== WebSocket Price Feed ====================

# In-memory storage for latest BTC price
latest_btc_price = {"price": None, "timestamp": None}

@app.get("/api/hyperliquid/ws-price")
def get_ws_price():
    """Get latest BTC price from WebSocket feed"""
    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="Hyperliquid integration not enabled")
    
    # For now, return REST API price (WebSocket will be implemented next)
    price = hl_client.get_current_price("BTC")
    if price:
        latest_btc_price["price"] = price
        latest_btc_price["timestamp"] = datetime.now().isoformat()
    
    return latest_btc_price

@app.post("/api/hyperliquid/close/{coin}")
def close_hyperliquid_position(coin: str):
    """Close all positions for a given coin via market order and return fill price"""
    # Check if execution is allowed in current mode
    check_execution_allowed()
    
    if not hl_client:
        raise HTTPException(status_code=503, detail="Hyperliquid client not initialized")
    
    # Ensure client is initialized
    hl_client._ensure_initialized()
    
    if not hl_client.enabled:
        raise HTTPException(status_code=503, detail="Hyperliquid integration not enabled")

    if not hl_client.exchange_client:
        raise HTTPException(status_code=400, detail="Exchange client not configured - check wallet credentials")

    try:
        coin = coin.upper()
        
        print(f"[DEBUG] Wallet address being used: {hl_client.wallet_address}")
        
        # Debug: Get all positions to see what's available
        all_positions = hl_client.get_positions(None)
        print(f"[DEBUG] All positions: {all_positions}")
        
        # Check for specific position
        positions = hl_client.get_positions(coin)
        print(f"[DEBUG] Positions for {coin}: {positions}")
        
        if not positions or len(positions) == 0:
            # If no position found, check if maybe the coin format is different
            # Try to find matching position
            for pos in all_positions:
                pos_coin = pos.get('coin', '')
                if coin in pos_coin or pos_coin in coin:
                    print(f"[INFO] Found position with coin '{pos_coin}' matching '{coin}'")
                    # Use the actual coin name from Hyperliquid
                    coin = pos_coin
                    positions = [pos]
                    break
            
            if not positions or len(positions) == 0:
                # List available positions in error message
                available_coins = [p.get('coin') for p in all_positions]
                raise HTTPException(
                    status_code=400, 
                    detail=f"No open position found for {coin}. Available positions: {available_coins}"
                )
        
        position = positions[0]
        actual_coin = position.get('coin', coin)
        print(f"[INFO] Closing position for {actual_coin}: size={position.get('size')}, entry=${position.get('entry_price')}")
        
        # Close the position using the actual coin name from Hyperliquid
        result = hl_client.market_close(actual_coin)
        print(f"[DEBUG] market_close result: {result}")
        
        # Wait 2 seconds for the order to be processed
        print(f"[DEBUG] Waiting 2 seconds for position close to be confirmed...")
        time.sleep(2)
        
        # Verify position was actually closed by checking again
        print(f"[DEBUG] Checking if position was actually closed...")
        positions_after = hl_client.get_positions(actual_coin)
        print(f"[DEBUG] Positions after market_close: {positions_after}")
        
        # If position still exists, try alternative close method using market order
        if positions_after and len(positions_after) > 0:
            print(f"[WARN] Position still exists after market_close! Trying alternative close method...")
            
            # Get current position details
            remaining_position = positions_after[0]
            remaining_size = remaining_position.get('size', 0)
            position_direction = remaining_position.get('direction', 'long')
            
            print(f"[DEBUG] Remaining position: size={remaining_size}, direction={position_direction}")
            
            # Get current market price for the opposite trade
            current_price = hl_client.get_current_price(actual_coin)
            
            if current_price and remaining_size > 0:
                # Determine if we need to buy or sell to close
                # If position is long (size > 0), we need to sell (is_buy=False)
                # If position is short (size < 0), we need to buy (is_buy=True)
                is_buy_to_close = position_direction == 'short'
                
                print(f"[DEBUG] Attempting alternative close: is_buy={is_buy_to_close}, size={abs(remaining_size)}, price={current_price}")
                
                # Place a market order to close the remaining position
                try:
                    alt_result = hl_client.exchange_client.order(
                        name=actual_coin,
                        is_buy=is_buy_to_close,
                        sz=abs(remaining_size),
                        limit_px=round(current_price * (1.002 if is_buy_to_close else 0.998), 0),  # Small buffer
                        order_type={"limit": {"tif": "Ioc"}},  # Immediate-or-Cancel
                        reduce_only=True,
                        cloid=None
                    )
                    print(f"[DEBUG] Alternative close result: {alt_result}")
                    
                    # Wait another 2 seconds and verify again
                    time.sleep(2)
                    positions_final = hl_client.get_positions(actual_coin)
                    print(f"[DEBUG] Positions after alternative close: {positions_final}")
                    
                    if positions_final and len(positions_final) > 0:
                        print(f"[ERROR] Position STILL exists after alternative close attempt!")
                    else:
                        print(f"[INFO] Alternative close succeeded - position is now closed")
                        # Update result to show success
                        result = alt_result
                except Exception as alt_error:
                    print(f"[ERROR] Alternative close method failed: {alt_error}")
                    import traceback
                    traceback.print_exc()
        else:
            print(f"[INFO] Position successfully closed with market_close method")
        
        if result and result.get("status") == "error":
            error_msg = result.get("message", "Unknown error")
            raise HTTPException(status_code=400, detail=f"Close position failed: {error_msg}")
        
        # Parse the fill price from the response
        fill_price = None
        statuses = []
        print(f"[DEBUG] Full result structure: {result}")
        
        if result and result.get("status") == "ok":
            # Try to get filled price from response - multiple possible formats
            response_data = result.get("response", {})
            print(f"[DEBUG] Response data: {response_data}")
            
            # Try format 1: response.data.statuses[0].filled.avgPx
            if isinstance(response_data, dict):
                data = response_data.get("data", {})
                statuses = data.get("statuses", [])
                if statuses and len(statuses) > 0:
                    filled_data = statuses[0].get("filled", {})
                    avg_px = filled_data.get("avgPx")
                    if avg_px:
                        fill_price = float(avg_px)
                        print(f"[INFO] Got fill price from statuses[0].filled.avgPx: ${fill_price}")
            
            # Try format 2: response.data.statuses[0].totalSz (calculate avg price)
            if not fill_price and statuses:
                total_sz = statuses[0].get("totalSz")
                if total_sz and total_sz > 0:
                    # Use the close price as approximation
                    fill_price = hl_client.get_current_price(actual_coin)
                    print(f"[INFO] Using current price as fill price (filled {total_sz} units): ${fill_price}")
            
            # Try format 3: direct avgPx in result
            if not fill_price and "avgPx" in result:
                fill_price = float(result["avgPx"])
                print(f"[INFO] Got fill price from result.avgPx: ${fill_price}")
        
        if not fill_price:
            # Fallback to current market price if we can't get fill price
            fill_price = hl_client.get_current_price(actual_coin)
            print(f"[WARN] Could not extract fill price from result, using current price: ${fill_price}")

        return {
            "status": "success",
            "coin": actual_coin,
            "fill_price": fill_price,
            "result": result,
            "message": f"Position closed for {actual_coin} at ${fill_price:.2f}"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Error closing position: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error closing position: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    # Optimize for faster startup - use single worker, disable access log
    uvicorn.run(
        app, 
        host="127.0.0.1", 
        port=8000,
        log_level="warning",  # Reduce logging overhead
        access_log=False  # Disable access logs for faster startup
    )

