"""Comparing Hyperliquid's positions with the live journal (GET /api/hyperliquid/reconcile)."""

import pytest
from test_fill_sync import journal

from routers import hyperliquid


@pytest.fixture
def account(client, hl):
    """A connected account with no fills, whose positions are `hl.positions`."""
    hl.positions = []
    hl.fetch_positions.side_effect = lambda coin=None: hl.positions
    hl.get_user_fills.return_value = []
    return client


def position(coin="BTC", size=0.02, entry=100_000.0, leverage=10):
    return {"coin": coin, "size": size, "entry_price": entry, "leverage": leverage}


def reconcile(client):
    response = client.get("/api/hyperliquid/reconcile")
    assert response.status_code == 200
    return response.json()


class TestReconcile:
    def test_in_sync(self, account, hl):
        journal(units=0.0125, entry=100_000)
        journal(units=0.0075, entry=100_000)
        hl.positions = [position(size=0.02)]

        assert reconcile(account) == {"in_sync": True, "issues": []}

    def test_a_position_the_journal_has_no_trade_for(self, account, hl):
        hl.positions = [position(coin="kPEPE", size=-1_000)]

        [issue] = reconcile(account)["issues"]

        assert issue["kind"] == "untracked"
        assert issue["coin"] == "kPEPE"
        assert issue["untracked_size"] == -1_000
        assert "1000 kPEPE short" in issue["message"]

    def test_a_journal_trade_with_no_position(self, account, hl):
        trade_id = journal(units=0.02, entry=100_000)

        [issue] = reconcile(account)["issues"]

        assert issue["kind"] == "missing"
        assert issue["trade_ids"] == [trade_id]
        assert issue["untracked_size"] == 0

    def test_a_position_bigger_than_its_trades(self, account, hl):
        journal(units=0.01, entry=100_000)
        hl.positions = [position(size=0.03)]

        [issue] = reconcile(account)["issues"]

        assert issue["kind"] == "mismatch"
        assert issue["untracked_size"] == pytest.approx(0.02)

    def test_opposite_directions_cant_be_fixed_by_adding_a_trade(self, account, hl):
        journal(direction="short", units=0.01, entry=100_000)
        hl.positions = [position(size=0.03)]

        [issue] = reconcile(account)["issues"]

        assert issue["kind"] == "mismatch"
        assert issue["untracked_size"] == 0

    def test_small_rounding_differences_are_in_sync(self, account, hl):
        journal(units=0.02, entry=100_000)
        hl.positions = [position(size=0.02 * 1.005)]

        assert reconcile(account)["in_sync"] is True

    def test_paper_trades_are_ignored(self, account, hl):
        journal(units=0.02, entry=100_000, mode="paper")

        assert reconcile(account)["in_sync"] is True

    def test_a_failed_positions_fetch_is_an_error_not_missing_positions(self, account, hl):
        journal(units=0.02, entry=100_000)
        hl.fetch_positions.side_effect = ConnectionError("offline")

        response = account.get("/api/hyperliquid/reconcile")

        assert response.status_code == 502

    def test_applies_fills_first(self, account, hl, monkeypatch):
        """A stop that filled since the last sync closes its trade instead of showing as missing."""
        synced = []
        monkeypatch.setattr(hyperliquid.fill_sync, "sync", lambda client: synced.append(client))

        reconcile(account)

        assert synced == [hl]

    def test_needs_an_account(self, account, hl):
        hl.enabled = False

        assert account.get("/api/hyperliquid/reconcile").status_code == 503


class TestAdopt:
    def test_journals_the_untracked_position(self, account, hl):
        hl.positions = [position(size=-0.5, entry=3_000, leverage=5, coin="ETH")]

        body = account.post("/api/hyperliquid/reconcile/eth/adopt").json()

        trade = next(t for t in account.get("/api/trades/open?mode=live").json()["trades"] if t["_index"] == body["trade_index"])
        assert trade["Asset"] == "ETH-USDC"
        assert trade["Direction"] == "short"
        assert trade["Entry"] == 3_000
        assert trade["Position_Size"] == pytest.approx(1_500)
        assert trade["Margin"] == pytest.approx(300)
        assert trade["Leverage"] == 5
        assert reconcile(account)["in_sync"] is True

    def test_adds_only_what_the_journal_is_missing(self, account, hl):
        journal(units=0.01, entry=100_000)
        hl.positions = [position(size=0.03)]

        assert account.post("/api/hyperliquid/reconcile/BTC/adopt").json()["size"] == pytest.approx(0.02)
        assert reconcile(account)["in_sync"] is True

    def test_refuses_a_position_already_in_the_journal(self, account, hl):
        journal(units=0.02, entry=100_000)
        hl.positions = [position(size=0.02)]

        response = account.post("/api/hyperliquid/reconcile/BTC/adopt")

        assert response.status_code == 400
        assert len(account.get("/api/trades/open?mode=live").json()["trades"]) == 1

    def test_refuses_a_coin_with_no_position(self, account, hl):
        assert account.post("/api/hyperliquid/reconcile/BTC/adopt").status_code == 400
