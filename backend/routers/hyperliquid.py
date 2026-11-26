"""Hyperliquid exchange integration: market data, positions and live order execution."""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from models import StopLoss, TakeProfit
from storage import load_mode

logger = logging.getLogger(__name__)

try:
    from hyperliquid_client import hl_client, round_price
except ImportError:
    hl_client = None
    round_price = None

router = APIRouter(prefix="/api/hyperliquid", tags=["hyperliquid"])

# Allocations may sum to 100% give or take rounding in the browser (e.g. 3 x 33.333%)
ALLOCATION_TOLERANCE = 1e-4
DEFAULT_SZ_DECIMALS = 5
# How long to wait after a close before checking the position is actually gone
CLOSE_CONFIRM_DELAY_SECONDS = 2


def check_execution_allowed():
    """Check if execution is allowed based on current mode. Raises 403 if blocked."""
    mode = load_mode()
    if mode != "live":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "mode_blocked",
                "mode": mode,
                "reason": "Execution endpoints are blocked in paper mode. Switch to live mode to execute trades."
            }
        )


def _first_status(result: Any) -> Dict:
    """The first entry of an order response's `response.data.statuses`, or {}."""
    response = result.get("response") if isinstance(result, dict) else None
    if not isinstance(response, dict):
        return {}
    statuses = (response.get("data") or {}).get("statuses") or []
    return statuses[0] if statuses and isinstance(statuses[0], dict) else {}


def _order_error(result: Any) -> Optional[str]:
    """The exchange's reason an order call was rejected, or None if it was accepted.

    Hyperliquid reports per-order rejections as status "ok" with an `error` entry in
    `statuses`, so checking the top-level status alone is not enough.
    """
    if not isinstance(result, dict):
        return "no response from exchange"
    if result.get("status") != "ok":
        return str(result.get("message") or result.get("response") or "unknown error")
    error = _first_status(result).get("error")
    return str(error) if error else None


def _sz_decimals(coin: str) -> int:
    asset_data = hl_client.get_asset_metadata()
    if isinstance(asset_data, dict) and coin in asset_data:
        return asset_data[coin].get("sz_decimals", DEFAULT_SZ_DECIMALS)
    return DEFAULT_SZ_DECIMALS


def _find_position(positions: List[Dict], coin: str) -> Optional[Dict]:
    """The open position whose coin is exactly `coin`, ignoring case (so ETH never matches ETHFI)."""
    wanted = coin.strip().upper()
    for position in positions:
        if str(position.get("coin") or "").upper() == wanted and position.get("size"):
            return position
    return None


@router.get("/status")
def get_hyperliquid_status():
    """Get Hyperliquid integration status"""
    if not hl_client:
        return {"enabled": False, "connected": False, "message": "Hyperliquid client not available"}

    return {
        "enabled": hl_client.enabled,
        "connected": hl_client.info_client is not None,
        "testnet": hl_client.use_testnet if hl_client.enabled else None,
        "wallet_address": hl_client.wallet_address if hl_client.enabled else None
    }

@router.get("/price/{coin}")
def get_hyperliquid_price(coin: str):
    """Get current price for a coin"""
    if not hl_client:
        raise HTTPException(status_code=503, detail="Hyperliquid client not available")

    price = hl_client.get_current_price(coin.upper())
    if price is None:
        raise HTTPException(status_code=404, detail=f"Price not available for {coin}")

    return {"coin": coin.upper(), "price": price, "timestamp": datetime.now().isoformat()}

@router.get("/positions")
def get_hyperliquid_positions(coin: Optional[str] = None):
    """Get open positions from Hyperliquid"""
    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="Hyperliquid integration not enabled")

    if not hl_client.wallet_address:
        raise HTTPException(status_code=400, detail="Wallet address not configured")

    positions = hl_client.get_positions(coin.upper() if coin else None)
    return {"positions": positions, "count": len(positions)}

@router.get("/assets")
def get_hyperliquid_assets():
    """Get available assets and their max leverage from Hyperliquid"""
    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="Hyperliquid integration not enabled")

    asset_data = hl_client.get_asset_metadata()
    if asset_data is None:
        raise HTTPException(status_code=500, detail="Failed to fetch asset metadata")

    # Format for frontend
    assets = []
    for name, data in asset_data.items():
        assets.append({
            "symbol": name,
            "max_leverage": data["max_leverage"],
            "sz_decimals": data["sz_decimals"],
            "only_isolated": data["only_isolated"]
        })

    return {"assets": assets, "count": len(assets)}

class HyperliquidOrderRequest(BaseModel):
    coin: str
    is_buy: bool
    # Margin to commit in USD: the position's notional is margin_amount x leverage
    margin_amount: float = Field(gt=0)
    leverage: int = Field(ge=1)
    entry_price: float  # the browser's price, for logging only; orders use a server-fetched price
    # Allocations are fractions of the filled position (0-1)
    take_profits: List[TakeProfit] = []
    stop_losses: List[StopLoss] = []
    is_isolated: bool = True

    @model_validator(mode="after")
    def allocations_fit_the_position(self):
        for label, levels in (("Take profit", self.take_profits), ("Stop loss", self.stop_losses)):
            total = sum(level.allocation for level in levels)
            if total > 1 + ALLOCATION_TOLERANCE:
                raise ValueError(f"{label} allocations add up to {total:.2%}; they cannot exceed 100% of the position")
        return self

def _place_protection(levels, kind: str, filled_size: float, sz_decimals: int, place) -> List[str]:
    """
    Place TP or SL orders sized as fractions of what actually filled. `place(size, price)` sends one
    order and returns the exchange response. Returns a warning for each level that was not accepted.
    """
    warnings = []
    allocated = 0.0
    for number, level in enumerate(levels, start=1):
        if level.price <= 0 or level.allocation <= 0:
            continue
        price = round_price(level.price, sz_decimals)
        # Cap at what's left so per-level rounding can never add up to more than the position
        size = min(round(filled_size * level.allocation, sz_decimals), round(filled_size - allocated, sz_decimals))
        allocated += max(size, 0)
        if price <= 0 or size <= 0:
            error = f"size {size} or price {price} rounds to zero"
        else:
            try:
                error = _order_error(place(size, price))
            except Exception as e:
                logger.exception(f"Failed to place {kind} {number}")
                error = str(e)
        if error:
            message = f"{kind} {number} at ${price:,} was not placed: {error}."
            if kind == "Stop loss":
                message += " That part of the position has no stop on Hyperliquid; set one there manually."
            logger.error(message)
            warnings.append(message)
    return warnings

@router.post("/order")
def place_hyperliquid_order(request: HyperliquidOrderRequest):
    """
    Open a position with an IOC (market-style) entry, then place reduce-only TP limits and SL triggers
    sized from what actually filled.

    `status` is "success" when the entry filled and every TP/SL was accepted. If the entry filled but
    any of them was not, `status` is "partial" and `warnings` says what is missing: the position is
    open either way, so the caller should still journal it, using `avg_price` and `notional`.
    """
    check_execution_allowed()

    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="Hyperliquid integration not enabled")

    if not hl_client.exchange_client:
        raise HTTPException(status_code=400, detail="Exchange client not configured - check wallet credentials")

    # Size from a price the server fetches itself, not the one the browser sent
    current_price = hl_client.get_current_price(request.coin)
    if current_price is None:
        raise HTTPException(status_code=400, detail="Could not fetch current market price. Please try again.")
    logger.debug(f"Using real-time price: {current_price} (frontend sent: {request.entry_price})")

    sz_decimals = _sz_decimals(request.coin)
    position_size_units = round((request.margin_amount * request.leverage) / current_price, sz_decimals)
    if position_size_units <= 0:
        raise HTTPException(status_code=400, detail="Order size rounds to zero; increase the margin")

    # Hyperliquid has no true market order: use an IOC limit with a 0.2% buffer
    limit_px = round_price(current_price * (1.002 if request.is_buy else 0.998), sz_decimals)
    if limit_px <= 0:
        raise HTTPException(status_code=400, detail=f"Price {current_price} cannot be expressed as a valid {request.coin} order price")
    logger.info(f"Order: {request.coin} | Size: {position_size_units} | Leverage: {request.leverage}x | Margin: ${request.margin_amount:.2f} @ {limit_px}")

    warnings = []
    exchange = hl_client.exchange_client

    # Set leverage BEFORE placing the order (per-coin setting)
    try:
        exchange.update_leverage(request.leverage, request.coin, not request.is_isolated)
    except Exception as e:
        logger.warning(f"Could not set leverage: {e}")
        warnings.append(f"Could not set {request.leverage}x leverage ({e}); the position uses the coin's existing leverage setting.")

    try:
        result = exchange.order(
            name=request.coin,
            is_buy=request.is_buy,
            sz=position_size_units,
            limit_px=limit_px,
            order_type={"limit": {"tif": "Ioc"}},
            reduce_only=False,
            cloid=None,
        )
    except Exception as e:
        logger.exception("Entry order request failed")
        raise HTTPException(status_code=502, detail=f"Order request failed: {e}. Check Hyperliquid before retrying.")
    logger.debug(f"Order result: {result}")

    error = _order_error(result)
    if error:
        raise HTTPException(status_code=400, detail=f"Order failed: {error}")

    filled = _first_status(result).get("filled") or {}
    filled_size = float(filled.get("totalSz") or 0)
    avg_price = float(filled.get("avgPx") or 0)
    if filled_size <= 0 or avg_price <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"Entry order reported no fill ({_first_status(result) or result}); check Hyperliquid before retrying.",
        )

    close_is_buy = not request.is_buy
    warnings += _place_protection(
        request.take_profits, "Take profit", filled_size, sz_decimals,
        lambda size, price: exchange.order(
            name=request.coin, is_buy=close_is_buy, sz=size, limit_px=price,
            order_type={"limit": {"tif": "Gtc"}}, reduce_only=True, cloid=None,
        ),
    )
    warnings += _place_protection(
        request.stop_losses, "Stop loss", filled_size, sz_decimals,
        lambda size, price: hl_client.place_stop_order(
            coin=request.coin, is_buy=request.is_buy, size=size, trigger_price=price,
            is_long_position=request.is_buy,
        ),
    )

    notional = filled_size * avg_price
    return {
        "status": "partial" if warnings else "success",
        "order_id": filled.get("oid"),
        "requested_size": position_size_units,
        "filled_size": filled_size,
        "avg_price": avg_price,
        "notional": notional,
        "margin_used": notional / request.leverage,
        "leverage": request.leverage,
        "warnings": warnings,
        "message": f"Order filled: {filled_size} {request.coin} @ ${avg_price:,.2f} at {request.leverage}x leverage",
    }

latest_btc_price = {"price": None, "timestamp": None}

@router.get("/ws-price")
def get_ws_price():
    """Get latest BTC price from WebSocket feed"""
    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="Hyperliquid integration not enabled")

    # For now, return REST API price (WebSocket will be implemented next)
    price = hl_client.get_current_price("BTC")
    if price:
        latest_btc_price["price"] = price
        latest_btc_price["timestamp"] = datetime.now().isoformat()

    return latest_btc_price

class ClosePositionRequest(BaseModel):
    # Coin units to close (one journal trade's share); omit to close the whole position.
    # More than the position holds closes all of it.
    size: Optional[float] = Field(default=None, gt=0)

@router.post("/close/{coin}")
def close_hyperliquid_position(coin: str, request: ClosePositionRequest):
    """
    Close `size` units of the position in `coin` (or all of it) with a market order and return the fill price.

    The coin must match an open position exactly. The JSON body is required, even if it's just `{}`,
    so a cross-site form post can't trigger a close.
    """
    check_execution_allowed()

    if not hl_client:
        raise HTTPException(status_code=503, detail="Hyperliquid client not initialized")

    # Ensure client is initialized
    hl_client._ensure_initialized()

    if not hl_client.enabled:
        raise HTTPException(status_code=503, detail="Hyperliquid integration not enabled")

    if not hl_client.exchange_client:
        raise HTTPException(status_code=400, detail="Exchange client not configured - check wallet credentials")

    try:
        all_positions = hl_client.get_positions(None)
        position = _find_position(all_positions, coin)
        if not position:
            available_coins = [p.get('coin') for p in all_positions]
            raise HTTPException(
                status_code=400,
                detail=f"No open position found for {coin.upper()}. Open positions: {available_coins}"
            )

        actual_coin = position['coin']
        position_size = abs(float(position['size']))
        sz_decimals = _sz_decimals(actual_coin)
        tolerance = 10 ** -sz_decimals / 2

        if request.size is None or request.size >= position_size - tolerance:
            close_size = None  # the whole position
            target_remaining = 0.0
        else:
            close_size = round(request.size, sz_decimals)
            if close_size <= 0:
                raise HTTPException(status_code=400, detail=f"Close size {request.size} rounds to zero")
            target_remaining = position_size - close_size

        logger.info(f"Closing {close_size or 'all'} of {actual_coin} position: size={position['size']}, entry=${position.get('entry_price')}")
        result = hl_client.market_close(actual_coin, sz=close_size)
        logger.debug(f"market_close result: {result}")

        # Verify the position actually shrank to the target; if not, send a reduce-only IOC for the shortfall
        time.sleep(CLOSE_CONFIRM_DELAY_SECONDS)
        after = _find_position(hl_client.get_positions(actual_coin), actual_coin)
        remaining = float(after['size']) if after else 0.0
        shortfall = round(abs(remaining) - target_remaining, sz_decimals)

        if shortfall > tolerance:
            logger.warning(f"{actual_coin} position is {remaining} after market_close (target {target_remaining}); closing the remaining {shortfall}")
            current_price = hl_client.get_current_price(actual_coin)
            if current_price:
                is_buy_to_close = remaining < 0  # a short is closed by buying
                try:
                    alt_result = hl_client.exchange_client.order(
                        name=actual_coin,
                        is_buy=is_buy_to_close,
                        sz=shortfall,
                        limit_px=round_price(current_price * (1.002 if is_buy_to_close else 0.998), sz_decimals),  # Small buffer
                        order_type={"limit": {"tif": "Ioc"}},
                        reduce_only=True,
                        cloid=None
                    )
                    logger.debug(f"Alternative close result: {alt_result}")
                    if not _order_error(alt_result):
                        result = alt_result
                except Exception as alt_error:
                    logger.exception(f"Alternative close method failed: {alt_error}")

        error = _order_error(result)
        if error:
            raise HTTPException(status_code=400, detail=f"Close position failed: {error}")

        filled = _first_status(result).get("filled") or {}
        fill_price = float(filled.get("avgPx") or 0) or None
        if not fill_price:
            fill_price = hl_client.get_current_price(actual_coin)
            logger.warning(f"Could not extract fill price from result, using current price: ${fill_price}")

        return {
            "status": "success",
            "coin": actual_coin,
            "closed_size": float(filled.get("totalSz") or 0) or (close_size or position_size),
            "fill_price": fill_price,
            "result": result,
            "message": f"Position closed for {actual_coin} at ${fill_price:.2f}" if fill_price
                       else f"Position closed for {actual_coin} (fill price unavailable)",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error closing position: {e}")
        raise HTTPException(status_code=500, detail=f"Error closing position: {str(e)}")
