"""
Portfolio size per mode.

- Paper mode: the balance the user enters, adjusted by the P&L of closed paper trades.
- Live mode: always the connected Hyperliquid account's value (equity, including unrealized P&L).
  It can't be entered by hand, so live orders are never sized from an out-of-date number.
"""

import logging
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException

from models import UpdatePortfolioRequest
from storage import _resolve_mode, load_portfolio_size, reset_portfolio_size, save_portfolio_size

logger = logging.getLogger(__name__)

try:
    from hyperliquid_client import hl_client
except ImportError:
    hl_client = None

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

NOT_CONNECTED = "Connect your Hyperliquid account in Settings to use live mode."
UNREACHABLE = "Couldn't reach Hyperliquid to get your account value. Try again shortly."
LIVE_IS_SYNCED = "The live portfolio is your Hyperliquid account value and can't be set by hand."


def resolve_portfolio(mode: Optional[str] = None) -> Dict:
    """
    The portfolio for a mode and where it came from:
    - source "manual": paper mode's entered balance.
    - source "hyperliquid": the live account's value. `stale` is true when Hyperliquid couldn't be
      reached and this is the last value fetched. With no value yet, `portfolio_size` is None.
    - source "none": live mode with no account connected; `portfolio_size` is None.
    """
    if _resolve_mode(mode) == "paper":
        return {"portfolio_size": load_portfolio_size("paper"), "source": "manual"}
    if not (hl_client and hl_client.enabled):
        return {"portfolio_size": None, "source": "none", "sync_error": NOT_CONNECTED}
    try:
        summary = hl_client.get_account_summary()
        return {"portfolio_size": summary["account_value"], "source": "hyperliquid", "stale": False, **summary}
    except Exception as e:
        logger.warning(f"Could not fetch Hyperliquid account value: {e}")
        last = hl_client.last_account_summary()
        if last:
            return {"portfolio_size": last["account_value"], "source": "hyperliquid", "stale": True, **last}
        return {"portfolio_size": None, "source": "hyperliquid", "stale": True, "sync_error": UNREACHABLE}


def _paper_only(mode: Optional[str]):
    if _resolve_mode(mode) != "paper":
        raise HTTPException(status_code=400, detail=LIVE_IS_SYNCED)


@router.post("/reset")
def reset_portfolio(mode: Optional[str] = None):
    """Reset the paper balance"""
    _paper_only(mode)
    try:
        if reset_portfolio_size("paper"):
            return {"message": "Portfolio reset successfully"}
        return {"message": "Portfolio was not set"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resetting portfolio: {str(e)}") from e

@router.get("")
def get_portfolio(mode: Optional[str] = None):
    """Get current portfolio size and its source"""
    return resolve_portfolio(mode)

@router.put("")
def update_portfolio(request: UpdatePortfolioRequest, mode: Optional[str] = None):
    """Set the paper balance"""
    if request.portfolio_size < 0:
        raise HTTPException(status_code=400, detail="Portfolio size cannot be negative")
    _paper_only(mode)
    save_portfolio_size(request.portfolio_size, "paper")
    return {"portfolio_size": request.portfolio_size, "message": "Portfolio size updated"}
