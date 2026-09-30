"""
TradeLab Core Business Logic
All trade management, portfolio, analytics, and calculation functions.
No HTTP/API dependencies — pure business logic.
"""

import json
import math
import os
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from trade_calculator import trade_calc, TradeCalculator

try:
    from hyperliquid_client import hl_client
    _HL_AVAILABLE = True
except ImportError:
    hl_client = None
    _HL_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


def _normalize_mode(mode: Optional[str] = None) -> str:
    if mode in DATA_FILES:
        return mode
    return load_mode() if mode is None else DEFAULT_MODE


def _get_mode_file(mode: Optional[str] = None) -> dict:
    current_mode = _normalize_mode(mode)
    return DATA_FILES[current_mode]


def _ensure_paper_files_exist():
    paper_files = DATA_FILES['paper']
    if not os.path.exists(paper_files['trades']):
        pd.DataFrame(columns=JOURNAL_COLUMNS).to_csv(paper_files['trades'], index=False)
    if not os.path.exists(paper_files['portfolio']):
        with open(paper_files['portfolio'], 'w') as f:
            json.dump({'portfolio_size': 0}, f)


def _normalize_mode_value(mode: str) -> str:
    aliases = {
        'planning': 'paper',
        'paper': 'paper',
        'live': 'live',
    }
    return aliases.get((mode or '').lower(), '')


def load_trades(mode: Optional[str] = None) -> pd.DataFrame:
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


def save_trades(df: pd.DataFrame, mode: Optional[str] = None):
    files = _get_mode_file(mode)
    if mode == 'paper':
        _ensure_paper_files_exist()
    df.to_csv(files['trades'], index=False)


def load_portfolio_size(mode: Optional[str] = None) -> float:
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


def load_risk_pct(mode: Optional[str] = None) -> float:
    try:
        files = _get_mode_file(mode)
        if mode == 'paper':
            _ensure_paper_files_exist()
        if os.path.exists(files['portfolio']):
            with open(files['portfolio'], 'r') as f:
                config = json.load(f)
                return config.get('risk_pct', RISK_PCT * 100)
        return RISK_PCT * 100
    except Exception:
        return RISK_PCT * 100


def save_portfolio_size(size: float, mode: Optional[str] = None):
    files = _get_mode_file(mode)
    if mode == 'paper':
        _ensure_paper_files_exist()
    risk_pct = load_risk_pct(mode)
    with open(files['portfolio'], 'w') as f:
        json.dump({'portfolio_size': size, 'risk_pct': risk_pct}, f)


def save_portfolio_config(size: float, risk_pct: float, mode: Optional[str] = None):
    files = _get_mode_file(mode)
    if mode == 'paper':
        _ensure_paper_files_exist()
    with open(files['portfolio'], 'w') as f:
        json.dump({'portfolio_size': size, 'risk_pct': risk_pct}, f)


def load_mode() -> str:
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
    except Exception:
        try:
            with open(MODE_FILE, 'w') as f:
                json.dump({'mode': DEFAULT_MODE}, f)
        except Exception:
            pass
        return DEFAULT_MODE


def save_mode(mode: str):
    try:
        with open(MODE_FILE, 'w') as f:
            json.dump({'mode': mode}, f)
    except Exception as e:
        print(f"[ERROR] Error saving mode: {e}")


def add_trade(
    asset: str,
    direction: str,
    entry_price: float,
    stop_loss: float,
    position_size: float,
    take_profits: List[Dict],
    stop_losses: List[Dict],
    thesis: Optional[str] = None,
    margin: Optional[float] = None,
    leverage: Optional[int] = None,
    mode: Optional[str] = None,
) -> dict:
    current_mode = mode or load_mode()

    if entry_price <= 0:
        raise ValueError("Entry price must be greater than 0")
    if direction.lower() not in ['long', 'short']:
        raise ValueError("Direction must be 'long' or 'short'")
    if stop_loss > 0:
        if direction.lower() == 'long' and stop_loss >= entry_price:
            raise ValueError("Stop loss must be below entry price for long positions")
        if direction.lower() == 'short' and stop_loss <= entry_price:
            raise ValueError("Stop loss must be above entry price for short positions")
    for tp in take_profits:
        if tp.get('price', 0) > 0:
            if direction.lower() == 'long' and tp['price'] <= entry_price:
                raise ValueError(f"Take profit {tp['price']} must be above entry price for long positions")
            if direction.lower() == 'short' and tp['price'] >= entry_price:
                raise ValueError(f"Take profit {tp['price']} must be below entry price for short positions")

    df = load_trades(current_mode)

    new_trade = {
        'Date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'Asset': asset.strip(),
        'Direction': direction.lower(),
        'Entry': float(entry_price),
        'SL': float(stop_loss) if stop_loss > 0 else 0.0,
        'TPs': json.dumps([tp if isinstance(tp, dict) else tp.dict() for tp in take_profits]),
        'SLs': json.dumps([sl if isinstance(sl, dict) else sl.dict() for sl in stop_losses]),
        'Position_Size': float(position_size),
        'Thesis': str(thesis) if thesis else '',
        'Status': 'Open',
        'Exit_Price': None,
        'P&L': 0.0,
        'Hold_Time': None,
        'TP_Hit': False,
        'TP_Price': None,
        'SL_Hit': False,
        'SL_Price': None,
        'Hit_TPs': json.dumps([]),
        'Margin': float(margin) if margin is not None else float(position_size) / int(leverage) if leverage else 0.0,
        'Leverage': int(leverage) if leverage else 1,
    }

    df = pd.concat([df, pd.DataFrame([new_trade])], ignore_index=True)
    save_trades(df, current_mode)

    return {"message": "Trade added successfully", "trade_index": len(df) - 1}


def close_trade(trade_index: int, exit_price: float, mode: Optional[str] = None) -> dict:
    current_mode = mode or load_mode()
    df = load_trades(current_mode)

    if trade_index not in df.index:
        raise ValueError(f"Invalid trade index: {trade_index}")

    trade = df.loc[trade_index]

    if trade['Status'] != 'Open':
        raise ValueError("Trade is already closed")

    entry_price = trade['Entry']
    direction = trade['Direction']

    if direction == 'long':
        pnl = (exit_price - entry_price) / entry_price * trade['Position_Size']
    else:
        pnl = (entry_price - exit_price) / entry_price * trade['Position_Size']

    entry_date = pd.to_datetime(trade['Date'])
    exit_date = datetime.now()
    hold_time = (exit_date - entry_date).total_seconds() / 3600

    df.at[trade_index, 'Status'] = 'Closed'
    df.at[trade_index, 'Exit_Price'] = exit_price
    df.at[trade_index, 'P&L'] = pnl
    df.at[trade_index, 'Hold_Time'] = f"{hold_time:.1f}h"

    portfolio_size = load_portfolio_size(current_mode)
    new_portfolio_size = portfolio_size + pnl
    save_portfolio_size(new_portfolio_size, current_mode)

    save_trades(df, current_mode)

    return {
        "message": "Trade closed successfully",
        "pnl": pnl,
        "new_portfolio_size": new_portfolio_size,
    }


def partial_close_trade(
    trade_index: int,
    tp_price: float,
    tp_allocation: float,
    tp_index: int,
    mode: Optional[str] = None,
) -> dict:
    current_mode = mode or load_mode()
    df = load_trades(current_mode)

    if trade_index not in df.index:
        raise ValueError(f"Invalid trade index: {trade_index}")

    trade = df.loc[trade_index]

    if trade['Status'] != 'Open':
        raise ValueError("Trade is already closed")

    entry_price = trade['Entry']
    direction = trade['Direction']
    total_position_size = trade['Position_Size']
    allocated_position_size = total_position_size * tp_allocation

    if direction == 'long':
        pnl = (tp_price - entry_price) / entry_price * allocated_position_size
    else:
        pnl = (entry_price - tp_price) / entry_price * allocated_position_size

    portfolio_size = load_portfolio_size(current_mode)
    new_portfolio_size = portfolio_size + pnl
    save_portfolio_size(new_portfolio_size, current_mode)

    remaining_position_size = total_position_size - allocated_position_size

    df.at[trade_index, 'Position_Size'] = remaining_position_size
    df.at[trade_index, 'TP_Hit'] = True
    df.at[trade_index, 'TP_Price'] = tp_price

    hit_tps = json.loads(trade['Hit_TPs']) if trade['Hit_TPs'] else []
    hit_tps.append(tp_index)
    df.at[trade_index, 'Hit_TPs'] = json.dumps(hit_tps)

    current_pnl = trade['P&L'] if pd.notna(trade['P&L']) else 0.0
    df.at[trade_index, 'P&L'] = current_pnl + pnl

    all_tps = json.loads(trade['TPs']) if trade['TPs'] else []
    is_last_tp = (tp_index == len(all_tps) - 1) or (len(all_tps) == 1)

    if is_last_tp or remaining_position_size < total_position_size * 0.01:
        if direction == 'long':
            remaining_pnl = (tp_price - entry_price) / entry_price * remaining_position_size
        else:
            remaining_pnl = (entry_price - tp_price) / entry_price * remaining_position_size

        entry_date = pd.to_datetime(trade['Date'])
        exit_date = datetime.now()
        hold_time = (exit_date - entry_date).total_seconds() / 3600

        df.at[trade_index, 'Status'] = 'Closed'
        df.at[trade_index, 'Exit_Price'] = tp_price
        df.at[trade_index, 'P&L'] = current_pnl + pnl + remaining_pnl
        df.at[trade_index, 'Hold_Time'] = f"{hold_time:.1f}h"

        portfolio_size = load_portfolio_size(current_mode)
        new_portfolio_size = portfolio_size + remaining_pnl
        save_portfolio_size(new_portfolio_size, current_mode)

    save_trades(df, current_mode)

    return {
        "message": "TP hit - trade partially closed" if remaining_position_size > 0 else "TP hit - trade fully closed",
        "pnl": pnl,
        "remaining_position_size": remaining_position_size,
        "new_portfolio_size": new_portfolio_size,
    }


def stop_loss_hit(
    trade_index: int,
    sl_price: float,
    sl_allocation: float,
    sl_index: int,
    mode: Optional[str] = None,
) -> dict:
    current_mode = mode or load_mode()
    df = load_trades(current_mode)

    if trade_index not in df.index:
        raise ValueError(f"Invalid trade index: {trade_index}")

    trade = df.loc[trade_index]

    if trade['Status'] != 'Open':
        raise ValueError("Trade is already closed")

    entry_price = trade['Entry']
    direction = trade['Direction']
    total_position_size = trade['Position_Size']
    allocated_position_size = total_position_size * sl_allocation

    if direction == 'long':
        pnl = (sl_price - entry_price) / entry_price * allocated_position_size
    else:
        pnl = (entry_price - sl_price) / entry_price * allocated_position_size

    portfolio_size = load_portfolio_size(current_mode)
    new_portfolio_size = portfolio_size + pnl
    save_portfolio_size(new_portfolio_size, current_mode)

    remaining_position_size = total_position_size - allocated_position_size

    df.at[trade_index, 'Position_Size'] = remaining_position_size
    df.at[trade_index, 'SL_Hit'] = True
    df.at[trade_index, 'SL_Price'] = sl_price

    current_pnl = trade['P&L'] if pd.notna(trade['P&L']) else 0.0
    df.at[trade_index, 'P&L'] = current_pnl + pnl

    all_sls = json.loads(trade['SLs']) if trade['SLs'] else []
    is_last_sl = (sl_index == len(all_sls) - 1) or (len(all_sls) == 1)

    if is_last_sl or remaining_position_size < total_position_size * 0.01:
        if direction == 'long':
            remaining_pnl = (sl_price - entry_price) / entry_price * remaining_position_size
        else:
            remaining_pnl = (entry_price - sl_price) / entry_price * remaining_position_size

        entry_date = pd.to_datetime(trade['Date'])
        exit_date = datetime.now()
        hold_time = (exit_date - entry_date).total_seconds() / 3600

        df.at[trade_index, 'Status'] = 'Closed'
        df.at[trade_index, 'Exit_Price'] = sl_price
        df.at[trade_index, 'P&L'] = current_pnl + pnl + remaining_pnl
        df.at[trade_index, 'Hold_Time'] = f"{hold_time:.1f}h"

        portfolio_size = load_portfolio_size(current_mode)
        new_portfolio_size = portfolio_size + remaining_pnl
        save_portfolio_size(new_portfolio_size, current_mode)

    save_trades(df, current_mode)

    return {
        "message": "SL hit - trade partially closed" if remaining_position_size > 0 else "SL hit - trade fully closed",
        "pnl": pnl,
        "remaining_position_size": remaining_position_size,
        "new_portfolio_size": new_portfolio_size,
    }


def delete_trade(trade_index: int, mode: Optional[str] = None) -> dict:
    current_mode = mode or load_mode()
    df = load_trades(current_mode)

    if trade_index >= len(df) or trade_index < 0:
        raise ValueError("Invalid trade index")

    df = df.drop(df.index[trade_index]).reset_index(drop=True)
    save_trades(df, current_mode)

    return {"message": "Trade deleted successfully", "trade_index": trade_index}


def clear_all_trades(mode: Optional[str] = None) -> dict:
    current_mode = mode or load_mode()
    empty_df = pd.DataFrame(columns=JOURNAL_COLUMNS)
    save_trades(empty_df, current_mode)
    return {"message": "All trades cleared successfully", "trades_count": 0}


def get_open_trades(mode: Optional[str] = None) -> List[dict]:
    current_mode = mode or load_mode()
    df = load_trades(current_mode)
    if df.empty or 'Status' not in df.columns:
        return []
    open_trades = df[df['Status'] == 'Open']
    return _clean_trade_data(open_trades)


def get_closed_trades(
    asset: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    sort: Optional[str] = None,
    page: Optional[int] = None,
    limit: Optional[int] = None,
    search: Optional[str] = None,
    mode: Optional[str] = None,
) -> dict:
    current_mode = mode or load_mode()
    df = load_trades(current_mode)
    if df.empty or 'Status' not in df.columns:
        return {"trades": [], "count": 0}

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
        page_num = max(int(page or 1), 1)
        limit_num = max(int(limit or 25), 1)
        start_idx = (page_num - 1) * limit_num
        end_idx = start_idx + limit_num
        closed_trades = closed_trades.iloc[start_idx:end_idx]

    trades_list = _clean_trade_data(closed_trades)
    return {"trades": trades_list, "count": total_count}


def get_all_trades(mode: Optional[str] = None) -> List[dict]:
    current_mode = mode or load_mode()
    df = load_trades(current_mode)
    if df.empty:
        return []
    return _clean_trade_data(df)


def calculate_position_size(
    entry_price: float,
    stop_loss: float,
    leverage: float,
    direction: str,
    risk_percentage: Optional[float] = None,
    mode: Optional[str] = None,
) -> dict:
    current_mode = mode or load_mode()
    portfolio_size = load_portfolio_size(current_mode)
    risk_pct = risk_percentage / 100 if risk_percentage else RISK_PCT
    risk_amount = portfolio_size * risk_pct

    if entry_price == 0:
        return {
            "position_size_dollars": 0, "position_size_units": 0,
            "margin_required": 0, "risk_amount": 0,
            "message": "Please enter an entry price",
        }

    if stop_loss == 0 or stop_loss is None:
        if direction.lower() == 'long':
            liquidation_price = entry_price * (1 - 1 / leverage)
        else:
            liquidation_price = entry_price * (1 + 1 / leverage)
        price_diff = abs(entry_price - liquidation_price)
        if price_diff == 0:
            return {
                "position_size_dollars": 0, "position_size_units": 0,
                "margin_required": 0, "risk_amount": 0,
                "message": "Invalid leverage",
            }
        liquidation_percentage = price_diff / entry_price
        position_size_dollars = risk_amount / liquidation_percentage
        position_size_units = position_size_dollars / entry_price
        margin_required = position_size_dollars / leverage
        verified_position_size = margin_required * leverage
        return {
            "position_size_dollars": position_size_dollars,
            "position_size_units": position_size_units,
            "margin_required": margin_required,
            "risk_amount": risk_amount,
            "sl_percentage": liquidation_percentage * 100,
            "liquidation_price": liquidation_price,
            "verification": f"${margin_required:,.2f} margin × {leverage}x = ${verified_position_size:,.2f} position",
            "message": f"Margin: ${margin_required:,.2f} | Position: {position_size_units:.6f} units",
        }

    price_diff = abs(entry_price - stop_loss)
    if price_diff == 0:
        return {
            "position_size_dollars": 0, "position_size_units": 0,
            "margin_required": 0, "risk_amount": 0,
            "message": "Stop loss cannot equal entry price",
        }

    sl_percentage = price_diff / entry_price
    position_size_dollars = risk_amount / sl_percentage
    position_size_units = position_size_dollars / entry_price
    margin_required = position_size_dollars / leverage
    verified_position_size = margin_required * leverage

    return {
        "position_size_dollars": position_size_dollars,
        "position_size_units": position_size_units,
        "margin_required": margin_required,
        "risk_amount": risk_amount,
        "sl_percentage": sl_percentage * 100,
        "verification": f"${margin_required:,.2f} margin × {leverage}x = ${verified_position_size:,.2f} position",
        "message": f"Margin: ${margin_required:,.2f} | Position: {position_size_units:.6f} units",
    }


def calculate_risk_reward(
    entry_price: float,
    stop_loss: float,
    take_profits: List[Dict],
    direction: str,
) -> dict:
    if not take_profits or len(take_profits) == 0:
        return {"rr_ratio": 0, "message": "No take profits set"}

    try:
        rr_ratio = trade_calc.calculate_rr_ratio(
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profits=take_profits,
            direction=direction,
        )
        return {
            "rr_ratio": rr_ratio,
            "message": f"Risk/Reward: 1:{rr_ratio:.2f}" if rr_ratio > 0 else "Invalid setup",
        }
    except Exception as e:
        return {"rr_ratio": 0, "message": f"Calculation error: {str(e)}"}


def calculate_profit_loss(
    entry_price: float,
    stop_loss: float,
    position_size: float,
    take_profits: List[Dict],
    stop_losses: List[Dict],
    direction: str,
    leverage: Optional[float] = None,
) -> dict:
    if position_size <= 0:
        return {"take_profits": [], "stop_losses": [], "message": "Invalid position size"}

    total_tp_allocation = sum(tp.get('allocation', 0) for tp in take_profits)
    total_sl_allocation = sum(sl.get('allocation', 0) for sl in stop_losses)

    tp_results = []
    for i, tp in enumerate(take_profits):
        if tp.get('price', 0) > 0:
            if direction == 'long':
                profit_per_unit = tp['price'] - entry_price
            else:
                profit_per_unit = entry_price - tp['price']

            if total_tp_allocation > 0:
                normalized_allocation = tp.get('allocation', 0) / total_tp_allocation
            else:
                normalized_allocation = tp.get('allocation', 0)

            allocated_position_size = position_size * normalized_allocation
            position_units = allocated_position_size / entry_price
            profit_amount = position_units * profit_per_unit

            tp_results.append({
                "index": i,
                "price": tp['price'],
                "allocation": tp.get('allocation', 0),
                "profit_amount": profit_amount,
                "normalized_allocation": normalized_allocation,
            })

    sl_results = []
    for i, sl in enumerate(stop_losses):
        if sl.get('price', 0) > 0:
            if direction == 'long':
                loss_per_unit = entry_price - sl['price']
            else:
                loss_per_unit = sl['price'] - entry_price

            if total_sl_allocation > 0:
                normalized_allocation = sl.get('allocation', 0) / total_sl_allocation
            else:
                normalized_allocation = sl.get('allocation', 0)

            allocated_position_size = position_size * normalized_allocation
            position_units = allocated_position_size / entry_price
            loss_amount = position_units * loss_per_unit

            sl_results.append({
                "index": i,
                "price": sl['price'],
                "allocation": sl.get('allocation', 0),
                "loss_amount": loss_amount,
                "normalized_allocation": normalized_allocation,
            })

    if len(sl_results) == 0 and stop_loss == 0 and leverage and leverage > 0:
        margin = position_size / leverage
        sl_results.append({
            "index": 0,
            "price": 0,
            "allocation": 1.0,
            "loss_amount": margin,
            "normalized_allocation": 1.0,
            "is_liquidation": True,
        })

    return {"take_profits": tp_results, "stop_losses": sl_results, "message": ""}


def calculate_trade_details(
    portfolio_size: float,
    risk_percentage: float,
    entry_price: float,
    stop_loss: float,
    take_profits: List[Dict],
    leverage: float,
    direction: str,
    market_volume_24h: float = 0,
    is_maker: bool = False,
) -> dict:
    try:
        details = trade_calc.calculate_complete_trade(
            portfolio_size=portfolio_size,
            risk_percentage=risk_percentage,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profits=take_profits,
            leverage=leverage,
            direction=direction,
            market_volume_24h=market_volume_24h or 0,
            is_maker=is_maker or False,
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
            "message": f"R/R: 1:{details.rr_ratio:.2f} | Breakeven: ${details.breakeven_price:.2f}",
        }
    except Exception as e:
        return {"error": str(e), "message": f"Calculation error: {str(e)}"}


def get_analytics_overview(mode: Optional[str] = None) -> dict:
    current_mode = mode or load_mode()
    df = load_trades(current_mode)
    if df.empty:
        return {
            "total_trades": 0, "open_trades": 0,
            "winning_trades": 0, "losing_trades": 0,
            "win_rate": 0, "total_pnl": 0,
        }

    if 'Status' not in df.columns:
        return {
            "total_trades": len(df), "open_trades": 0,
            "winning_trades": 0, "losing_trades": 0,
            "win_rate": 0, "total_pnl": 0,
        }

    closed_trades = df[df['Status'] == 'Closed']
    open_trades_count = len(df[df['Status'] == 'Open'])
    total_trades = len(df)

    if len(closed_trades) > 0 and 'P&L' in closed_trades.columns:
        winning_trades = len(closed_trades[closed_trades['P&L'] > 0])
        losing_trades = len(closed_trades[closed_trades['P&L'] < 0])
        win_rate = (winning_trades / len(closed_trades)) * 100
        total_pnl = closed_trades['P&L'].sum()
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
        "total_pnl": total_pnl,
    }


def get_analytics_metrics(timeframe: str = 'all', mode: Optional[str] = None) -> dict:
    current_mode = mode or load_mode()
    df = load_trades(current_mode)
    if df.empty or 'Status' not in df.columns:
        return {"total_pnl": 0, "win_rate": 0, "avg_win": 0, "avg_loss": 0}
    closed = df[df['Status'] == 'Closed'].copy()
    if closed.empty:
        return {"total_pnl": 0, "win_rate": 0, "avg_win": 0, "avg_loss": 0}
    closed['Date'] = pd.to_datetime(closed['Date'], errors='coerce')
    closed = _apply_timeframe_filter(closed, timeframe)
    pnl_series = pd.to_numeric(closed['P&L'], errors='coerce').fillna(0)
    total_pnl = float(pnl_series.sum())
    wins = pnl_series[pnl_series > 0]
    losses = pnl_series[pnl_series < 0]
    win_rate = float(len(wins) / len(pnl_series) * 100) if len(pnl_series) else 0
    avg_win = float(wins.mean()) if len(wins) else 0
    avg_loss = float(losses.mean()) if len(losses) else 0
    return {"total_pnl": total_pnl, "win_rate": win_rate, "avg_win": avg_win, "avg_loss": avg_loss}


def get_pnl_series(timeframe: str = 'all', mode: Optional[str] = None) -> list:
    current_mode = mode or load_mode()
    df = load_trades(current_mode)
    if df.empty or 'Status' not in df.columns:
        return []
    closed = df[df['Status'] == 'Closed'].copy()
    if closed.empty:
        return []
    closed['Date'] = pd.to_datetime(closed['Date'], errors='coerce')
    closed = _apply_timeframe_filter(closed, timeframe)
    if closed.empty:
        return []
    closed = closed.sort_values('Date')
    closed['P&L'] = pd.to_numeric(closed['P&L'], errors='coerce').fillna(0)
    closed['cumulative_pnl'] = closed['P&L'].cumsum()
    return [
        {'date': row['Date'].strftime('%Y-%m-%d') if pd.notna(row['Date']) else None,
         'cumulative_pnl': float(row['cumulative_pnl'])}
        for _, row in closed.iterrows()
    ]


def _apply_timeframe_filter(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
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


def _clean_trade_data(df: pd.DataFrame) -> List[dict]:
    if '_index' not in df.columns:
        df = df.copy()
        df['_index'] = df.index
    df = df.replace([float('inf'), float('-inf')], None)
    df = df.where(pd.notnull(df), None)
    trades_list = df.to_dict('records')

    for trade in trades_list:
        for key, value in trade.items():
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


def get_current_price(coin: str = "BTC") -> Optional[float]:
    """Get current price from Hyperliquid. Returns None if unavailable."""
    if not _HL_AVAILABLE or hl_client is None:
        return None
    try:
        return hl_client.get_current_price(coin.upper())
    except Exception:
        return None


def calculate_unrealized_pnl(trade: dict, current_price: Optional[float] = None) -> Optional[float]:
    """Calculate unrealized P&L for an open trade.
    If current_price is None, attempts to fetch from Hyperliquid.
    """
    if not trade.get('Entry') or trade.get('Status') != 'Open':
        return None

    entry = trade['Entry']
    position_size = trade.get('Position_Size', 0) or 0
    direction = (trade.get('Direction') or 'long').lower()
    asset = trade.get('Asset', '')

    if current_price is None and asset:
        coin = asset.split('-')[0] if '-' in asset else asset
        current_price = get_current_price(coin)

    if current_price is None:
        return None

    if direction == 'long':
        pnl = (current_price - entry) * (position_size / entry)
    else:
        pnl = (entry - current_price) * (position_size / entry)

    return pnl


def calculate_liquidation_price(entry: float, leverage: float, direction: str,
                                  maintenance_margin: float = 0.0125) -> float:
    """Calculate liquidation price for a trade."""
    liquidation_threshold = (1 / leverage) - maintenance_margin
    if direction.lower() == 'long':
        return entry * (1 - liquidation_threshold)
    else:
        return entry * (1 + liquidation_threshold)


def toggle_mode() -> str:
    """Toggle between paper and live mode. Returns the new mode."""
    current = load_mode()
    new_mode = 'paper' if current == 'live' else 'live'
    save_mode(new_mode)
    return new_mode