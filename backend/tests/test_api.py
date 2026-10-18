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

        assert client.get("/api/portfolio?mode=paper").json() == {"portfolio_size": 5_000}
        assert client.get("/api/portfolio?mode=live").json() == {"portfolio_size": 0}

    def test_rejects_negative(self, client):
        assert client.put("/api/portfolio", json={"portfolio_size": -1}).status_code == 400

    def test_reset_clears_current_mode_portfolio(self, client):
        client.put("/api/portfolio?mode=live", json={"portfolio_size": 5_000})

        response = client.post("/api/portfolio/reset")

        assert response.status_code == 200
        assert client.get("/api/portfolio?mode=live").json() == {"portfolio_size": 0}


class TestTradeLifecycle:
    def test_add_and_list_open(self, funded):
        response = funded.post("/api/trades?mode=paper", json=_trade())

        assert response.status_code == 200
        trades = funded.get("/api/trades/open?mode=paper").json()["trades"]
        assert len(trades) == 1
        assert trades[0]["Asset"] == "BTC"
        assert trades[0]["Margin"] == pytest.approx(200)
        assert trades[0]["_index"] == 0

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

    def test_close_books_pnl_to_portfolio(self, funded):
        funded.post("/api/trades?mode=paper", json=_trade())

        body = funded.post("/api/trades/close?mode=paper", json={"trade_index": 0, "exit_price": 110}).json()

        assert body["pnl"] == pytest.approx(200)
        assert body["new_portfolio_size"] == pytest.approx(10_200)
        assert funded.get("/api/trades/open?mode=paper").json()["trades"] == []

    def test_cannot_close_twice(self, funded):
        funded.post("/api/trades?mode=paper", json=_trade())
        funded.post("/api/trades/close?mode=paper", json={"trade_index": 0, "exit_price": 110})

        response = funded.post("/api/trades/close?mode=paper", json={"trade_index": 0, "exit_price": 110})

        assert response.status_code == 400

    def test_partial_take_profit_then_final(self, funded):
        funded.post("/api/trades?mode=paper", json=_trade())

        first = funded.post("/api/trades/partial-close?mode=paper", json={
            "trade_index": 0, "tp_price": 110, "tp_allocation": 0.5, "tp_index": 0,
        }).json()
        assert first["pnl"] == pytest.approx(100)
        assert first["remaining_position_size"] == pytest.approx(1_000)

        funded.post("/api/trades/partial-close?mode=paper", json={
            "trade_index": 0, "tp_price": 120, "tp_allocation": 1.0, "tp_index": 1,
        })

        closed = funded.get("/api/trades/closed?mode=paper").json()["trades"]
        assert len(closed) == 1
        assert closed[0]["P&L"] == pytest.approx(300)
        assert funded.get("/api/portfolio?mode=paper").json()["portfolio_size"] == pytest.approx(10_300)

    def test_stop_loss_hit_closes_trade(self, funded):
        funded.post("/api/trades?mode=paper", json=_trade())

        body = funded.post("/api/trades/stop-loss-hit?mode=paper", json={
            "trade_index": 0, "sl_price": 95, "sl_allocation": 1.0, "sl_index": 0,
        }).json()

        assert body["pnl"] == pytest.approx(-100)
        closed = funded.get("/api/trades/closed?mode=paper").json()["trades"]
        assert closed[0]["P&L"] == pytest.approx(-100)

    def test_delete(self, funded):
        funded.post("/api/trades?mode=paper", json=_trade(asset="BTC"))
        funded.post("/api/trades?mode=paper", json=_trade(asset="ETH"))

        funded.delete("/api/trades/0?mode=paper")

        trades = funded.get("/api/trades?mode=paper").json()["trades"]
        assert [t["Asset"] for t in trades] == ["ETH"]


class TestClosedTradesAndAnalytics:
    @pytest.fixture
    def history(self, funded):
        for asset, exit_price in [("BTC", 110), ("ETH", 90), ("SOL", 120)]:
            funded.post("/api/trades?mode=paper", json=_trade(asset=asset))
        for index, exit_price in enumerate([110, 90, 120]):
            funded.post("/api/trades/close?mode=paper", json={"trade_index": index, "exit_price": exit_price})
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


class TestCalculations:
    def test_position_size_uses_portfolio_and_risk(self, funded):
        body = funded.post("/api/calculate/position-size?mode=paper", json={
            "entry_price": 100, "stop_loss": 95, "leverage": 10, "direction": "long", "risk_percentage": 1,
        }).json()

        assert body["position_size_dollars"] == pytest.approx(2_000)
        assert body["margin_required"] == pytest.approx(200)

    def test_risk_reward(self, client):
        body = client.post("/api/calculate/risk-reward", json={
            "entry_price": 100, "stop_loss": 95, "direction": "long",
            "take_profits": [{"price": 110, "allocation": 1.0}],
        }).json()

        assert body["rr_ratio"] == pytest.approx(2.0)


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

        response = client.post("/api/hyperliquid/close/BTC")

        assert response.status_code == 403
        hl.market_close.assert_not_called()


class TestWebhook:
    PAYLOAD = {"asset": "BTC", "direction": "long", "entry": 100, "sl": 95, "tp1": 110, "tp1_alloc": 100,
               "portfolio_size": 10_000, "risk_pct": 1, "mode": "paper"}

    def test_disabled_without_configured_secret(self, client, monkeypatch):
        monkeypatch.delenv("TRADELAB_WEBHOOK_SECRET", raising=False)

        assert client.post("/api/webhook/trade", json=self.PAYLOAD).status_code == 503
        assert client.get("/api/trades?mode=paper").json() == {"trades": []}

    @pytest.mark.parametrize("secret", [None, "wrong"])
    def test_rejects_missing_or_wrong_secret(self, client, monkeypatch, secret):
        monkeypatch.setenv("TRADELAB_WEBHOOK_SECRET", "s3cret")

        response = client.post("/api/webhook/trade", json={**self.PAYLOAD, "secret": secret})

        assert response.status_code == 401
        assert client.get("/api/trades?mode=paper").json() == {"trades": []}

    def test_secret_in_body_creates_sized_trade(self, client, monkeypatch):
        monkeypatch.setenv("TRADELAB_WEBHOOK_SECRET", "s3cret")

        response = client.post("/api/webhook/trade", json={**self.PAYLOAD, "secret": "s3cret"})

        assert response.status_code == 200
        assert response.json()["position_size"] == pytest.approx(2_000)
        trades = client.get("/api/trades/open?mode=paper").json()["trades"]
        assert len(trades) == 1
        assert "s3cret" not in str(trades)

    def test_secret_in_header(self, client, monkeypatch):
        monkeypatch.setenv("TRADELAB_WEBHOOK_SECRET", "s3cret")

        response = client.post("/api/webhook/trade", json=self.PAYLOAD, headers={"X-Webhook-Secret": "s3cret"})

        assert response.status_code == 200


class TestCors:
    def test_allows_frontend_origin(self, client):
        response = client.get("/health", headers={"Origin": "http://localhost:3001"})

        assert response.headers.get("access-control-allow-origin") == "http://localhost:3001"

    def test_does_not_allow_other_origins(self, client):
        response = client.get("/health", headers={"Origin": "https://evil.example"})

        assert "access-control-allow-origin" not in response.headers
