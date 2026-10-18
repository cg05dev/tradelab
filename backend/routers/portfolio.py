from typing import Optional

from fastapi import APIRouter, HTTPException

from models import UpdatePortfolioRequest
from storage import load_portfolio_size, reset_portfolio_size, save_portfolio_size

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.post("/reset")
def reset_portfolio(mode: Optional[str] = None):
    """Reset the stored portfolio size for the selected mode"""
    try:
        if reset_portfolio_size(mode):
            return {"message": "Portfolio reset successfully"}
        return {"message": "Portfolio was not set"}
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
