"""The API only answers the TradeLab page on this computer (see main.local_only)."""

import pytest
from conftest import make_client
from fastapi.testclient import TestClient

import main


@pytest.fixture
def local(data_dir):
    return make_client()


def test_page_requests_are_allowed(local):
    assert local.get("/api/mode").status_code == 200
    assert local.post("/api/mode", json={"mode": "paper"}).status_code == 200


@pytest.mark.parametrize("base_url", ["http://127.0.0.1:8000", "http://[::1]:8000", "http://localhost:8000"])
def test_loopback_hosts_are_local(data_dir, base_url):
    assert TestClient(main.app, base_url=base_url).get("/api/mode").status_code == 200


def test_other_hosts_are_refused(data_dir):
    """A DNS-rebinding page, or a tunnel, sends its own hostname."""
    remote = TestClient(main.app, base_url="http://evil.example", headers={"X-TradeLab-Client": "x"})

    assert remote.get("/api/mode").status_code == 403
    assert remote.post("/api/hyperliquid/close/BTC", json={}).status_code == 403


@pytest.mark.parametrize("header", ["X-Forwarded-For", "Forwarded", "CF-Connecting-IP"])
def test_proxied_requests_are_refused_even_with_a_localhost_host(local, header):
    """A tunnel that rewrites Host to localhost still adds forwarding headers."""
    assert local.get("/api/mode", headers={header: "203.0.113.7"}).status_code == 403


def test_changes_require_the_client_header(data_dir):
    """A cross-site form post or fetch can't add a custom header without passing CORS."""
    bare = TestClient(main.app, base_url="http://localhost")

    assert bare.get("/api/mode").status_code == 200
    assert bare.post("/api/mode", json={"mode": "paper"}).status_code == 403
    assert bare.put("/api/connection", json={"account_address": "0x" + "1" * 40}).status_code == 403
    assert bare.get("/api/mode").json()["mode"] == "live"


def test_webhook_is_reachable_through_a_tunnel(data_dir, monkeypatch):
    """TradingView reaches the webhook from outside; it has its own secret (503 here: none configured)."""
    monkeypatch.delenv("TRADELAB_WEBHOOK_SECRET", raising=False)
    remote = TestClient(main.app, base_url="https://abc.tunnel.example", headers={"X-Forwarded-For": "52.89.214.238"})

    assert remote.post("/api/webhook/trade", json={}).status_code == 503
