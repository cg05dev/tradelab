"""Request models shared across routers."""

from typing import List, Optional

from pydantic import BaseModel


class TakeProfit(BaseModel):
    price: float
    allocation: float

class StopLoss(BaseModel):
    price: float
    allocation: float

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

class PositionSizeRequest(BaseModel):
    entry_price: float
    stop_loss: float
    leverage: float
    direction: str
    risk_percentage: Optional[float] = None

class CloseTradeRequest(BaseModel):
    trade_index: int
    exit_price: float

class PartialCloseRequest(BaseModel):
    trade_index: int
    tp_price: float
    tp_allocation: float
    tp_index: int

class StopLossHitRequest(BaseModel):
    trade_index: int
    sl_price: float
    sl_allocation: float
    sl_index: int

class UpdatePortfolioRequest(BaseModel):
    portfolio_size: float

class ModeUpdateRequest(BaseModel):
    mode: str
