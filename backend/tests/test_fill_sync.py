"""Applying Hyperliquid fills to the live journal (fill_sync.py)."""

import sqlite3
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

import fill_sync
import hyperliquid_client
import storage
from routers import hyperliquid
from test_hyperliquid_orders import RESTING, _filled, _order

JOURNALED_AT = "2026-11-26 17:17:33"
T0 = int(datetime.strptime(JOURNALED_AT, "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
MINUTE = 60_000


def fill(tid, oid, direction, size, price, at, fee=0.0, coin="BTC"):
    return {"tid": tid, "oid": oid, "dir": direction, "sz": str(size), "px": str(price), "time": at,
            "fee": str(fee), "feeToken": "USDC", "coin": coin, "closedPnl": "0", "side": "B"}


def journal(direction="long", entry=60_591.0, units=0.00246, sl=60_550.0, tps=((61_000, 1.0),), date=JOURNALED_AT, mode="live", asset="BTC-USDC"):
    import json
    return storage.insert_trade({
        "Date": date, "Asset": asset, "Direction": direction, "Entry": entry, "SL": sl,
        "TPs": json.dumps([{"price": p, "allocation": a} for p, a in tps]),
        "SLs": json.dumps([{"price": sl, "allocation": 1.0}]), "Position_Size": units * entry,
        "Status": "Open", "P&L": 0.0, "TP_Hit": False, "SL_Hit": False, "Hit_TPs": "[]", "Leverage": 40,
    }, mode)


def trade(trade_id, mode="live"):
    return storage.load_trades(mode).loc[trade_id]


@pytest.fixture
def exchange():
    """A connected account whose fills are `exchange.fills`."""
    client = Mock(enabled=True)
    client.fills = []
    client.get_user_fills.side_effect = lambda since: [f for f in client.fills if f["time"] >= since]
    return client


def recorded_fills():
    with sqlite3.connect(storage.DB_FILE) as conn:
        return conn.execute("SELECT tid, trade_id, kind, size FROM exchange_fills ORDER BY trade_id, tid").fetchall()


class TestStopLossOnTheExchange:
    """The real trade this was built for: a 40x BTC long journaled before fill sync existed,
    stopped out on Hyperliquid while TradeLab wasn't watching."""

    def test_closes_the_trade_with_what_the_account_actually_lost(self, exchange):
        trade_id = journal()
        exchange.fills = [
            fill(1, 100, "Open Long", 0.00246, 60_591, T0 - 2_000, fee=0.064391),
            fill(2, 200, "Close Long", 0.00246, 60_532, T0 + 5 * MINUTE, fee=0.064328),
        ]

        result = fill_sync.sync(exchange)

        t = trade(trade_id)
        assert result["closed"] == [trade_id]
        assert t["Status"] == "Closed"
        assert t["Exit_Price"] == 60_532
        # price move -0.14514, both fees: the account went from 4.98 to 4.706141
        assert t["P&L"] == pytest.approx(-0.273859)
        assert t["SL_Hit"] and t["SL_Price"] == 60_532
        assert not t["TP_Hit"]
        assert t["Position_Size"] == pytest.approx(0.00246 * 60_591)
        assert t["Hold_Time"] == "0.1h"

    def test_running_again_changes_nothing(self, exchange):
        trade_id = journal()
        exchange.fills = [
            fill(1, 100, "Open Long", 0.00246, 60_591, T0 - 2_000, fee=0.064391),
            fill(2, 200, "Close Long", 0.00246, 60_532, T0 + 5 * MINUTE, fee=0.064328),
        ]
        fill_sync.sync(exchange)
        before = (trade(trade_id).to_dict(), recorded_fills())

        assert fill_sync.sync(exchange) == {"synced": True, "updated": [], "closed": []}
        assert (trade(trade_id).to_dict(), recorded_fills()) == before

    def test_without_its_entry_fill_uses_the_journal_entry(self, exchange):
        trade_id = journal()
        exchange.fills = [fill(2, 200, "Close Long", 0.00246, 60_532, T0 + MINUTE, fee=0.064328)]

        fill_sync.sync(exchange)

        assert trade(trade_id)["Status"] == "Closed"
        assert trade(trade_id)["P&L"] == pytest.approx((60_532 - 60_591) * 0.00246 - 0.064328)


class TestOrdersPlacedByTradeLab:
    def test_take_profit_then_stop(self, exchange):
        trade_id = journal(units=0.02, entry=100_000, sl=95_000, tps=((110_000, 0.5), (120_000, 0.5)))
        fill_sync.claim_orders(trade_id, [(10, "entry", None), (11, "take_profit", 0), (12, "take_profit", 1), (13, "stop_loss", 0)])
        exchange.fills = [fill(1, 10, "Open Long", 0.02, 100_000, T0 - 1_000, fee=0.9)]

        exchange.fills.append(fill(2, 11, "Close Long", 0.01, 110_000, T0 + MINUTE, fee=0.5))
        fill_sync.sync(exchange)

        t = trade(trade_id)
        assert t["Status"] == "Open"
        assert t["TP_Hit"] and t["Hit_TPs"] == "[0]" and t["TP_Price"] == 110_000
        assert t["Position_Size"] == pytest.approx(0.01 * 100_000)
        assert t["P&L"] == pytest.approx(100 - 0.5 - 0.45)  # half the entry fee

        exchange.fills.append(fill(3, 13, "Close Long", 0.01, 94_900, T0 + 2 * MINUTE, fee=0.5))
        fill_sync.sync(exchange)

        t = trade(trade_id)
        assert t["Status"] == "Closed"
        assert t["SL_Hit"] and t["SL_Price"] == 94_900
        assert t["Exit_Price"] == pytest.approx(102_450)  # size-weighted
        assert t["P&L"] == pytest.approx(100 - 51 - 0.9 - 1.0)
        assert t["Position_Size"] == pytest.approx(2_000)

    def test_a_close_from_tradelab_goes_to_its_trade_not_the_oldest(self, exchange):
        older = journal(units=0.01, entry=100_000)
        newer = journal(units=0.01, entry=101_000, date="2026-11-26 17:20:00")
        fill_sync.claim_orders(newer, [(50, "close", None)])
        exchange.fills = [fill(9, 50, "Close Long", 0.01, 102_000, T0 + 10 * MINUTE)]

        fill_sync.sync(exchange)

        assert trade(newer)["Status"] == "Closed"
        assert trade(newer)["P&L"] == pytest.approx(10)
        assert trade(older)["Status"] == "Open"

    def test_an_order_of_another_trade_is_never_credited_to_an_open_one(self, exchange):
        gone = journal()
        storage.update_trade(gone, {"Status": "Closed"}, "live")
        fill_sync.claim_orders(gone, [(13, "stop_loss", 0)])
        still_open = journal()
        exchange.fills = [fill(3, 13, "Close Long", 0.00246, 60_532, T0 + MINUTE)]

        fill_sync.sync(exchange)

        assert trade(still_open)["Status"] == "Open"


class TestMatchingWithoutOrderIds:
    def test_closes_go_to_the_oldest_trade_first_and_can_be_split(self, exchange):
        first = journal(units=0.01, entry=100_000)
        second = journal(units=0.01, entry=100_000, date="2026-11-26 17:18:00")
        exchange.fills = [fill(9, 77, "Close Long", 0.015, 101_000, T0 + 5 * MINUTE, fee=1.5)]

        fill_sync.sync(exchange)

        assert trade(first)["Status"] == "Closed"
        assert trade(first)["P&L"] == pytest.approx(10 - 1.0)
        assert trade(second)["Status"] == "Open"
        assert trade(second)["Position_Size"] == pytest.approx(500)
        assert trade(second)["P&L"] == pytest.approx(5 - 0.5)

    def test_ignores_fills_from_before_the_trade(self, exchange):
        trade_id = journal()
        exchange.fills = [fill(1, 5, "Close Long", 0.00246, 60_000, T0 - 3 * MINUTE)]

        fill_sync.sync(exchange)

        assert trade(trade_id)["Status"] == "Open"

    def test_ignores_other_coins_and_the_other_direction(self, exchange):
        trade_id = journal()
        exchange.fills = [
            fill(1, 5, "Close Long", 0.00246, 3_000, T0 + MINUTE, coin="ETH"),
            fill(2, 6, "Close Short", 0.00246, 60_000, T0 + MINUTE),
        ]

        fill_sync.sync(exchange)

        assert trade(trade_id)["Status"] == "Open"

    def test_short_trade(self, exchange):
        trade_id = journal(direction="short", entry=60_000, sl=61_000, tps=((58_000, 1.0),), units=0.01)
        exchange.fills = [
            fill(1, 1, "Open Short", 0.01, 60_000, T0 - 1_000, fee=0.25),
            fill(2, 2, "Close Short", 0.01, 58_000, T0 + MINUTE, fee=0.25),
        ]

        fill_sync.sync(exchange)

        t = trade(trade_id)
        assert t["P&L"] == pytest.approx(20 - 0.5)
        assert t["TP_Hit"] and t["Hit_TPs"] == "[0]"
        assert not t["SL_Hit"]

    def test_entry_is_the_opening_fill_closest_to_when_it_was_journaled(self, exchange):
        trade_id = journal(units=0.01, entry=100_000)
        exchange.fills = [
            fill(1, 1, "Open Long", 0.01, 99_000, T0 - 4 * MINUTE, fee=5),
            fill(2, 2, "Open Long", 0.01, 100_000, T0 - 2_000, fee=0.4),
            fill(3, 3, "Close Long", 0.01, 100_500, T0 + MINUTE, fee=0.4),
        ]

        fill_sync.sync(exchange)

        assert trade(trade_id)["P&L"] == pytest.approx(5 - 0.8)


class TestScope:
    def test_paper_trades_are_never_touched(self, exchange):
        paper = journal(mode="paper")
        exchange.fills = [fill(2, 200, "Close Long", 0.00246, 60_532, T0 + MINUTE)]

        fill_sync.sync(exchange)

        assert trade(paper, "paper")["Status"] == "Open"
        exchange.get_user_fills.assert_not_called()

    def test_does_nothing_without_an_account(self):
        assert fill_sync.sync(Mock(enabled=False))["synced"] is False

    def test_deleting_a_trade_removes_its_fill_records(self, exchange):
        trade_id = journal()
        fill_sync.claim_orders(trade_id, [(13, "stop_loss", 0)])
        exchange.fills = [fill(2, 13, "Close Long", 0.001, 60_532, T0 + MINUTE)]
        fill_sync.sync(exchange)

        storage.delete_trade(trade_id, "live")

        with sqlite3.connect(storage.DB_FILE) as conn:
            assert conn.execute("SELECT COUNT(*) FROM exchange_fills").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM exchange_orders").fetchone()[0] == 0


class TestEndpoints:
    @pytest.fixture
    def live(self, client, hl, monkeypatch):
        monkeypatch.setattr(hyperliquid, "CLOSE_CONFIRM_DELAY_SECONDS", 0)
        client.post("/api/mode", json={"mode": "live"})
        hl.get_current_price.return_value = 100_000.0
        hl.get_asset_metadata.return_value = {"BTC": {"sz_decimals": 5}}
        hl.place_stop_order.return_value = RESTING
        return client

    def test_order_returns_the_ids_of_every_order_it_placed(self, live, hl):
        hl.exchange_client.order.side_effect = [_filled(0.02, 100_000, oid=42), RESTING, RESTING]

        body = live.post("/api/hyperliquid/order", json=_order()).json()

        assert body["order_ids"] == {"entry": 42, "take_profits": [7, 7], "stop_losses": [7]}

    def test_journaling_a_live_trade_records_its_orders(self, live):
        response = live.post("/api/trades?mode=live", json={
            "asset": "BTC", "direction": "long", "entry_price": 100, "stop_loss": 95, "position_size": 1_000,
            "take_profits": [{"price": 110, "allocation": 1}], "stop_losses": [{"price": 95, "allocation": 1}],
            "exchange_orders": {"entry": 1, "take_profits": [2], "stop_losses": [None]},
        })

        with sqlite3.connect(storage.DB_FILE) as conn:
            rows = conn.execute("SELECT oid, trade_id, role, level FROM exchange_orders ORDER BY oid").fetchall()
        trade_id = response.json()["trade_index"]
        assert rows == [(1, trade_id, "entry", None), (2, trade_id, "take_profit", 0)]

    def test_closing_a_journal_trade_journals_its_real_fill(self, live, hl):
        trade_id = journal(units=0.01, entry=100_000)
        hl.enabled = True
        hl.get_positions.side_effect = [[{"coin": "BTC", "size": 0.01}], []]
        hl.market_close.return_value = _filled(0.01, 101_000, oid=99)
        hl.get_user_fills.return_value = [fill(5, 99, "Close Long", 0.01, 101_000, T0 + MINUTE, fee=0.4)]

        body = live.post("/api/hyperliquid/close/BTC", json={"size": 0.01, "trade_index": trade_id}).json()

        assert body["journal"] == {"trade_index": trade_id, "status": "Closed", "exit_price": 101_000, "pnl": pytest.approx(9.6)}

    def test_closing_refuses_a_trade_that_isnt_open(self, live, hl):
        trade_id = journal()
        storage.update_trade(trade_id, {"Status": "Closed"}, "live")

        response = live.post("/api/hyperliquid/close/BTC", json={"trade_index": trade_id})

        assert response.status_code == 400
        hl.market_close.assert_not_called()


class TestFetchingFills:
    def test_pages_through_and_dedupes(self, keychain):
        import connection
        connection.save_account("0x" + "11" * 20, "mainnet")
        client = hyperliquid_client.HyperliquidClient()
        client.FILLS_PAGE_SIZE = 2
        pages = [
            [{"tid": 1, "time": 10}, {"tid": 2, "time": 20}],
            [{"tid": 2, "time": 20}, {"tid": 3, "time": 30}],
            [{"tid": 3, "time": 30}],
        ]
        with patch.object(client, "_info", side_effect=pages) as info:
            fills = client.get_user_fills(5)

        assert [f["tid"] for f in fills] == [1, 2, 3]
        assert [c.args[0]["startTime"] for c in info.call_args_list] == [5, 20, 30]
        assert info.call_args_list[0].args[0]["type"] == "userFillsByTime"
