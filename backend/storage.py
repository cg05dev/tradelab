"""
CSV/JSON persistence for trades, portfolio size and the active trading mode.
Paper and live modes keep separate files.
"""

import json
import math
import os
from typing import Optional

import pandas as pd


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

JOURNAL_COLUMNS = [
    'Date', 'Asset', 'Direction', 'Entry', 'SL', 'TPs', 'SLs', 'Position_Size',
    'Confirmations', 'Thesis', 'Status', 'Exit_Price', 'P&L', 'Hold_Time',
    'TP_Hit', 'TP_Price', 'SL_Hit', 'SL_Price', 'Hit_TPs', 'Margin', 'Leverage'
]

TEXT_COLUMNS = ['Date', 'Asset', 'Direction', 'TPs', 'SLs', 'Confirmations', 'Thesis', 'Status', 'Hold_Time', 'Hit_TPs']

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
            df = pd.read_csv(files['trades'], dtype={col: object for col in TEXT_COLUMNS})
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

def _normalize_mode_value(mode: str) -> str:
    aliases = {
        'planning': 'paper',
        'paper': 'paper',
        'live': 'live',
    }
    return aliases.get((mode or '').lower(), '')

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
