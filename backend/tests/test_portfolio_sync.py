"""The live portfolio comes from the connected Hyperliquid account (routers/portfolio.py)."""

from unittest.mock import Mock

import pytest

from conftest import make_client
from routers import portfolio

SUMMARY = {"account_value": 12_345.67, "withdrawable": 10_000.0, "margin_used": 2_345.67, "updated_at": "2026-11-26T12:00:00+00:00"}


@pytest.fixture
def account(monkeypatch):
    """A connected Hyperliquid account whose value is SUMMARY's."""
    client = Mock(enabled=True)
    client.get_account_summary.return_value = SUMMARY
    client.last_account_summary.return_value = None
    monkeypatch.setattr(portfolio, "hl_client", client)
    return client


@pytest.fixture
def api(data_dir, hl):
    api = make_client()
    api.put("/api/portfolio?mode=paper", json={"portfolio_size": 2_000})
    return api


def test_without_an_account_live_has_no_portfolio(api):
    body = api.get("/api/portfolio?mode=live").json()

    assert body["portfolio_size"] is None
    assert body["source"] == "none"
    assert "Settings" in body["sync_error"]


def test_without_an_account_live_sizing_is_refused(api):
    response = api.post("/api/calculate/position-size?mode=live", json={
        "entry_price": 100, "stop_loss": 95, "leverage": 10, "direction": "long", "risk_percentage": 1,
    })

    assert response.status_code == 409


def test_the_live_portfolio_can_never_be_typed_in(api):
    assert api.put("/api/portfolio?mode=live", json={"portfolio_size": 500}).status_code == 400
    assert api.post("/api/portfolio/reset?mode=live").status_code == 400


def test_live_portfolio_is_the_account_value(api, account):
    body = api.get("/api/portfolio?mode=live").json()

    assert body["portfolio_size"] == pytest.approx(12_345.67)
    assert body["source"] == "hyperliquid"
    assert body["stale"] is False
    assert body["withdrawable"] == pytest.approx(10_000)


def test_paper_portfolio_stays_manual(api, account):
    assert api.get("/api/portfolio?mode=paper").json() == {"portfolio_size": 2_000, "source": "manual"}
    account.get_account_summary.assert_not_called()


def test_paper_balance_stays_editable_while_connected(api, account):
    assert api.put("/api/portfolio?mode=live", json={"portfolio_size": 1}).status_code == 400
    assert api.put("/api/portfolio?mode=paper", json={"portfolio_size": 3_000}).status_code == 200


def test_outage_shows_the_last_value_as_stale(api, account):
    account.get_account_summary.side_effect = RuntimeError("timeout")
    account.last_account_summary.return_value = SUMMARY

    body = api.get("/api/portfolio?mode=live").json()

    assert body["portfolio_size"] == pytest.approx(12_345.67)
    assert body["stale"] is True


def test_outage_before_any_sync_refuses_to_guess(api, account):
    account.get_account_summary.side_effect = RuntimeError("timeout")

    body = api.get("/api/portfolio?mode=live").json()
    sizing = api.post("/api/calculate/position-size?mode=live", json={
        "entry_price": 100, "stop_loss": 95, "leverage": 10, "direction": "long", "risk_percentage": 1,
    })

    assert body["portfolio_size"] is None
    assert body["source"] == "hyperliquid"
    assert "sync_error" in body
    assert sizing.status_code == 503


def test_position_sizing_uses_the_account_value(api, account):
    body = api.post("/api/calculate/position-size?mode=live", json={
        "entry_price": 100, "stop_loss": 95, "leverage": 10, "direction": "long", "risk_percentage": 1,
    }).json()

    assert body["risk_amount"] == pytest.approx(123.4567)
