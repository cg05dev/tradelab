import traceback
from typing import Optional

import pandas as pd
from fastapi import APIRouter

from storage import load_mode, load_trades

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


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

@router.get("/metrics")
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
        gross_profit = float(wins.sum()) if len(wins) else 0
        gross_loss = abs(float(losses.sum())) if len(losses) else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
        cumulative_pnl = pnl_series.cumsum()
        running_peak = cumulative_pnl.cummax().clip(lower=0)
        drawdown = cumulative_pnl - running_peak
        max_drawdown = abs(float(drawdown.min())) if len(drawdown) else 0
        return {
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
            "trade_count": int(len(pnl_series)),
            "win_count": int(len(wins)),
            "loss_count": int(len(losses)),
        }
    except Exception as e:
        print(f"Error in get_analytics_metrics: {e}")
        traceback.print_exc()
        return {"total_pnl": 0, "win_rate": 0, "avg_win": 0, "avg_loss": 0}

@router.get("/pnl-series")
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
            {
                'date': row['Date'].isoformat() if pd.notna(row['Date']) else None,
                'asset': row.get('Asset'),
                'pnl': float(row['P&L']),
                'cumulative_pnl': float(row['cumulative_pnl']),
            }
            for _, row in closed.iterrows()
        ]
    except Exception as e:
        print(f"Error in get_pnl_series: {e}")
        traceback.print_exc()
        return []

@router.get("/overview")
def get_analytics_overview(mode: Optional[str] = None):
    """Get trading analytics overview"""
    try:
        current_mode = mode or load_mode()
        df = load_trades(current_mode)
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
