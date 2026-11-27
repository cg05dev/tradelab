"""Hyperliquid exchange integration: market data, positions and live order execution."""

import logging
import secrets
import time
from contextlib import nullcontext
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

import fees
import fill_sync
from models import ExchangeOrders, StopLoss, TakeProfit, TradeData
from routers.trades import record_trade, validate_levels
from storage import load_mode, load_trades

logger = logging.getLogger(__name__)

try:
    from hyperliquid_client import hl_client, round_price
except ImportError:
    hl_client = None
    round_price = None

try:
    from hyperliquid.utils.types import Cloid
except ImportError:
    Cloid = None

router = APIRouter(prefix="/api/hyperliquid", tags=["hyperliquid"])

# Allocations may sum to 100% give or take rounding in the browser (e.g. 3 x 33.333%)
ALLOCATION_TOLERANCE = 1e-4
DEFAULT_SZ_DECIMALS = 5
# How long to wait after a close before checking the position is actually gone
CLOSE_CONFIRM_DELAY_SECONDS = 2
# When an entry request fails without an answer (a timeout, a dropped connection), how many times,
# and how far apart, to ask Hyperliquid whether the order was placed anyway
ENTRY_LOOKUP_ATTEMPTS = 3
ENTRY_LOOKUP_DELAY_SECONDS = 1.0


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
def get_hyperliquid_positions():
    """The connected account's open positions, with Hyperliquid's own liquidation price for each."""
    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="No Hyperliquid account connected. Connect one in Settings.")
    return {"positions": hl_client.get_positions()}


@router.get("/assets")
def get_hyperliquid_assets():
    """Get available assets and their max leverage from Hyperliquid (public; no account needed)"""
    if not hl_client or not hl_client.info_client:
        raise HTTPException(status_code=503, detail="Hyperliquid market data unavailable")

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
    # For the journal entry the order is saved as (asset defaults to "<coin>-USDC")
    asset: Optional[str] = None
    thesis: Optional[str] = None

    @model_validator(mode="after")
    def allocations_fit_the_position(self):
        for label, levels in (("Take profit", self.take_profits), ("Stop loss", self.stop_losses)):
            total = sum(level.allocation for level in levels)
            if total > 1 + ALLOCATION_TOLERANCE:
                raise ValueError(f"{label} allocations add up to {total:.2%}; they cannot exceed 100% of the position")
        return self

def _order_oid(result: Any) -> Optional[int]:
    """The oid of an accepted order: resting (TP limits, stop triggers) or filled immediately."""
    status = _first_status(result)
    return (status.get("resting") or status.get("filled") or {}).get("oid")


def _place_protection(levels, kind: str, filled_size: float, sz_decimals: int, place) -> Tuple[List[str], List[Optional[int]]]:
    """
    Place TP or SL orders sized as fractions of what actually filled. `place(size, price)` sends one
    order and returns the exchange response. Returns a warning for each level that was not accepted,
    and each level's oid (None if it wasn't placed), in the order of `levels`.
    """
    warnings = []
    oids: List[Optional[int]] = []
    allocated = 0.0
    for number, level in enumerate(levels, start=1):
        oids.append(None)
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
                result = place(size, price)
                error = _order_error(result)
                if not error:
                    oids[-1] = _order_oid(result)
            except Exception as e:
                logger.exception(f"Failed to place {kind} {number}")
                error = str(e)
        if error:
            message = f"{kind} {number} at ${price:,} was not placed: {error}."
            if kind == "Stop loss":
                message += " That part of the position has no stop on Hyperliquid; set one there manually."
            logger.error(message)
            warnings.append(message)
    return warnings, oids

def _new_cloid() -> str:
    """A random client order id (16 bytes as 0x-prefixed hex), so an order can be looked up even if
    the request that placed it never got an answer."""
    return "0x" + secrets.token_hex(16)


def _entry_fill_after_error(cloid: str, since_ms: int) -> Optional[Dict]:
    """
    After an entry request failed without an answer, ask Hyperliquid whether the order was placed.

    Returns None if Hyperliquid has no order with this cloid (it was never placed), otherwise
    {"oid", "totalSz", "avgPx"} like a filled status. "totalSz" is 0 if it was placed but didn't fill,
    and "avgPx" is None if its fills haven't been reported yet. Raises if Hyperliquid can't be asked.
    """
    error: Optional[Exception] = None
    for attempt in range(ENTRY_LOOKUP_ATTEMPTS):
        if attempt:
            time.sleep(ENTRY_LOOKUP_DELAY_SECONDS)
        try:
            status = hl_client.order_status(cloid)
        except Exception as e:
            logger.warning(f"Could not look up order {cloid}: {e}")
            error = e
            continue
        error = None
        if status.get("status") != "order":
            continue  # unknownOid: possibly still in flight, so ask again
        order = (status.get("order") or {}).get("order") or {}
        oid = order.get("oid")
        filled_size = float(order.get("origSz") or 0) - float(order.get("sz") or 0)
        avg_price = None
        if filled_size > 0:
            try:
                fills = [f for f in hl_client.get_user_fills(since_ms) if f.get("oid") == oid]
            except Exception:
                logger.exception(f"Could not fetch the fills of order {oid}")
                fills = []
            size = sum(float(f["sz"]) for f in fills)
            if size > 0:
                filled_size = size
                avg_price = sum(float(f["px"]) * float(f["sz"]) for f in fills) / size
        return {"oid": oid, "totalSz": filled_size, "avgPx": avg_price}
    if error:
        raise error
    return None


@router.post("/order")
def place_hyperliquid_order(request: HyperliquidOrderRequest):
    """
    Open a position with an IOC (market-style) entry, place reduce-only TP limits and SL triggers sized
    from what actually filled, and save the trade to the live journal.

    The journal entry is written here, in the same request as the order, so a filled order is never
    left out of the journal because the browser went away. `trade_index` is the new trade.

    `status` is "success" when the entry filled and every TP/SL was accepted. If the entry filled but
    any of them was not, `status` is "partial" and `warnings` says what is missing.
    """
    check_execution_allowed()

    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="No Hyperliquid account connected. Connect one in Settings.")

    if not hl_client.exchange_client:
        raise HTTPException(status_code=400, detail="Trading isn't enabled for this account. Enable it in Settings.")

    # Size from a price the server fetches itself, not the one the browser sent
    current_price = hl_client.get_current_price(request.coin)
    if current_price is None:
        raise HTTPException(status_code=400, detail="Could not fetch current market price. Please try again.")
    logger.debug(f"Using real-time price: {current_price} (frontend sent: {request.entry_price})")

    direction = "long" if request.is_buy else "short"
    # Checked before trading, so a filled order is never refused by the journal afterwards
    validate_levels(direction, current_price, [sl.price for sl in request.stop_losses], [tp.price for tp in request.take_profits])

    sz_decimals = _sz_decimals(request.coin)
    position_size_units = round((request.margin_amount * request.leverage) / current_price, sz_decimals)
    if position_size_units <= 0:
        raise HTTPException(status_code=400, detail="Order size rounds to zero; increase the margin")

    # Hyperliquid has no true market order: use an IOC limit with a 0.2% buffer
    limit_px = round_price(current_price * (1.002 if request.is_buy else 0.998), sz_decimals)
    if limit_px <= 0:
        raise HTTPException(status_code=400, detail=f"Price {current_price} cannot be expressed as a valid {request.coin} order price")
    logger.info(f"Order: {request.coin} | Size: {position_size_units} | Leverage: {request.leverage}x | Margin: ${request.margin_amount:.2f} @ {limit_px}")

    # Nothing may sync fills until this trade is journaled and has claimed its orders, so its
    # entry fill can't be credited to another trade first
    with fill_sync.lock:
        return _place_order(request, direction, current_price, position_size_units, limit_px, sz_decimals)


def _place_order(request: HyperliquidOrderRequest, direction: str, current_price: float,
                 position_size_units: float, limit_px: float, sz_decimals: int):
    warnings = []
    exchange = hl_client.exchange_client

    # Set leverage BEFORE placing the order (per-coin setting)
    try:
        exchange.update_leverage(request.leverage, request.coin, not request.is_isolated)
    except Exception as e:
        logger.warning(f"Could not set leverage: {e}")
        warnings.append(f"Could not set {request.leverage}x leverage ({e}); the position uses the coin's existing leverage setting.")

    cloid = _new_cloid()
    sent_ms = int(time.time() * 1000) - 60_000
    try:
        result = exchange.order(
            name=request.coin,
            is_buy=request.is_buy,
            sz=position_size_units,
            limit_px=limit_px,
            order_type={"limit": {"tif": "Ioc"}},
            reduce_only=False,
            cloid=Cloid.from_str(cloid),
        )
        logger.debug(f"Order result: {result}")
        error = _order_error(result)
        if error:
            raise HTTPException(status_code=400, detail=f"Order failed: {error}")
        filled = _first_status(result).get("filled") or {}
    except HTTPException:
        raise
    except Exception as e:
        # No answer: the order may or may not have reached the exchange. Ask Hyperliquid by its cloid.
        logger.exception(f"Entry order request failed; looking up order {cloid}")
        try:
            filled = _entry_fill_after_error(cloid, sent_ms)
        except Exception as lookup_error:
            logger.critical(f"Entry order {cloid} for {request.coin} has an unknown outcome: {lookup_error}")
            raise HTTPException(
                status_code=502,
                detail=f"The order request failed ({e}) and Hyperliquid couldn't be asked whether it was placed. "
                       "Don't place it again: check Open Trades, which flags any position the journal is missing.",
            ) from e
        if filled is None:
            raise HTTPException(
                status_code=502,
                detail=f"The order request failed ({e}). Hyperliquid has no record of it, so nothing was placed.",
            ) from e
        if filled["totalSz"] > 0:
            logger.warning(f"Entry order {cloid} filled despite the failed request: {filled}")
            if filled["avgPx"] is None:
                filled["avgPx"] = current_price
                warnings.append("The entry filled, but its fill price wasn't available yet, so the journal's entry price is the market price.")

    filled_size = float(filled.get("totalSz") or 0)
    avg_price = float(filled.get("avgPx") or 0)
    if filled_size <= 0 or avg_price <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"Entry order reported no fill ({filled or result}); check Hyperliquid before retrying.",
        )

    close_is_buy = not request.is_buy
    tp_warnings, tp_oids = _place_protection(
        request.take_profits, "Take profit", filled_size, sz_decimals,
        lambda size, price: exchange.order(
            name=request.coin, is_buy=close_is_buy, sz=size, limit_px=price,
            order_type={"limit": {"tif": "Gtc"}}, reduce_only=True, cloid=None,
        ),
    )
    sl_warnings, sl_oids = _place_protection(
        request.stop_losses, "Stop loss", filled_size, sz_decimals,
        lambda size, price: hl_client.place_stop_order(
            coin=request.coin, is_buy=request.is_buy, size=size, trigger_price=price,
            is_long_position=request.is_buy,
        ),
    )
    warnings += tp_warnings + sl_warnings

    notional = filled_size * avg_price
    order_ids = {"entry": filled.get("oid"), "take_profits": tp_oids, "stop_losses": sl_oids}
    trade_index = None
    try:
        trade_index = record_trade(TradeData(
            asset=(request.asset or f"{request.coin}-USDC").strip(),
            direction=direction,
            entry_price=avg_price,
            stop_loss=next((sl.price for sl in request.stop_losses if sl.price > 0), 0.0),
            position_size=notional,
            take_profits=request.take_profits,
            stop_losses=request.stop_losses,
            thesis=request.thesis,
            margin=notional / request.leverage,
            leverage=request.leverage,
            exchange_orders=ExchangeOrders(**order_ids),
        ), "live")
    except Exception as e:
        logger.critical(f"Order {filled.get('oid')} FILLED ({filled_size} {request.coin} @ {avg_price}) but couldn't be journaled: {e}")
        warnings.append(
            f"The order filled, but saving it to the journal failed ({e}). "
            "Open Trades flags the position, and you can add it to the journal from there."
        )

    return {
        "status": "partial" if warnings else "success",
        "order_id": filled.get("oid"),
        "order_ids": order_ids,
        "trade_index": trade_index,
        "journaled": trade_index is not None,
        "requested_size": position_size_units,
        "filled_size": filled_size,
        "avg_price": avg_price,
        "notional": notional,
        "margin_used": notional / request.leverage,
        "leverage": request.leverage,
        "warnings": warnings,
        "message": f"Order filled: {filled_size} {request.coin} @ ${avg_price:,.2f} at {request.leverage}x leverage",
    }

# A journal and exchange size this close (as a fraction of the larger) count as the same
RECONCILE_TOLERANCE = 0.01


def _journal_positions() -> Dict[str, Dict]:
    """The open live journal trades netted per coin (upper case): {coin: {"size": signed coin units,
    "trade_ids": [...]}}, long positive. Fill sync keeps each trade's Position_Size at what's left."""
    df = load_trades("live")
    netted: Dict[str, Dict] = {}
    if df.empty or "Status" not in df.columns:
        return netted
    for trade_id, row in df[df["Status"] == "Open"].iterrows():
        coin = fill_sync.coin_of(row.get("Asset"))
        entry = float(row.get("Entry") or 0)
        if not coin or entry <= 0:
            continue
        units = float(row.get("Position_Size") or 0) / entry
        sign = -1 if str(row.get("Direction") or "").lower() == "short" else 1
        bucket = netted.setdefault(coin, {"size": 0.0, "trade_ids": []})
        bucket["size"] += sign * units
        bucket["trade_ids"].append(int(trade_id))
    return netted


def _same_size(a: float, b: float) -> bool:
    return abs(a - b) <= max(abs(a), abs(b)) * RECONCILE_TOLERANCE + 1e-12


def _untracked_size(exchange_size: float, journal_size: float) -> float:
    """How much of the exchange position no open journal trade accounts for (signed), or 0 if the
    journal accounts for all of it or more."""
    if exchange_size == 0 or _same_size(exchange_size, journal_size):
        return 0.0
    if journal_size and (journal_size > 0) != (exchange_size > 0):
        return 0.0  # opposite directions: not something adding a trade fixes
    extra = exchange_size - journal_size
    return extra if (extra > 0) == (exchange_size > 0) else 0.0


def _fetch_positions_or_502() -> List[Dict]:
    try:
        return hl_client.fetch_positions()
    except Exception as e:
        logger.exception("Could not fetch Hyperliquid positions")
        raise HTTPException(status_code=502, detail=f"Couldn't fetch positions from Hyperliquid: {e}") from e


def _describe(coin: str, size: float) -> str:
    return f"{abs(size):g} {coin} {'long' if size > 0 else 'short'}"


@router.get("/reconcile")
def reconcile_positions():
    """
    Compare the account's open positions on Hyperliquid with the open live journal trades, coin by
    coin. Fills are applied first, so a TP or stop that just filled isn't reported.

    Each issue is one coin: "untracked" (a position the journal has no trade for), "missing" (open
    journal trades with no position) or "mismatch" (both exist but the sizes differ). An issue whose
    `untracked_size` isn't 0 can be fixed by adding that much to the journal (POST .../adopt).
    """
    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="No Hyperliquid account connected. Connect one in Settings.")
    with fill_sync.lock:
        try:
            fill_sync.sync(hl_client)
        except Exception as e:
            logger.warning(f"Could not sync fills before reconciling: {e}")
        positions = _fetch_positions_or_502()
        journal = _journal_positions()

    exchange: Dict[str, Tuple[str, float]] = {}
    for position in positions:
        if position.get("coin") and position.get("size"):
            exchange[str(position["coin"]).upper()] = (str(position["coin"]), float(position["size"]))

    issues = []
    for key in sorted(set(exchange) | set(journal)):
        coin, exchange_size = exchange.get(key, (key, 0.0))
        journal_size = journal.get(key, {}).get("size", 0.0)
        trade_ids = journal.get(key, {}).get("trade_ids", [])
        if _same_size(exchange_size, journal_size):
            continue
        if not trade_ids:
            kind = "untracked"
            message = f"Hyperliquid has a {_describe(coin, exchange_size)} position that isn't in the journal."
        elif exchange_size == 0:
            kind = "missing"
            message = (f"The journal has {len(trade_ids)} open {coin} trade{'s' if len(trade_ids) > 1 else ''}, but "
                       f"Hyperliquid has no {coin} position. If it was closed there, close the trade here with "
                       "\"Close this trade's size on Hyperliquid\" unchecked.")
        else:
            kind = "mismatch"
            message = (f"Hyperliquid's {coin} position is a {_describe(coin, exchange_size)}, but the journal's open "
                       f"{coin} trades add up to a {_describe(coin, journal_size)}.")
        issues.append({
            "coin": coin,
            "kind": kind,
            "exchange_size": exchange_size,
            "journal_size": journal_size,
            "trade_ids": trade_ids,
            "untracked_size": _untracked_size(exchange_size, journal_size),
            "message": message,
        })
    return {"in_sync": not issues, "issues": issues}


@router.post("/reconcile/{coin}/adopt")
def adopt_position(coin: str):
    """
    Add the part of the `coin` position that no open journal trade accounts for to the live journal,
    as a new open trade at the position's entry price, so its fills are tracked from now on.
    """
    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="No Hyperliquid account connected. Connect one in Settings.")
    with fill_sync.lock:
        position = _find_position(_fetch_positions_or_502(), coin)
        if not position:
            raise HTTPException(status_code=400, detail=f"Hyperliquid has no {coin.upper()} position")
        actual_coin = str(position["coin"])
        exchange_size = float(position["size"])
        journal_size = _journal_positions().get(actual_coin.upper(), {}).get("size", 0.0)
        untracked = _untracked_size(exchange_size, journal_size)
        if not untracked:
            raise HTTPException(status_code=400, detail=f"The journal already accounts for the whole {actual_coin} position")

        entry = float(position.get("entry_price") or 0)
        if entry <= 0:
            raise HTTPException(status_code=502, detail=f"Hyperliquid didn't report an entry price for {actual_coin}")
        leverage = int(position.get("leverage") or 1)
        notional = abs(untracked) * entry
        trade_index = record_trade(TradeData(
            asset=f"{actual_coin}-USDC",
            direction="long" if untracked > 0 else "short",
            entry_price=entry,
            stop_loss=0.0,
            position_size=notional,
            take_profits=[],
            stop_losses=[],
            thesis="Added from Hyperliquid: a position the journal didn't have",
            margin=notional / leverage,
            leverage=leverage,
        ), "live")
    logger.info(f"Adopted {untracked} {actual_coin} from Hyperliquid as live trade {trade_index}")
    return {"trade_index": trade_index, "coin": actual_coin, "size": untracked, "entry_price": entry}


class ClosePositionRequest(BaseModel):
    # Coin units to close (one journal trade's share); omit to close the whole position.
    # More than the position holds closes all of it.
    size: Optional[float] = Field(default=None, gt=0)
    # The live journal trade being closed: its close fills are credited to it and its journal
    # entry is updated from them
    trade_index: Optional[int] = None

@router.get("/fees")
def get_fee_rates():
    """Fee rates and the stop slippage TradeLab plans with: the connected account's, else Hyperliquid's base tier."""
    return fees.current_rates(hl_client)


@router.post("/sync")
def sync_fills():
    """Apply new Hyperliquid fills to the open live journal trades now (also runs in the background)."""
    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="No Hyperliquid account connected. Connect one in Settings.")
    try:
        return fill_sync.sync(hl_client)
    except Exception as e:
        logger.exception("Fill sync failed")
        raise HTTPException(status_code=502, detail=f"Couldn't fetch fills from Hyperliquid: {e}") from e


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
        raise HTTPException(status_code=503, detail="No Hyperliquid account connected. Connect one in Settings.")

    if not hl_client.exchange_client:
        raise HTTPException(status_code=400, detail="Trading isn't enabled for this account. Enable it in Settings.")

    journal_trade = None
    if request.trade_index is not None:
        trades = load_trades("live")
        if request.trade_index not in trades.index or trades.loc[request.trade_index, "Status"] != "Open":
            raise HTTPException(status_code=400, detail=f"Trade {request.trade_index} isn't an open live trade")
        journal_trade = request.trade_index

    # For a journal trade, nothing else may sync until this close's fills are claimed for it
    with fill_sync.lock if journal_trade is not None else nullcontext():
        return _close_position(coin, request, journal_trade)


def _all_oids(result: Any) -> List[int]:
    try:
        statuses = result["response"]["data"]["statuses"]
    except (KeyError, TypeError):
        return []
    return [oid for s in statuses if isinstance(s, dict) for oid in [(s.get("filled") or s.get("resting") or {}).get("oid")] if oid]


def _close_position(coin: str, request: ClosePositionRequest, journal_trade: Optional[int]):
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
        close_oids = _all_oids(result)

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
                    close_oids += _all_oids(alt_result)
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

        journal = None
        if journal_trade is not None:
            fill_sync.claim_orders(journal_trade, [(oid, "close", None) for oid in close_oids])
            try:
                fill_sync.sync(hl_client)
            except Exception:
                logger.exception("Could not sync fills after closing; the background sync will retry")
            row = load_trades("live").loc[journal_trade]
            def number(value):
                return float(value) if value is not None and value == value else None  # NaN -> None
            journal = {"trade_index": journal_trade, "status": str(row["Status"]),
                       "exit_price": number(row["Exit_Price"]), "pnl": number(row["P&L"])}

        return {
            "status": "success",
            "coin": actual_coin,
            "closed_size": float(filled.get("totalSz") or 0) or (close_size or position_size),
            "fill_price": fill_price,
            # The journal trade after its close fills were applied; status stays "Open" if they
            # haven't been reported yet (the background sync applies them shortly)
            "journal": journal,
            "result": result,
            "message": f"Position closed for {actual_coin} at ${fill_price:.2f}" if fill_price
                       else f"Position closed for {actual_coin} (fill price unavailable)",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error closing position: {e}")
        raise HTTPException(status_code=500, detail=f"Error closing position: {str(e)}") from e
