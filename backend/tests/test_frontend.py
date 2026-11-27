"""The backend serves the built app on the same origin as the API (main.frontend)."""

import pytest
from conftest import make_client
from fastapi.testclient import TestClient

import main


@pytest.fixture
def dist(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>TradeLab</title>")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log('app')")
    monkeypatch.setattr(main, "FRONTEND_DIST", tmp_path)
    return tmp_path


@pytest.fixture
def app(data_dir):
    return make_client()


@pytest.mark.parametrize("path", ["/", "/trade", "/settings", "/analytics"])
def test_app_routes_get_the_app(app, dist, path):
    response = app.get(path)

    assert response.status_code == 200
    assert "<title>TradeLab</title>" in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_built_assets_are_served_and_cached(app, dist):
    response = app.get("/assets/index-abc123.js")

    assert response.text == "console.log('app')"
    assert "immutable" in response.headers["cache-control"]


def test_missing_files_are_not_the_app(app, dist):
    assert app.get("/assets/missing.js").status_code == 404
    assert app.get("/favicon.ico").status_code == 404


def test_api_routes_still_win(app, dist):
    assert app.get("/api/mode").json()["mode"] in ("paper", "live")
    assert app.get("/health").json() == {"status": "ok"}
    assert app.get("/api/nope").status_code == 404
    assert app.get("/api/nope").headers["content-type"] == "application/json"


def test_files_outside_the_build_are_never_served(app, dist):
    (dist.parent / "secret.txt").write_text("keys")

    assert "keys" not in app.get("/../secret.txt").text
    assert "keys" not in app.get("/%2e%2e/secret.txt").text


def test_explains_when_the_app_isnt_built(app, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FRONTEND_DIST", tmp_path / "missing")

    response = app.get("/")

    assert response.status_code == 404
    assert "start.py" in response.json()["detail"]


def test_the_app_is_local_only_too(data_dir, dist):
    remote = TestClient(main.app, base_url="http://evil.example")

    assert remote.get("/").status_code == 403
