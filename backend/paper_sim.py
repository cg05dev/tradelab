"""
Paper trades that behave like live ones, against real mainnet prices.

A paper trade is journaled at the market price, like a live one. `step()` then watches the price
for every open paper trade and fills its exits the way Hyperliquid would:

- a take profit (a resting limit order) fills at its price, paying the maker fee;
- the stop (a stop-market order) fills past its price by the planned slippage, or at the price the
  market had already reached if it gapped through; it pays the taker fee;
- with no stop, the trade is liquidated at its liquidation price (risk.py), using the asset's own
  maintenance margin.

Entering paid the taker fee (`charge_entry`). Every fill moves the paper balance, so paper P&L is
what the same trade would have made live, fees included.

Prices: mid prices every step, and once a minute the 1-minute candles since the last check, so a
wick between steps (or while TradeLab was off) still fills. When one candle reaches both the stop
and a target, the stop is assumed to have come first.
"""

import json
import logging
import threading
import time
from typing import Dict, List, Optional

import requests

import fees
import storage
from fill_sync import _levels, _opened_ms, coin_of
from risk import DEFAULT_MAX_LEVERAGE, liquidation_price

logger = logging.getLogger(__name__)

MAINNET_INFO = "https://api.hyperliquid.xyz/info"
CANDLE_CHECK_MS = 60_000
META_REFRESH_SECONDS = 3600
CLOSED_FRACTION = 1e-4

_lock = threading.Lock()


class MainnetMarket:
    """Public mainnet prices. Paper trading always simulates mainnet, whatever account is connected."""

    def __init__(self):
        self._max_leverage: Dict[str, float] = {}
        self._max_leverage_at = 0.0

    def max_leverage(self, coin: str) -> Optional[float]:
        """The asset's maximum leverage, which sets its maintenance margin. Refreshed hourly."""
        if time.time() - self._max_leverage_at > META_REFRESH_SECONDS:
            try:
                response = requests.post(MAINNET_INFO, json={"type": "meta"}, timeout=10)
                response.raise_for_status()
                self._max_leverage = {
                    asset["name"].upper(): float(asset["maxLeverage"])
                    for asset in response.json().get("universe", []) if asset.get("maxLeverage")
                }
                self._max_leverage_at = time.time()
            except Exception as e:
                logger.warning(f"Could not fetch mainnet max leverage, assuming {DEFAULT_MAX_LEVERAGE}x: {e}")
        return self._max_leverage.get(coin.upper())

    def mids(self) -> Dict[str, float]:
        response = requests.post(MAINNET_INFO, json={"type": "allMids"}, timeout=10)
        response.raise_for_status()
        return {coin.upper(): float(price) for coin, price in response.json().items()}

    def candles(self, coin: str, start_ms: int, end_ms: int) -> List[Dict]:
        response = requests.post(MAINNET_INFO, json={
            "type": "candleSnapshot", "req": {"coin": coin, "interval": "1m", "startTime": start_ms, "endTime": end_ms},
        }, timeout=10)
        response.raise_for_status()
        return [{"t": c["t"], "o": float(c["o"]), "h": float(c["h"]), "l": float(c["l"])} for c in response.json()]


def charge_entry(trade_id: int, notional: float, rates: Optional[Dict] = None):
    """Start simulating a new paper trade: charge its entry taker fee to the trade and the balance."""
    rates = rates or fees.default_rates()
    fee = notional * rates["taker"]
    with storage._connect() as conn:
        row = conn.execute("SELECT entry, position_size, date FROM trades WHERE id = ? AND mode = 'paper'", (trade_id,)).fetchone()
        if not row or not row[0]:
            return
        entry, size, date = row
        conn.execute(
            "INSERT OR IGNORE INTO paper_sim (trade_id, units_total, checked_ms) VALUES (?, ?, ?)",
            (trade_id, size / entry, _opened_ms(date)),
        )
        conn.execute("UPDATE trades SET pnl = COALESCE(pnl, 0) - ? WHERE id = ?", (fee, trade_id))
        _add_to_balance(conn, -fee)


def _add_to_balance(conn, delta: float):
    if delta:
        conn.execute(
            "INSERT INTO portfolio (mode, size) VALUES ('paper', ?) ON CONFLICT (mode) DO UPDATE SET size = size + excluded.size",
            (delta,),
        )


def step(market=None, rates: Optional[Dict] = None, now_ms: Optional[int] = None) -> Dict:
    """Fill whatever exits the market has reached for the open paper trades. Returns {"closed", "updated"}."""
    market = market or MainnetMarket()
    rates = rates or fees.default_rates()
    now_ms = now_ms or int(time.time() * 1000)
    with _lock:
        trades = _open_paper_trades(now_ms)
        if not trades:
            return {"closed": [], "updated": []}
        mids = market.mids()
        updated, closed = set(), []
        for trade in trades:
            coin = trade["coin"]
            trade["max_leverage"] = market.max_leverage(coin)
            # Candles first (older prices), then the current mid
            observations: List[Dict] = []
            if now_ms - trade["checked_ms"] >= CANDLE_CHECK_MS:
                start = max(trade["checked_ms"] - CANDLE_CHECK_MS, trade["opened_ms"])
                for candle in market.candles(coin, start, now_ms):
                    # The candle the trade opened in includes prices from before it existed
                    if candle["t"] >= trade["opened_ms"]:
                        observations.append({"open": candle["o"], "high": candle["h"], "low": candle["l"]})
                trade["checked_ms"] = now_ms
                trade["state_changed"] = True
            if coin in mids:
                price = mids[coin]
                observations.append({"open": price, "high": price, "low": price})
            for observation in observations:
                if trade["status"] != "Open":
                    break
                if _apply(trade, observation, rates):
                    updated.add(trade["id"])
            if trade["status"] == "Closed":
                closed.append(trade["id"])
        _save(trades)
        return {"closed": closed, "updated": sorted(updated)}


def _open_paper_trades(now_ms: int) -> List[Dict]:
    df = storage.load_trades("paper")
    if df.empty or "Status" not in df.columns:
        return []
    open_rows = df[df["Status"] == "Open"]
    if open_rows.empty:
        return []
    with storage._connect() as conn:
        state = {
            row[0]: row[1:]
            for row in conn.execute("SELECT trade_id, units_total, exit_units, exit_value, checked_ms FROM paper_sim")
        }
    trades = []
    for trade_id, row in open_rows.iterrows():
        entry = float(row.get("Entry") or 0)
        if entry <= 0:
            continue
        units_total, exit_units, exit_value, checked_ms = state.get(
            # Trades from before simulation existed start being watched now, not from their open date
            trade_id, (float(row.get("Position_Size") or 0) / entry, 0.0, 0.0, now_ms)
        )
        try:
            hit_tps = json.loads(row.get("Hit_TPs") or "[]")
        except (TypeError, ValueError):
            hit_tps = []
        trades.append({
            "id": int(trade_id), "coin": coin_of(row.get("Asset")), "direction": str(row.get("Direction") or "").lower(),
            "entry": entry, "sl": float(row.get("SL") or 0), "tps": _levels(row.get("TPs")),
            "leverage": float(row.get("Leverage") or 1) or 1, "opened_ms": _opened_ms(row.get("Date")),
            "units_total": units_total, "exit_units": exit_units, "exit_value": exit_value, "checked_ms": checked_ms,
            "pnl": float(row.get("P&L") or 0), "hit_tps": hit_tps, "status": "Open",
            "fields": {}, "balance_delta": 0.0, "state_changed": trade_id not in state, "now_ms": now_ms,
        })
    return [t for t in trades if t["coin"] and t["direction"] in ("long", "short")]


def _apply(trade: Dict, price: Dict, rates: Dict) -> bool:
    """Fill the exits one price observation (open/high/low) reaches. Adverse exits are checked first."""
    long = trade["direction"] == "long"
    if long:
        adverse_reached = lambda level: price["low"] <= level  # noqa: E731
        target_reached = lambda level: price["high"] >= level  # noqa: E731
        beyond = lambda a, b: a <= b  # noqa: E731  (a is at or past b, in the losing direction)
    else:
        adverse_reached = lambda level: price["high"] >= level  # noqa: E731
        target_reached = lambda level: price["low"] <= level  # noqa: E731
        beyond = lambda a, b: a >= b  # noqa: E731

    stop = trade["sl"]
    liquidation = liquidation_price(trade["entry"], trade["leverage"], trade["direction"], trade.get("max_leverage"))
    if stop > 0 and not beyond(stop, liquidation):
        if adverse_reached(stop):
            slipped = stop * (1 - rates["stop_slippage"]) if long else stop * (1 + rates["stop_slippage"])
            # A gap through the stop fills at the market, not at the stop
            fill = price["open"] if beyond(price["open"], slipped) else slipped
            _fill(trade, fill, _remaining(trade), rates["taker"], "stop")
            return True
    elif adverse_reached(liquidation):  # no stop, or one past liquidation that never gets the chance
        _fill(trade, liquidation, _remaining(trade), rates["taker"], "liquidation")
        return True

    filled = False
    for index, tp in enumerate(trade["tps"]):
        target = float(tp["price"])
        if index in trade["hit_tps"] or trade["status"] != "Open":
            continue
        # A target on the losing side of the entry never fills as a take profit
        if beyond(target, trade["entry"]) or not target_reached(target):
            continue
        units = min(trade["units_total"] * float(tp["allocation"]), _remaining(trade))
        if units > 0:
            trade["hit_tps"].append(index)
            _fill(trade, target, units, rates["maker"], "take_profit")
            filled = True
    return filled


def _remaining(trade: Dict) -> float:
    return max(trade["units_total"] - trade["exit_units"], 0.0)


def _fill(trade: Dict, price: float, units: float, fee_rate: float, kind: str):
    sign = 1 if trade["direction"] == "long" else -1
    pnl = sign * (price - trade["entry"]) * units - fee_rate * price * units
    trade["pnl"] += pnl
    trade["balance_delta"] += pnl
    trade["exit_units"] += units
    trade["exit_value"] += price * units
    trade["state_changed"] = True
    fields = trade["fields"]
    fields["P&L"] = trade["pnl"]
    fields["Position_Size"] = _remaining(trade) * trade["entry"]
    if kind == "take_profit":
        fields.update({"TP_Hit": True, "TP_Price": price, "Hit_TPs": json.dumps(sorted(trade["hit_tps"]))})
    elif kind == "stop":
        fields.update({"SL_Hit": True, "SL_Price": price})
    logger.info(f"Paper trade {trade['id']} {trade['coin']}: {kind} filled {units:g} @ {price:g}, P&L {pnl:+.4f}")
    if _remaining(trade) <= trade["units_total"] * CLOSED_FRACTION:
        trade["status"] = "Closed"
        hold_hours = (trade["now_ms"] - trade["opened_ms"]) / 3_600_000
        fields.update({
            "Status": "Closed",
            "Exit_Price": trade["exit_value"] / trade["exit_units"],
            "Hold_Time": f"{max(hold_hours, 0):.1f}h",
            "Closed_At": storage.local_time(trade["now_ms"]),
            "Position_Size": trade["units_total"] * trade["entry"],
        })


def _save(trades: List[Dict]):
    with storage._connect() as conn:
        for trade in trades:
            if trade["state_changed"]:
                conn.execute(
                    "INSERT INTO paper_sim (trade_id, units_total, exit_units, exit_value, checked_ms) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT (trade_id) DO UPDATE SET exit_units = excluded.exit_units, "
                    "exit_value = excluded.exit_value, checked_ms = excluded.checked_ms",
                    (trade["id"], trade["units_total"], trade["exit_units"], trade["exit_value"], trade["checked_ms"]),
                )
            if trade["fields"]:
                fields = trade["fields"]
                assignments = ", ".join(f"{storage.SQL_COLUMNS[col]} = ?" for col in fields)
                updated = conn.execute(
                    # Unless it was closed by hand in the meantime
                    f"UPDATE trades SET {assignments} WHERE id = ? AND mode = 'paper' AND status = 'Open'",
                    [storage._to_db(col, value) for col, value in fields.items()] + [trade["id"]],
                ).rowcount
                if updated:
                    _add_to_balance(conn, trade["balance_delta"])
