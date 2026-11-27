from unittest.mock import Mock

import pytest


def _trade(**overrides):
    trade = {
        "asset": "BTC",
        "direction": "long",
        "entry_price": 100,
        "stop_loss": 95,
        "position_size": 2_000,
        "take_profits": [{"price": 110, "allocation": 0.5}, {"price": 120, "allocation": 0.5}],
        "stop_losses": [{"price": 95, "allocation": 1.0}],
        "leverage": 10,
    }
    trade.update(overrides)
    return trade


def _open(client, **overrides):
    """Add a paper trade and return its id."""
    return client.post("/api/trades?mode=paper", json=_trade(**overrides)).json()["trade_index"]


@pytest.fixture
def funded(client):
    client.put("/api/portfolio?mode=paper", json={"portfolio_size": 10_000})
    return client


class TestMode:
    def test_defaults_to_live(self, client):
        assert client.get("/api/mode").json() == {"mode": "live"}

    def test_planning_is_an_alias_for_paper(self, client):
        assert client.post("/api/mode", json={"mode": "planning"}).json()["mode"] == "paper"
        assert client.get("/api/mode").json() == {"mode": "paper"}

    def test_rejects_unknown_mode(self, client):
        assert client.post("/api/mode", json={"mode": "yolo"}).status_code == 400


class TestPortfolio:
    def test_update_and_read(self, client):
        client.put("/api/portfolio?mode=paper", json={"portfolio_size": 5_000})

        assert client.get("/api/portfolio?mode=paper").json() == {"portfolio_size": 5_000, "source": "manual"}
        assert client.get("/api/portfolio?mode=live").json()["source"] == "none"

    def test_rejects_negative(self, client):
        assert client.put("/api/portfolio", json={"portfolio_size": -1}).status_code == 400

    def test_reset_clears_the_paper_balance(self, client):
        client.put("/api/portfolio?mode=paper", json={"portfolio_size": 5_000})

        response = client.post("/api/portfolio/reset?mode=paper")

        assert response.status_code == 200
        assert client.get("/api/portfolio?mode=paper").json()["portfolio_size"] == 0


@pytest.mark.usefixtures("no_fees")
class TestTradeLifecycle:
    def test_add_and_list_open(self, funded):
        response = funded.post("/api/trades?mode=paper", json=_trade())

        assert response.status_code == 200
        trades = funded.get("/api/trades/open?mode=paper").json()["trades"]
        assert len(trades) == 1
        assert trades[0]["Asset"] == "BTC"
        assert trades[0]["Margin"] == pytest.approx(200)
        assert trades[0]["_index"] == response.json()["trade_index"]

    def test_modes_have_separate_journals(self, funded):
        funded.post("/api/trades?mode=paper", json=_trade())

        assert funded.get("/api/trades?mode=live").json() == {"trades": []}

    @pytest.mark.parametrize("overrides", [
        {"entry_price": 0},
        {"direction": "sideways"},
        {"stop_loss": 105},
        {"take_profits": [{"price": 90, "allocation": 1.0}]},
    ])
    def test_invalid_trade_is_a_client_error(self, funded, overrides):
        response = funded.post("/api/trades?mode=paper", json=_trade(**overrides))

        assert response.status_code == 400

    @pytest.mark.parametrize("allocation", [50, 100, -0.1])
    def test_rejects_allocations_that_are_not_fractions(self, funded, allocation):
        response = funded.post("/api/trades?mode=paper", json=_trade(take_profits=[{"price": 110, "allocation": allocation}]))

        assert response.status_code == 422
        assert funded.get("/api/trades?mode=paper").json() == {"trades": []}

    def test_close_books_pnl_to_portfolio(self, funded):
        trade_id = _open(funded)

        body = funded.post("/api/trades/close?mode=paper", json={"trade_index": trade_id, "exit_price": 110}).json()

        assert body["pnl"] == pytest.approx(200)
        assert body["new_portfolio_size"] == pytest.approx(10_200)
        assert funded.get("/api/trades/open?mode=paper").json()["trades"] == []

    def test_cannot_close_twice(self, funded):
        trade_id = _open(funded)
        funded.post("/api/trades/close?mode=paper", json={"trade_index": trade_id, "exit_price": 110})

        response = funded.post("/api/trades/close?mode=paper", json={"trade_index": trade_id, "exit_price": 110})

        assert response.status_code == 400

    def test_delete(self, funded):
        btc = _open(funded, asset="BTC")
        _open(funded, asset="ETH")

        assert funded.delete(f"/api/trades/{btc}?mode=paper").status_code == 200

        trades = funded.get("/api/trades?mode=paper").json()["trades"]
        assert [t["Asset"] for t in trades] == ["ETH"]


@pytest.mark.usefixtures("no_fees")
class TestClosedTradesAndAnalytics:
    @pytest.fixture
    def history(self, funded):
        ids = [_open(funded, asset=asset) for asset in ["BTC", "ETH", "SOL"]]
        for trade_id, exit_price in zip(ids, [110, 90, 120], strict=True):
            funded.post("/api/trades/close?mode=paper", json={"trade_index": trade_id, "exit_price": exit_price})
        return funded

    def test_search_sort_and_paginate(self, history):
        body = history.get("/api/trades/closed?mode=paper&sort=pnl_desc&limit=2&page=1").json()

        assert body["count"] == 3
        assert [t["Asset"] for t in body["trades"]] == ["SOL", "BTC"]
        assert history.get("/api/trades/closed?mode=paper&search=eth").json()["count"] == 1

    def test_metrics(self, history):
        metrics = history.get("/api/analytics/metrics?mode=paper").json()

        assert metrics["total_pnl"] == pytest.approx(400)  # +200, -200, +400
        assert metrics["win_rate"] == pytest.approx(200 / 3)
        assert metrics["profit_factor"] == pytest.approx(3.0)
        assert metrics["max_drawdown"] == pytest.approx(200)
        assert (metrics["win_count"], metrics["loss_count"]) == (2, 1)

    def test_pnl_series_is_cumulative(self, history):
        series = history.get("/api/analytics/pnl-series?mode=paper").json()

        assert [p["cumulative_pnl"] for p in series] == pytest.approx([200, 0, 400])


class TestFeeRates:
    def test_defaults_without_an_account(self, client):
        body = client.get("/api/hyperliquid/fees").json()

        assert body == {"taker": 0.00045, "maker": 0.00015, "stop_slippage": 0.0005, "source": "default"}

    def test_uses_the_accounts_rates(self, client, monkeypatch):
        from routers import hyperliquid
        account = Mock(enabled=True, get_fee_rates=Mock(return_value={"taker": 0.000432, "maker": 0.000144}))
        monkeypatch.setattr(hyperliquid, "hl_client", account)

        body = client.get("/api/hyperliquid/fees").json()

        assert body["taker"] == pytest.approx(0.000432)
        assert body["source"] == "account"


class TestExecutionGuard:
    def test_live_order_blocked_in_paper_mode(self, client, hl):
        client.post("/api/mode", json={"mode": "planning"})

        response = client.post("/api/hyperliquid/order", json={
            "coin": "BTC", "is_buy": True, "margin_amount": 100, "leverage": 10, "entry_price": 100,
        })

        assert response.status_code == 403
        hl.exchange_client.order.assert_not_called()

    def test_close_position_blocked_in_paper_mode(self, client, hl):
        client.post("/api/mode", json={"mode": "paper"})

        response = client.post("/api/hyperliquid/close/BTC", json={})

        assert response.status_code == 403
        hl.market_close.assert_not_called()


class TestCors:
    def test_allows_frontend_origin(self, client):
        response = client.get("/health", headers={"Origin": "http://localhost:3001"})

        assert response.headers.get("access-control-allow-origin") == "http://localhost:3001"

    def test_does_not_allow_other_origins(self, client):
        response = client.get("/health", headers={"Origin": "https://evil.example"})

        assert "access-control-allow-origin" not in response.headers
