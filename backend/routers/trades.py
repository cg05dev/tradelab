import io
import json
import logging
from datetime import datetime
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile

from models import CloseTradeRequest, PartialCloseRequest, StopLossHitRequest, TradeData
from storage import (
    JOURNAL_COLUMNS,
    clean_trade_data,
    load_mode,
    load_portfolio_size,
    load_trades,
    save_portfolio_size,
    save_trades,
)

logger = logging.getLogger(__name__)

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
        logger.exception(f"Error in get_closed_trades: {e}")
        return {"trades": [], "count": 0}

@router.get("/closed/count")
def get_closed_trades_count(mode: Optional[str] = None):
    try:
        current_mode = mode or load_mode()
        df = load_trades(current_mode)
        if df.empty or 'Status' not in df.columns:
            return {"count": 0}
        return {"count": int((df['Status'] == 'Closed').sum())}
    except Exception as e:
        logger.exception(f"Error in get_closed_trades_count: {e}")
        return {"count": 0}

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
        
        df = load_trades(current_mode)
        
        new_trade = {
            'Date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
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
        
        new_row = pd.DataFrame([new_trade])
        if df.empty:
            # Keep the journal's full column set without concatenating an empty frame
            df = new_row.reindex(columns=df.columns.union(new_row.columns, sort=False))
        else:
            df = pd.concat([df, new_row], ignore_index=True)
        save_trades(df, current_mode)
        
        return {"message": "Trade added successfully", "trade_index": len(df) - 1}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/close")
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

@router.post("/partial-close")
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

@router.post("/stop-loss-hit")
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

@router.delete("/clear")
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

@router.delete("/{trade_index}")
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

@router.post("/import")
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
