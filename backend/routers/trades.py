import json
import logging
from datetime import datetime
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

import fees
import fill_sync
import paper_sim
from models import CloseTradeRequest, TradeData
from storage import (
    clean_trade_data,
    closed_dates,
    insert_trade,
    load_mode,
    load_trades,
    local_time,
    update_trade,
)
from storage import delete_trade as delete_trade_row

logger = logging.getLogger(__name__)

try:
    from hyperliquid_client import hl_client
except ImportError:
    hl_client = None

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("")
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
        logger.exception(f"Error in get_trades: {e}")
        return {"trades": []}

@router.get("/open")
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
        logger.exception(f"Error in get_open_trades: {e}")
        return {"trades": []}

@router.get("/closed")
def get_closed_trades(asset=None, start=None, end=None, sort=None, page=None, limit=None, search=None, mode: Optional[str] = None):
    """Get closed trades with optional filtering, sorting, and pagination"""
    try:
        current_mode = mode or load_mode()
        df = load_trades(current_mode)
        if df.empty or 'Status' not in df.columns:
            return {"trades": []}

        closed_trades = df[df['Status'] == 'Closed'].copy()


        if asset:
            closed_trades = closed_trades[closed_trades['Asset'].astype(str).str.contains(asset, case=False, na=False)]

        # Dates refer to when a trade closed. A date-only `end` includes that whole day.
        closed_trades['_closed'] = closed_dates(closed_trades)
        if start:
            start_dt = pd.to_datetime(start, errors='coerce')
            if pd.notna(start_dt):
                closed_trades = closed_trades[closed_trades['_closed'] >= start_dt]

        if end:
            end_dt = pd.to_datetime(end, errors='coerce')
            if pd.notna(end_dt):
                if len(str(end).strip()) == 10:
                    closed_trades = closed_trades[closed_trades['_closed'] < end_dt + pd.Timedelta(days=1)]
                else:
                    closed_trades = closed_trades[closed_trades['_closed'] <= end_dt]

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
        elif sort == 'date_asc':
            closed_trades = closed_trades.sort_values(by='_closed', ascending=True)
        else:  # date_desc, the default
            closed_trades = closed_trades.sort_values(by='_closed', ascending=False)
        closed_trades = closed_trades.drop(columns='_closed')

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
        logger.exception(f"Error in get_closed_trades: {e}")
        return {"trades": [], "count": 0}


@router.post("")
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

        new_trade = {
            'Date': local_time(),
            'Asset': trade_data.asset.strip(),
            'Direction': trade_data.direction.lower(),
            'Entry': float(trade_data.entry_price),
            'SL': float(trade_data.stop_loss) if trade_data.stop_loss > 0 else 0.0,
            'TPs': json.dumps([tp.model_dump() for tp in trade_data.take_profits]),
            'SLs': json.dumps([sl.model_dump() for sl in trade_data.stop_losses]),
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

        trade_id = insert_trade(new_trade, current_mode)
        if current_mode == "paper":
            # Paper trades pay fees like live ones: the entry is a market (taker) order
            paper_sim.charge_entry(trade_id, new_trade['Position_Size'], fees.current_rates(hl_client))
        orders = trade_data.exchange_orders
        if orders and current_mode == "live":
            # So the fills of these orders are credited to this trade when they happen
            fill_sync.claim_orders(trade_id, [(orders.entry, "entry", None)]
                                   + [(oid, "take_profit", i) for i, oid in enumerate(orders.take_profits)]
                                   + [(oid, "stop_loss", i) for i, oid in enumerate(orders.stop_losses)])

        return {"message": "Trade added successfully", "trade_index": trade_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/close")
def close_trade(request: CloseTradeRequest, mode: Optional[str] = None):
    """Close a trade"""
    current_mode = mode or load_mode()
    df = load_trades(current_mode)

    # Use loc for actual DataFrame index (not positional)
    if request.trade_index not in df.index:
        raise HTTPException(status_code=400, detail=f"Invalid trade index: {request.trade_index}. Valid indices: {list(df.index)}")

    trade = df.loc[request.trade_index]
    updates = {}

    if trade['Status'] != 'Open':
        raise HTTPException(status_code=400, detail="Trade is already closed")

    # Calculate P&L
    entry_price = trade['Entry']
    direction = trade['Direction']

    if direction == 'long':
        pnl = (request.exit_price - entry_price) / entry_price * trade['Position_Size']
    else:
        pnl = (entry_price - request.exit_price) / entry_price * trade['Position_Size']
    if current_mode == 'paper':
        # A paper close is a market order: it pays the taker fee, as a live one would
        units = trade['Position_Size'] / entry_price if entry_price else 0
        pnl -= fees.current_rates(hl_client)['taker'] * request.exit_price * units

    # Calculate hold time
    entry_date = pd.to_datetime(trade['Date'])
    exit_date = datetime.now()
    hold_time = (exit_date - entry_date).total_seconds() / 3600

    # Update trade
    updates['Status'] = 'Closed'
    updates['Exit_Price'] = request.exit_price
    # Add to what earlier partial exits (and a paper trade's entry fee) already made
    prior_pnl = trade['P&L'] if pd.notna(trade['P&L']) else 0.0
    updates['P&L'] = prior_pnl + pnl
    updates['Hold_Time'] = f"{hold_time:.1f}h"
    updates['Closed_At'] = local_time()

    # Update portfolio size
    portfolio_delta = pnl

    new_portfolio_size = update_trade(request.trade_index, updates, current_mode, portfolio_delta)

    return {
        "message": "Trade closed successfully",
        "pnl": pnl,
        "new_portfolio_size": new_portfolio_size
    }


@router.delete("/{trade_index}")
def delete_trade(trade_index: int, mode: Optional[str] = None):
    """Delete a trade by id"""
    current_mode = mode or load_mode()
    if not delete_trade_row(trade_index, current_mode):
        raise HTTPException(status_code=400, detail="Invalid trade index")

    return {
        "message": "Trade deleted successfully",
        "trade_index": trade_index
    }

