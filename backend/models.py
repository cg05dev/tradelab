"""Request models shared across routers."""

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

# Allocations are fractions of the position (0.5 = half), never percentages. The bounds turn a
# percent sent by mistake (50 instead of 0.5) into a 422 instead of a 50x order or P&L.
Allocation = Annotated[float, Field(ge=0, le=1, description="Fraction of the position, 0-1")]


class TakeProfit(BaseModel):
    price: float
    allocation: Allocation

class StopLoss(BaseModel):
    price: float
    allocation: Allocation

class ExchangeOrders(BaseModel):
    """Hyperliquid order ids of a live trade, as the order endpoint returns them. The TP/SL lists
    line up with the trade's levels; None where a level wasn't placed."""
    entry: Optional[int] = None
    take_profits: List[Optional[int]] = []
    stop_losses: List[Optional[int]] = []

class TradeData(BaseModel):
    asset: str
    direction: str
    entry_price: float
    stop_loss: float
    position_size: float
    take_profits: List[TakeProfit]
    stop_losses: List[StopLoss]
    thesis: Optional[str] = None
    margin: Optional[float] = None
    leverage: Optional[int] = None
    exchange_orders: Optional[ExchangeOrders] = None  # live trades placed through TradeLab

class PositionSizeRequest(BaseModel):
    entry_price: float
    stop_loss: float
    leverage: float
    direction: str
    risk_percentage: Optional[float] = None

class CloseTradeRequest(BaseModel):
    trade_index: int
    exit_price: float


class UpdatePortfolioRequest(BaseModel):
    portfolio_size: float

class ModeUpdateRequest(BaseModel):
    mode: str
