"""
SQLite persistence for trades, portfolio size and the active trading mode.

Every trade row belongs to a mode ('paper' or 'live'), so the two journals never mix.
Trade ids are stable primary keys; the API exposes them as `_index` / `trade_index`.

Older installs stored data in per-mode CSV/JSON files. Those are imported once,
the first time the database is opened, and left on disk untouched.
"""

import json
import logging
import math
import os
import sqlite3
from contextlib import contextmanager
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(__file__)

DB_FILE = os.getenv('TRADELAB_DB_FILE', os.path.join(BASE_DIR, 'tradelab.db'))

# Pre-SQLite data files, read only by the one-time import
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

MODES = ('live', 'paper')
DEFAULT_MODE = 'live'

JOURNAL_COLUMNS = [
    'Date', 'Asset', 'Direction', 'Entry', 'SL', 'TPs', 'SLs', 'Position_Size',
    'Confirmations', 'Thesis', 'Status', 'Exit_Price', 'P&L', 'Hold_Time',
    'TP_Hit', 'TP_Price', 'SL_Hit', 'SL_Price', 'Hit_TPs', 'Margin', 'Leverage'
]

# Text columns that pandas would otherwise infer as float when every value is empty
TEXT_COLUMNS = ['Date', 'Asset', 'Direction', 'TPs', 'SLs', 'Confirmations', 'Thesis', 'Status', 'Hold_Time', 'Hit_TPs']

# Journal column -> SQL column
SQL_COLUMNS = {
    'Date': 'date', 'Asset': 'asset', 'Direction': 'direction', 'Entry': 'entry', 'SL': 'sl',
    'TPs': 'tps', 'SLs': 'sls', 'Position_Size': 'position_size', 'Confirmations': 'confirmations',
    'Thesis': 'thesis', 'Status': 'status', 'Exit_Price': 'exit_price', 'P&L': 'pnl',
    'Hold_Time': 'hold_time', 'TP_Hit': 'tp_hit', 'TP_Price': 'tp_price', 'SL_Hit': 'sl_hit',
    'SL_Price': 'sl_price', 'Hit_TPs': 'hit_tps', 'Margin': 'margin', 'Leverage': 'leverage',
}
BOOL_COLUMNS = ['TP_Hit', 'SL_Hit']

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    mode          TEXT    NOT NULL CHECK (mode IN ('live', 'paper')),
    date          TEXT,
    asset         TEXT,
    direction     TEXT,
    entry         REAL,
    sl            REAL,
    tps           TEXT,
    sls           TEXT,
    position_size REAL,
    confirmations TEXT,
    thesis        TEXT,
    status        TEXT,
    exit_price    REAL,
    pnl           REAL,
    hold_time     TEXT,
    tp_hit        INTEGER NOT NULL DEFAULT 0,
    tp_price      REAL,
    sl_hit        INTEGER NOT NULL DEFAULT 0,
    sl_price      REAL,
    hit_tps       TEXT,
    margin        REAL,
    leverage      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_trades_mode_status ON trades (mode, status);

CREATE TABLE IF NOT EXISTS portfolio (
    mode TEXT PRIMARY KEY CHECK (mode IN ('live', 'paper')),
    size REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@contextmanager
def _connect():
    """Open a connection and commit on success / roll back on error."""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        _ensure_schema(conn)
        with conn:
            yield conn
    finally:
        conn.close()


def _ensure_schema(conn):
    conn.executescript(SCHEMA)
    done = conn.execute("SELECT 1 FROM settings WHERE key = 'legacy_import_done'").fetchone()
    if not done:
        with conn:
            _import_legacy_files(conn)
            conn.execute("INSERT INTO settings (key, value) VALUES ('legacy_import_done', '1')")


def _import_legacy_files(conn):
    """One-time import of the pre-SQLite CSV/JSON files. Source files are not modified."""
    for mode in MODES:
        files = DATA_FILES[mode]
        if os.path.exists(files['trades']):
            df = pd.read_csv(files['trades'], dtype={col: object for col in TEXT_COLUMNS})
            _insert_rows(conn, df, mode)
            logger.info(f"Imported {len(df)} {mode} trades from {files['trades']}")
        if os.path.exists(files['portfolio']):
            with open(files['portfolio']) as f:
                size = json.load(f).get('portfolio_size', 0)
            conn.execute("INSERT OR REPLACE INTO portfolio (mode, size) VALUES (?, ?)", (mode, float(size or 0)))
    if os.path.exists(MODE_FILE):
        with open(MODE_FILE) as f:
            mode = _normalize_mode_value(json.load(f).get('mode', DEFAULT_MODE)) or DEFAULT_MODE
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('mode', ?)", (mode,))


def _to_db(column, value):
    """Convert a pandas/numpy value into something sqlite3 can store."""
    if value is None:
        return None
    if hasattr(value, 'item'):  # numpy scalar
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if column in BOOL_COLUMNS:
        if isinstance(value, str):
            return int(value.strip().lower() == 'true')
        return int(bool(value))
    return value


def _insert_rows(conn, df, mode):
    columns = [col for col in JOURNAL_COLUMNS if col in df.columns]
    sql_columns = ', '.join(['mode'] + [SQL_COLUMNS[col] for col in columns])
    placeholders = ', '.join(['?'] * (len(columns) + 1))
    rows = [
        [mode] + [_to_db(col, record[col]) for col in columns]
        for record in df[columns].to_dict('records')
    ]
    conn.executemany(f"INSERT INTO trades ({sql_columns}) VALUES ({placeholders})", rows)


def _resolve_mode(mode: Optional[str] = None) -> str:
    if mode is None:
        return load_mode()
    return _normalize_mode_value(mode) or DEFAULT_MODE


def load_trades(mode: Optional[str] = None):
    """Load the journal for a mode as a DataFrame indexed by trade id."""
    current_mode = _resolve_mode(mode)
    select = ', '.join(f'{sql} AS "{col}"' for col, sql in SQL_COLUMNS.items())
    with _connect() as conn:
        df = pd.read_sql_query(
            f"SELECT id, {select} FROM trades WHERE mode = ? ORDER BY id",
            conn,
            params=(current_mode,),
            index_col='id',
        )
    df.index.name = None
    for col in BOOL_COLUMNS:
        df[col] = df[col].astype(bool)
    for col in TEXT_COLUMNS:
        df[col] = df[col].astype(object)
    return df


def insert_trade(trade: Dict, mode: Optional[str] = None) -> int:
    """Insert one trade and return its id."""
    current_mode = _resolve_mode(mode)
    with _connect() as conn:
        _insert_rows(conn, pd.DataFrame([trade]), current_mode)
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_trade(trade_id: int, fields: Dict, mode: Optional[str] = None, portfolio_delta: float = 0.0) -> float:
    """
    Update a trade's fields and add `portfolio_delta` to the mode's portfolio size in one
    transaction. Returns the new portfolio size.
    """
    current_mode = _resolve_mode(mode)
    assignments = ', '.join(f"{SQL_COLUMNS[col]} = ?" for col in fields)
    values = [_to_db(col, value) for col, value in fields.items()]
    with _connect() as conn:
        updated = conn.execute(
            f"UPDATE trades SET {assignments} WHERE id = ? AND mode = ?",
            values + [trade_id, current_mode],
        ).rowcount
        if not updated:
            raise KeyError(trade_id)
        if portfolio_delta:
            conn.execute(
                "INSERT INTO portfolio (mode, size) VALUES (?, ?) "
                "ON CONFLICT (mode) DO UPDATE SET size = size + excluded.size",
                (current_mode, float(portfolio_delta)),
            )
        row = conn.execute("SELECT size FROM portfolio WHERE mode = ?", (current_mode,)).fetchone()
        return row[0] if row else 0


def delete_trade(trade_id: int, mode: Optional[str] = None) -> bool:
    current_mode = _resolve_mode(mode)
    with _connect() as conn:
        return conn.execute("DELETE FROM trades WHERE id = ? AND mode = ?", (trade_id, current_mode)).rowcount > 0


def clear_trades(mode: Optional[str] = None):
    current_mode = _resolve_mode(mode)
    with _connect() as conn:
        conn.execute("DELETE FROM trades WHERE mode = ?", (current_mode,))


def replace_trades(df, mode: Optional[str] = None):
    """Replace a mode's whole journal (CSV import) in a single transaction."""
    current_mode = _resolve_mode(mode)
    with _connect() as conn:
        conn.execute("DELETE FROM trades WHERE mode = ?", (current_mode,))
        _insert_rows(conn, df, current_mode)


def load_portfolio_size(mode: Optional[str] = None):
    """Load portfolio size for the selected mode (0 when unset)"""
    current_mode = _resolve_mode(mode)
    with _connect() as conn:
        row = conn.execute("SELECT size FROM portfolio WHERE mode = ?", (current_mode,)).fetchone()
    return row[0] if row else 0


def save_portfolio_size(size, mode: Optional[str] = None):
    """Save portfolio size for the selected mode"""
    current_mode = _resolve_mode(mode)
    with _connect() as conn:
        conn.execute("INSERT OR REPLACE INTO portfolio (mode, size) VALUES (?, ?)", (current_mode, float(size)))


def reset_portfolio_size(mode: Optional[str] = None) -> bool:
    """Remove the stored portfolio size for a mode. Returns whether one existed."""
    current_mode = _resolve_mode(mode)
    with _connect() as conn:
        return conn.execute("DELETE FROM portfolio WHERE mode = ?", (current_mode,)).rowcount > 0


def _normalize_mode_value(mode: str) -> str:
    aliases = {
        'planning': 'paper',
        'paper': 'paper',
        'live': 'live',
    }
    return aliases.get((mode or '').lower(), '')


def load_mode():
    """Load trading mode, defaults to live."""
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'mode'").fetchone()
    return (_normalize_mode_value(row[0]) if row else '') or DEFAULT_MODE


def save_mode(mode):
    """Save trading mode"""
    with _connect() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('mode', ?)", (mode,))


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
            # Skip _index field - it's a special field for tracking the trade id
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
