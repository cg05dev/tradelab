from typing import Optional

from fastapi import APIRouter

import fees
from models import PositionSizeRequest
from risk import liquidation_price
from routers.portfolio import portfolio_size_for
from storage import load_mode

try:
    from hyperliquid_client import hl_client
except ImportError:
    hl_client = None

router = APIRouter(prefix="/api/calculate", tags=["calculations"])

DEFAULT_RISK_PCT = 2.0


def _empty(message: str) -> dict:
    return {"position_size_dollars": 0, "position_size_units": 0, "margin_required": 0, "risk_amount": 0, "message": message}


@router.post("/position-size")
def calculate_position_size(request: PositionSizeRequest, mode: Optional[str] = None):
    """Size a position so the loss at the stop, fees and slippage included, is the risk amount.

    Without a stop, the position is sized against its liquidation price, as the planner does.
    """
    if request.entry_price <= 0:
        return _empty("Please enter an entry price")
    if request.leverage <= 0:
        return _empty("Invalid leverage")

    portfolio_size = portfolio_size_for(mode or load_mode())
    risk_amount = portfolio_size * (request.risk_percentage or DEFAULT_RISK_PCT) / 100
    rates = fees.current_rates(hl_client)

    liquidation = liquidation_price(request.entry_price, request.leverage, request.direction)
    exit_price = request.stop_loss or liquidation
    distance = abs(request.entry_price - exit_price) / request.entry_price
    if distance == 0:
        return _empty("Stop loss cannot equal entry price")

    position_size_dollars = risk_amount / (distance + fees.cost_at_stop(rates))
    position_size_units = position_size_dollars / request.entry_price
    margin_required = position_size_dollars / request.leverage
    return {
        "position_size_dollars": position_size_dollars,
        "position_size_units": position_size_units,
        "margin_required": margin_required,
        "risk_amount": risk_amount,
        "sl_percentage": distance * 100,
        "liquidation_price": liquidation,
        # Breakdown of the loss at the stop (or liquidation)
        "price_loss": position_size_dollars * distance,
        "fees_at_stop": position_size_dollars * 2 * rates["taker"],
        "slippage_at_stop": position_size_dollars * rates["stop_slippage"],
        "fee_rates": rates,
        "message": f"Margin: ${margin_required:,.2f} | Position: {position_size_units:.6f} units",
    }
