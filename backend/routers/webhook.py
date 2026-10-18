"""TradingView webhook: turns alerts into sized trade plans."""

import hmac
import logging
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from models import PositionSizeRequest, StopLoss, TakeProfit, TradeData
from routers.calculations import calculate_position_size
from routers.trades import add_trade
from storage import load_portfolio_size, save_portfolio_size

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhook", tags=["webhook"])


class WebhookTrade(BaseModel):
    action: str = "add_trade"
    asset: str = "BTC"
    direction: str = "long"
    entry: float = 0
    sl: float = 0
    leverage: int = 10
    risk_pct: float = 2.0
    portfolio_size: Optional[float] = None
    tp1: float = 0
    tp1_alloc: float = 50
    tp2: float = 0
    tp2_alloc: float = 30
    tp3: float = 0
    tp3_alloc: float = 20
    tp4: float = 0
    tp4_alloc: float = 0
    mode: str = "paper"
    # TradingView alerts cannot set custom headers, so the secret may travel in the body
    secret: Optional[str] = None

def verify_webhook_secret(provided: Optional[str]):
    """Reject webhook calls unless they carry TRADELAB_WEBHOOK_SECRET. Disabled when unset."""
    expected = os.getenv("TRADELAB_WEBHOOK_SECRET", "")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Webhook disabled: set TRADELAB_WEBHOOK_SECRET in backend/.env to enable it",
        )
    if not provided or not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

@router.post("/trade")
async def webhook_trade(data: WebhookTrade, x_webhook_secret: Optional[str] = Header(default=None)):
    """Receive trade plans from TradingView alerts via webhook."""
    verify_webhook_secret(x_webhook_secret or data.secret)
    try:
        direction = data.direction.lower().strip()
        if direction not in ["long", "short"]:
            direction = "long"

        mode = data.mode if data.mode in ["paper", "live"] else "paper"

        if data.portfolio_size and data.portfolio_size > 0:
            save_portfolio_size(data.portfolio_size, mode)

        tps = []
        if data.tp1 > 0:
            tps.append({"price": data.tp1, "allocation": data.tp1_alloc / 100.0})
        if data.tp2 > 0:
            tps.append({"price": data.tp2, "allocation": data.tp2_alloc / 100.0})
        if data.tp3 > 0:
            tps.append({"price": data.tp3, "allocation": data.tp3_alloc / 100.0})
        if data.tp4 > 0:
            tps.append({"price": data.tp4, "allocation": data.tp4_alloc / 100.0})

        sls = []
        if data.sl > 0:
            sls.append({"price": data.sl, "allocation": 1.0})

        portfolio = load_portfolio_size(mode)
        if portfolio <= 0:
            portfolio = data.portfolio_size if data.portfolio_size else 200.0
            save_portfolio_size(portfolio, mode)

        risk_pct = data.risk_pct if data.risk_pct > 0 else 2.0
        pos_result = calculate_position_size(
            PositionSizeRequest(
                entry_price=data.entry,
                stop_loss=data.sl,
                leverage=data.leverage,
                direction=direction,
                risk_percentage=risk_pct,
            ),
            mode,
        )
        position_size = pos_result.get("position_size_dollars", 0)
        margin = pos_result.get("margin_required", 0)

        result = add_trade(
            TradeData(
                asset=data.asset,
                direction=direction,
                entry_price=data.entry,
                stop_loss=data.sl if data.sl > 0 else 0,
                position_size=position_size,
                take_profits=[TakeProfit(**tp) for tp in tps],
                stop_losses=[StopLoss(**sl) for sl in sls],
                margin=margin,
                leverage=data.leverage,
            ),
            mode,
        )

        return {
            "status": "success",
            "message": f"Trade saved: {data.asset} {direction} @ ${data.entry:,.2f}",
            "position_size": position_size,
            "margin_required": margin,
            "risk_amount": pos_result.get("risk_amount", 0),
            "rr_ratio": pos_result.get("rr_ratio", 0) if data.sl > 0 else 0,
            "liquidation_price": pos_result.get("liquidation_price", 0),
            "trade_index": result.get("trade_index"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Webhook trade error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
