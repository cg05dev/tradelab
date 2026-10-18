from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Point every data file at a temp dir so tests never touch real journals."""
    monkeypatch.setattr(main, "MODE_FILE", str(tmp_path / "mode_config.json"))
    monkeypatch.setattr(main, "DATA_FILES", {
        "live": {
            "trades": str(tmp_path / "trades.csv"),
            "portfolio": str(tmp_path / "portfolio_config.json"),
        },
        "paper": {
            "trades": str(tmp_path / "trades_paper.csv"),
            "portfolio": str(tmp_path / "portfolio_paper.json"),
        },
    })
    return tmp_path


@pytest.fixture
def hl(monkeypatch):
    """A mock Hyperliquid client, so no test can reach the real exchange."""
    client = Mock()
    client.enabled = True
    monkeypatch.setattr(main, "hl_client", client)
    return client


@pytest.fixture
def client(data_dir, hl):
    return TestClient(main.app)
