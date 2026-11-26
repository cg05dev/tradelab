from unittest.mock import Mock

import keyring
import pytest
from fastapi.testclient import TestClient
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

import hyperliquid_client
import main
import storage
from routers import hyperliquid


class MemoryKeyring(KeyringBackend):
    """An in-memory keychain, so tests never read or write the real OS keychain."""
    priority = 1

    def __init__(self):
        super().__init__()
        self.items = {}

    def get_password(self, service, username):
        return self.items.get((service, username))

    def set_password(self, service, username, password):
        self.items[(service, username)] = password

    def delete_password(self, service, username):
        if self.items.pop((service, username), None) is None:
            raise PasswordDeleteError(username)


@pytest.fixture(autouse=True)
def isolated_connection(monkeypatch, data_dir):
    """Every test starts with no Hyperliquid account: a temporary database, no .env connection, an
    empty keychain, and a client that has forgotten whatever the previous test connected."""
    for name in ("HYPERLIQUID_ENABLED", "HYPERLIQUID_WALLET_ADDRESS", "HYPERLIQUID_PRIVATE_KEY", "HYPERLIQUID_USE_TESTNET"):
        monkeypatch.delenv(name, raising=False)
    original = keyring.get_keyring()
    memory = MemoryKeyring()
    keyring.set_keyring(memory)
    hyperliquid_client.hl_client.reload()
    yield memory
    keyring.set_keyring(original)
    hyperliquid_client.hl_client.reload()


@pytest.fixture
def keychain(isolated_connection):
    return isolated_connection


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Point the database and legacy data files at a temp dir so tests never touch real journals."""
    monkeypatch.setattr(storage, "DB_FILE", str(tmp_path / "tradelab.db"))
    monkeypatch.setattr(storage, "MODE_FILE", str(tmp_path / "mode_config.json"))
    monkeypatch.setattr(storage, "DATA_FILES", {
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
    monkeypatch.setattr(hyperliquid, "hl_client", client)
    return client


def make_client(**kwargs):
    """A test client that talks to the API the way the TradeLab page does: on localhost, with the client header."""
    return TestClient(main.app, base_url="http://localhost", headers={"X-TradeLab-Client": "test"}, **kwargs)


@pytest.fixture
def client(data_dir, hl):
    return make_client()
