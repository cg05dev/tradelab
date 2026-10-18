import os
from typing import Optional

from fastapi import APIRouter, HTTPException

from models import UpdatePortfolioRequest
from storage import _get_mode_file, load_portfolio_size, save_portfolio_size

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.post("/reset")
def reset_portfolio(mode: Optional[str] = None):
    """Reset portfolio configuration file for the selected mode"""
    try:
        portfolio_file = _get_mode_file(mode)['portfolio']
        if os.path.exists(portfolio_file):
            os.remove(portfolio_file)
            return {"message": "Portfolio reset successfully"}
        return {"message": "Portfolio file does not exist"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resetting portfolio: {str(e)}")

@router.get("")
def get_portfolio(mode: Optional[str] = None):
    """Get current portfolio size"""
    return {"portfolio_size": load_portfolio_size(mode)}

@router.put("")
def update_portfolio(request: UpdatePortfolioRequest, mode: Optional[str] = None):
    """Update portfolio size"""
    if request.portfolio_size < 0:
        raise HTTPException(status_code=400, detail="Portfolio size cannot be negative")
    save_portfolio_size(request.portfolio_size, mode)
    return {"portfolio_size": request.portfolio_size, "message": "Portfolio size updated"}
