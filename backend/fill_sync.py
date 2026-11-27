"""
Keep the live journal in step with what actually happened on Hyperliquid.

Take-profit and stop orders fill on the exchange, often while TradeLab isn't open. `sync()` reads
the account's fills and applies them to the open live journal trades they belong to: a trade's
P&L, remaining size, TP/SL hits and, once nothing is left, its exit price and close.

Which fills belong to which trade:
- Orders TradeLab placed for a trade (entry, TPs, stops, closes) are recorded in `exchange_orders`,
  so their fills are credited to that trade exactly.
- Fills of other orders (a trade journaled before this existed, or a position closed on
  Hyperliquid's site) are matched by coin, direction and time. An entry is the opening fill closest
  to the time the trade was journaled. Closes go to the oldest open trade first (Hyperliquid nets
  all trades in a coin into one position).

Every applied fill is recorded in `exchange_fills`, so running sync again changes nothing. A
trade's journal fields are always recomputed from its recorded fills.

P&L is what the account actually made: price moves on the closed size, minus the exit fees and
the matching share of the entry fee.
"""

import json
import logging
import threading
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

import storage

logger = logging.getLogger(__name__)

# Held while syncing, and by a close for a journal trade from placing the order until its fills
# are claimed, so a sync in between can't credit them to a different trade
lock = threading.RLock()

# An unrecorded entry fill must be this close to the time the trade was journaled
ENTRY_MATCH_BEFORE_MS = 5 * 60 * 1000
ENTRY_MATCH_AFTER_MS = 60 * 1000
# A fill this close to a planned TP/SL price counts as hitting it (stops fill with slippage)
LEVEL_TOLERANCE = 0.005
# Less than this fraction of a trade left open counts as fully closed
CLOSED_FRACTION = 1e-4


def coin_of(asset: Optional[str]) -> str:
    """"BTC-USDC" -> "BTC"."""
    return (asset or "").split("-")[0].strip().upper()


def claim_orders(trade_id: int, orders: Iterable[Tuple[Optional[int], str, Optional[int]]]):
    """Record Hyperliquid orders placed for a live trade: (oid, role, level) with role one of
    'entry', 'take_profit', 'stop_loss', 'close'. Orders without an oid are skipped."""
    rows = [(int(oid), trade_id, role, level) for oid, role, level in orders if oid]
    if not rows:
        return
    with storage._connect() as conn:
        conn.executemany("INSERT OR IGNORE INTO exchange_orders (oid, trade_id, role, level) VALUES (?, ?, ?, ?)", rows)


def sync(client) -> Dict:
    """
    Apply new Hyperliquid fills to the open live trades. Returns {"synced", "updated", "closed"}
    (trade ids). Does nothing without a connected account or open live trades. Raises if the fills
    can't be fetched.
    """
    if not client or not client.enabled:
        return {"synced": False, "updated": [], "closed": []}
    with lock:
        trades = _open_live_trades()
        if not trades:
            return {"synced": True, "updated": [], "closed": []}
        since = min(t["opened_ms"] for t in trades) - ENTRY_MATCH_BEFORE_MS
        fills = client.get_user_fills(since)
        return apply_fills(trades, fills)


def _opened_ms(date: Optional[str]) -> int:
    """The journal's local timestamp, as epoch milliseconds."""
    try:
        return int(datetime.strptime(str(date), "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
    except ValueError:
        parsed = pd.to_datetime(date, errors="coerce")
        return int(parsed.timestamp() * 1000) if pd.notna(parsed) else 0


def _levels(raw) -> List[Dict]:
    try:
        levels = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        return []
    return [lvl for lvl in levels if isinstance(lvl, dict) and float(lvl.get("price") or 0) > 0]


def _open_live_trades() -> List[Dict]:
    df = storage.load_trades("live")
    if df.empty or "Status" not in df.columns:
        return []
    trades = []
    for trade_id, row in df[df["Status"] == "Open"].iterrows():
        entry = float(row.get("Entry") or 0)
        trades.append({
            "id": int(trade_id),
            "coin": coin_of(row.get("Asset")),
            "direction": str(row.get("Direction") or "").lower(),
            "entry": entry,
            # Before its entry fill is found, the journal's size (USD notional at entry) gives the units
            "journal_units": float(row.get("Position_Size") or 0) / entry if entry > 0 else 0.0,
            "opened_ms": _opened_ms(row.get("Date")),
            "sl": float(row.get("SL") or 0),
            "tps": _levels(row.get("TPs")),
            "date": row.get("Date"),
        })
    return [t for t in trades if t["coin"] and t["direction"] in ("long", "short")]


def _fee_usd(fill: Dict) -> float:
    # Fees are almost always charged in USDC; any other token isn't converted
    return float(fill.get("fee") or 0) if (fill.get("feeToken") or "USDC") == "USDC" else 0.0


def apply_fills(trades: List[Dict], fills: List[Dict]) -> Dict:
    """Credit `fills` (Hyperliquid userFills entries) to `trades` (from _open_live_trades)."""
    fills = sorted(fills, key=lambda f: (f["time"], f["tid"]))
    ids = [t["id"] for t in trades]
    marks = ",".join("?" * len(ids))
    tids = [f["tid"] for f in fills]

    with storage._connect() as conn:
        claims = {
            oid: (trade_id, role, level)
            for oid, trade_id, role, level in conn.execute("SELECT oid, trade_id, role, level FROM exchange_orders")
        }
        recorded = {trade_id: [] for trade_id in ids}
        for row in conn.execute(
            f"SELECT trade_id, kind, oid, size, price, fee, time_ms FROM exchange_fills WHERE trade_id IN ({marks})", ids
        ):
            recorded[row[0]].append({"kind": row[1], "oid": row[2], "size": row[3], "price": row[4], "fee": row[5], "time": row[6]})
        # How much of each fill is already credited to any trade
        used: Dict[int, float] = {}
        for chunk_start in range(0, len(tids), 500):
            chunk = tids[chunk_start:chunk_start + 500]
            for tid, size in conn.execute(
                f"SELECT tid, SUM(size) FROM exchange_fills WHERE tid IN ({','.join('?' * len(chunk))}) GROUP BY tid", chunk
            ):
                used[tid] = size

        new_rows: List[Tuple] = []
        touched = set()

        def left(fill):
            return float(fill["sz"]) - used.get(fill["tid"], 0.0)

        def credit(trade, fill, kind, size):
            if kind == "close" and not opened(trade):
                # No entry fill found: pin the journal's size and entry as the opening, so later
                # syncs measure what's left against the same starting size
                synthetic = {"kind": "open", "oid": None, "size": trade["journal_units"], "price": trade["entry"],
                             "fee": 0.0, "time": trade["opened_ms"]}
                recorded[trade["id"]].append(synthetic)
                new_rows.append((-trade["id"], trade["id"], "open", None, synthetic["size"], synthetic["price"], 0.0, synthetic["time"]))
            fee = _fee_usd(fill) * size / float(fill["sz"])
            row = {"kind": kind, "oid": fill["oid"], "size": size, "price": float(fill["px"]), "fee": fee, "time": fill["time"]}
            recorded[trade["id"]].append(row)
            used[fill["tid"]] = used.get(fill["tid"], 0.0) + size
            new_rows.append((fill["tid"], trade["id"], kind, fill["oid"], size, row["price"], fee, fill["time"]))
            touched.add(trade["id"])

        def opened(trade):
            return [r for r in recorded[trade["id"]] if r["kind"] == "open"]

        def units(trade):
            opens = opened(trade)
            return sum(r["size"] for r in opens) if opens else trade["journal_units"]

        def remaining(trade):
            return units(trade) - sum(r["size"] for r in recorded[trade["id"]] if r["kind"] == "close")

        def open_time(trade):
            opens = opened(trade)
            return min(r["time"] for r in opens) if opens else trade["opened_ms"]

        # 1. Entry fills, for trades that don't have theirs yet
        for trade in trades:
            if opened(trade):
                continue
            open_dir = f"Open {trade['direction'].capitalize()}"
            candidates = [f for f in fills if f["coin"].upper() == trade["coin"] and f["dir"] == open_dir and left(f) > 0]
            entry_oids = {oid for oid, (tid_, role, _) in claims.items() if tid_ == trade["id"] and role == "entry"}
            if entry_oids:
                chosen = [f for f in candidates if f["oid"] in entry_oids]
            else:
                window = [
                    f for f in candidates
                    if f["oid"] not in claims
                    and trade["opened_ms"] - ENTRY_MATCH_BEFORE_MS <= f["time"] <= trade["opened_ms"] + ENTRY_MATCH_AFTER_MS
                ]
                closest = min(window, key=lambda f: abs(f["time"] - trade["opened_ms"]), default=None)
                chosen = [f for f in window if closest and f["oid"] == closest["oid"]]
            for fill in chosen:
                credit(trade, fill, "open", left(fill))

        # 2. Closing fills: to the trade whose order it was, otherwise to the oldest open trade
        for fill in fills:
            direction = {"Close Long": "long", "Close Short": "short"}.get(fill["dir"])
            if not direction:
                if fill["dir"] in ("Long > Short", "Short > Long"):
                    logger.warning(f"Fill {fill['tid']} flipped the {fill['coin']} position; apply it to the journal by hand")
                continue
            claimed = claims.get(fill["oid"])
            eligible = [
                t for t in trades
                if t["coin"] == fill["coin"].upper() and t["direction"] == direction and fill["time"] >= open_time(t)
                # An order TradeLab placed for one trade is only ever credited to that trade
                and (claimed is None or t["id"] == claimed[0])
            ]
            eligible.sort(key=lambda t: t["id"])
            for trade in eligible:
                size = min(left(fill), remaining(trade))
                if size <= float(fill["sz"]) * 1e-9 or remaining(trade) <= units(trade) * CLOSED_FRACTION:
                    continue
                credit(trade, fill, "close", size)

        conn.executemany(
            "INSERT INTO exchange_fills (tid, trade_id, kind, oid, size, price, fee, time_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            new_rows,
        )

        closed = []
        for trade in trades:
            if trade["id"] not in touched:
                continue
            fields = _journal_fields(trade, recorded[trade["id"]], claims)
            if fields.get("Status") == "Closed":
                closed.append(trade["id"])
            assignments = ", ".join(f"{storage.SQL_COLUMNS[col]} = ?" for col in fields)
            conn.execute(
                f"UPDATE trades SET {assignments} WHERE id = ? AND mode = 'live'",
                [storage._to_db(col, value) for col, value in fields.items()] + [trade["id"]],
            )
            logger.info(f"Synced live trade {trade['id']} ({trade['coin']}) from Hyperliquid fills: {fields}")

    return {"synced": True, "updated": sorted(touched), "closed": closed}


def _hit(trade: Dict, row: Dict, claims: Dict) -> Tuple[Optional[str], Optional[int]]:
    """Whether a closing fill was a TP or SL hit, and which level."""
    claim = claims.get(row["oid"])
    if claim and claim[0] == trade["id"] and claim[1] in ("take_profit", "stop_loss"):
        return claim[1], claim[2]
    if claim and claim[0] == trade["id"]:
        return None, None  # a close the user asked for
    long = trade["direction"] == "long"
    price = row["price"]
    if trade["sl"] > 0 and (price <= trade["sl"] * (1 + LEVEL_TOLERANCE) if long else price >= trade["sl"] * (1 - LEVEL_TOLERANCE)):
        return "stop_loss", 0
    reached = [
        i for i, tp in enumerate(trade["tps"])
        if (price >= float(tp["price"]) * (1 - LEVEL_TOLERANCE) if long else price <= float(tp["price"]) * (1 + LEVEL_TOLERANCE))
    ]
    if reached:
        return "take_profit", max(reached, key=lambda i: float(trade["tps"][i]["price"]) * (1 if long else -1))
    return None, None


def _journal_fields(trade: Dict, rows: List[Dict], claims: Dict) -> Dict:
    opens = [r for r in rows if r["kind"] == "open"]
    closes = [r for r in rows if r["kind"] == "close"]
    if opens:
        total_units = sum(r["size"] for r in opens)
        entry = sum(r["price"] * r["size"] for r in opens) / total_units
        entry_fee = sum(r["fee"] for r in opens)
        start_ms = min(r["time"] for r in opens)
    else:
        total_units, entry, entry_fee, start_ms = trade["journal_units"], trade["entry"], 0.0, trade["opened_ms"]
    closed_units = sum(r["size"] for r in closes)
    sign = 1 if trade["direction"] == "long" else -1
    price_pnl = sum(sign * (r["price"] - entry) * r["size"] for r in closes)
    fees = sum(r["fee"] for r in closes) + (entry_fee * min(closed_units / total_units, 1) if total_units else 0)
    left = max(total_units - closed_units, 0.0)

    fields = {"P&L": price_pnl - fees, "Position_Size": left * entry}
    hit_tps, tp_price, sl_price = [], None, None
    for row in closes:
        kind, level = _hit(trade, row, claims)
        if kind == "take_profit":
            if level not in hit_tps:
                hit_tps.append(level)
            tp_price = row["price"]
        elif kind == "stop_loss":
            sl_price = row["price"]
    if hit_tps:
        fields.update({"TP_Hit": True, "TP_Price": tp_price, "Hit_TPs": json.dumps(sorted(hit_tps))})
    if sl_price is not None:
        fields.update({"SL_Hit": True, "SL_Price": sl_price})

    if total_units and left <= total_units * CLOSED_FRACTION:
        end_ms = max(r["time"] for r in closes)
        fields.update({
            "Status": "Closed",
            "Exit_Price": sum(r["price"] * r["size"] for r in closes) / closed_units,
            "Hold_Time": f"{(end_ms - start_ms) / 3_600_000:.1f}h",
            "Closed_At": storage.local_time(end_ms),
            "Position_Size": total_units * entry,  # a closed trade keeps its full size, as manual closes do
        })
    return fields
