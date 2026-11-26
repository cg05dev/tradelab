"""Paper trades fill like live ones, against market prices (paper_sim.py)."""

import pytest

import fees
import paper_sim
import storage
from fill_sync import _opened_ms

RATES = {"taker": 0.0005, "maker": 0.0002, "stop_slippage": 0.001, "source": "default"}
MINUTE = 60_000


class FakeMarket:
    def __init__(self, mid=None, candles=()):
        self.prices = {"BTC": mid} if mid is not None else {}
        self.candle_list = list(candles)
        self.candle_calls = []

    def mids(self):
        return dict(self.prices)

    def candles(self, coin, start_ms, end_ms):
        self.candle_calls.append((coin, start_ms, end_ms))
        return [c for c in self.candle_list if start_ms - MINUTE < c["t"] <= end_ms]


@pytest.fixture
def paper(client, monkeypatch):
    """Paper mode with a $1,000 balance, trading at RATES."""
    monkeypatch.setattr(fees, "current_rates", lambda client: RATES)
    client.post("/api/mode", json={"mode": "planning"})
    client.put("/api/portfolio?mode=paper", json={"portfolio_size": 1_000})
    return client


def open_trade(api, direction="long", sl=95, tps=((110, 0.5), (120, 0.5)), leverage=10):
    """10 BTC-equivalent units at 100 ($1,000 notional)."""
    return api.post("/api/trades?mode=paper", json={
        "asset": "BTC-USDC", "direction": direction, "entry_price": 100, "stop_loss": sl, "position_size": 1_000,
        "take_profits": [{"price": p, "allocation": a} for p, a in tps], "stop_losses": [{"price": sl, "allocation": 1}] if sl else [],
        "leverage": leverage,
    }).json()["trade_index"]


def trade(trade_id):
    return storage.load_trades("paper").loc[trade_id]


def balance():
    return storage.load_portfolio_size("paper")


def opened(trade_id):
    return _opened_ms(trade(trade_id)["Date"])


def step(market, trade_id, after_ms=1_000):
    return paper_sim.step(market, RATES, now_ms=opened(trade_id) + after_ms)


class TestFees:
    def test_opening_pays_the_taker_fee(self, paper):
        trade_id = open_trade(paper)

        assert trade(trade_id)["P&L"] == pytest.approx(-0.5)  # 0.05% of $1,000
        assert balance() == pytest.approx(999.5)

    def test_closing_by_hand_pays_the_taker_fee_and_keeps_earlier_pnl(self, paper):
        trade_id = open_trade(paper)

        paper.post("/api/trades/close?mode=paper", json={"trade_index": trade_id, "exit_price": 105})

        assert trade(trade_id)["P&L"] == pytest.approx(-0.5 + 50 - 0.525)
        assert balance() == pytest.approx(1_000 - 0.5 + 50 - 0.525)


class TestStop:
    def test_fills_past_the_stop_and_closes(self, paper):
        trade_id = open_trade(paper)

        result = step(FakeMarket(mid=94.99), trade_id)

        t = trade(trade_id)
        exit_price = 95 * (1 - 0.001)
        loss = (exit_price - 100) * 10 - 0.0005 * exit_price * 10
        assert result["closed"] == [trade_id]
        assert t["Status"] == "Closed"
        assert t["SL_Hit"] and t["Exit_Price"] == pytest.approx(exit_price)
        assert t["P&L"] == pytest.approx(-0.5 + loss)
        assert t["Position_Size"] == pytest.approx(1_000)
        assert balance() == pytest.approx(1_000 - 0.5 + loss)

    def test_a_gap_through_the_stop_fills_at_the_market(self, paper):
        trade_id = open_trade(paper)

        step(FakeMarket(mid=90), trade_id)

        assert trade(trade_id)["Exit_Price"] == pytest.approx(90)

    def test_without_a_stop_the_trade_is_liquidated(self, paper):
        trade_id = open_trade(paper, sl=0, tps=())
        liquidation = 100 * (1 - (1 / 10 - 0.0125))

        step(FakeMarket(mid=91), trade_id)

        assert trade(trade_id)["Status"] == "Closed"
        assert trade(trade_id)["Exit_Price"] == pytest.approx(liquidation)
        assert not trade(trade_id)["SL_Hit"]

    def test_short(self, paper):
        trade_id = open_trade(paper, direction="short", sl=105, tps=((90, 1.0),))

        step(FakeMarket(mid=105.05), trade_id)  # just past the stop, before the slippage

        exit_price = 105 * 1.001
        assert trade(trade_id)["Exit_Price"] == pytest.approx(exit_price)
        assert trade(trade_id)["P&L"] == pytest.approx(-0.5 + (100 - exit_price) * 10 - 0.0005 * exit_price * 10)


class TestTakeProfits:
    def test_partial_then_final_target(self, paper):
        trade_id = open_trade(paper)

        step(FakeMarket(mid=110), trade_id)

        t = trade(trade_id)
        assert t["Status"] == "Open"
        assert t["TP_Hit"] and t["Hit_TPs"] == "[0]"
        assert t["Position_Size"] == pytest.approx(500)
        assert t["P&L"] == pytest.approx(-0.5 + 50 - 0.0002 * 110 * 5)

        step(FakeMarket(mid=121), trade_id, after_ms=2_000)

        t = trade(trade_id)
        assert t["Status"] == "Closed"
        assert t["Hit_TPs"] == "[0, 1]"
        assert t["Exit_Price"] == pytest.approx(115)
        assert t["P&L"] == pytest.approx(-0.5 + 50 + 100 - 0.0002 * (110 + 120) * 5)
        assert balance() == pytest.approx(1_000 + t["P&L"])

    def test_nothing_fills_twice(self, paper):
        trade_id = open_trade(paper)
        step(FakeMarket(mid=110), trade_id)
        before = (trade(trade_id)["P&L"], balance())

        step(FakeMarket(mid=110), trade_id, after_ms=2_000)

        assert (trade(trade_id)["P&L"], balance()) == before


class TestCandles:
    def test_a_wick_between_checks_still_fills(self, paper):
        trade_id = open_trade(paper)
        t0 = opened(trade_id)
        market = FakeMarket(mid=105, candles=[{"t": t0 + MINUTE, "o": 104, "h": 111, "l": 103}])

        step(market, trade_id, after_ms=2 * MINUTE)

        assert market.candle_calls
        assert trade(trade_id)["Hit_TPs"] == "[0]"

    def test_a_candle_reaching_both_counts_the_stop_first(self, paper):
        trade_id = open_trade(paper)
        t0 = opened(trade_id)

        step(FakeMarket(mid=100, candles=[{"t": t0 + MINUTE, "o": 100, "h": 111, "l": 94}]), trade_id, after_ms=2 * MINUTE)

        assert trade(trade_id)["Status"] == "Closed"
        assert trade(trade_id)["SL_Hit"] and not trade(trade_id)["TP_Hit"]

    def test_prices_from_before_the_trade_are_ignored(self, paper):
        trade_id = open_trade(paper)
        t0 = opened(trade_id)

        step(FakeMarket(mid=100, candles=[{"t": t0 - 30_000, "o": 100, "h": 100, "l": 90}]), trade_id, after_ms=2 * MINUTE)

        assert trade(trade_id)["Status"] == "Open"

    def test_candles_are_checked_once_a_minute(self, paper):
        trade_id = open_trade(paper)
        market = FakeMarket(mid=100)

        step(market, trade_id, after_ms=10_000)

        assert market.candle_calls == []


class TestScope:
    def test_no_open_paper_trades_means_no_requests(self, paper):
        market = FakeMarket(mid=100)
        market.mids = lambda: pytest.fail("should not fetch prices")

        assert paper_sim.step(market, RATES) == {"closed": [], "updated": []}

    def test_live_trades_are_left_to_fill_sync(self, paper):
        live_id = storage.insert_trade({"Date": "2026-11-26 17:17:33", "Asset": "BTC-USDC", "Direction": "long", "Entry": 100,
                                        "SL": 95, "Position_Size": 1_000, "Status": "Open", "TPs": "[]", "SLs": "[]"}, "live")

        paper_sim.step(FakeMarket(mid=50), RATES)

        assert storage.load_trades("live").loc[live_id]["Status"] == "Open"

    def test_trades_from_before_simulation_start_being_watched_now(self, paper):
        trade_id = storage.insert_trade({"Date": "2026-01-01 00:00:00", "Asset": "BTC-USDC", "Direction": "long", "Entry": 100,
                                         "SL": 95, "Position_Size": 1_000, "Status": "Open", "TPs": "[]", "SLs": "[]",
                                         "Leverage": 10, "Hit_TPs": "[]"}, "paper")
        market = FakeMarket(mid=100, candles=[{"t": _opened_ms("2026-01-02 00:00:00"), "o": 100, "h": 100, "l": 80}])

        paper_sim.step(market, RATES)

        assert trade(trade_id)["Status"] == "Open"  # its old history isn't replayed
        assert market.candle_calls == []
