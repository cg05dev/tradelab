"""Connecting a Hyperliquid account and enabling trading from the app (routers/connection.py)."""

import copy

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from hyperliquid.utils.signing import sign_agent

import connection
from conftest import make_client
from routers import connection as connection_router

MAIN = Account.from_key("0x" + "11" * 32)       # the user's main wallet
API_WALLET = Account.from_key("0x" + "22" * 32)  # an API wallet approved for MAIN
STRANGER = Account.from_key("0x" + "33" * 32)
SUB_ACCOUNT = "0x" + "ab" * 20


@pytest.fixture
def roles(monkeypatch):
    """Hyperliquid's userRole answers, by lowercase address. Unknown addresses are "missing"."""
    table = {
        MAIN.address.lower(): {"role": "user"},
        API_WALLET.address.lower(): {"role": "agent", "data": {"user": MAIN.address.lower()}},
        SUB_ACCOUNT: {"role": "subAccount", "data": {"master": MAIN.address.lower()}},
    }
    monkeypatch.setattr(connection_router, "fetch_user_role", lambda address, network: table.get(address.lower(), {"role": "missing"}))
    return table


@pytest.fixture
def api(data_dir, roles):
    return make_client()


@pytest.fixture
def connected(api):
    assert api.put("/api/connection", json={"account_address": MAIN.address, "network": "mainnet"}).status_code == 200
    return api


@pytest.fixture
def submitted(monkeypatch):
    """Capture actions sent to Hyperliquid's /exchange instead of sending them."""
    calls = []

    def submit(action, signature, nonce):
        calls.append({"action": action, "signature": signature, "nonce": nonce})
        return {"status": "ok", "response": {"type": "default"}}

    monkeypatch.setattr(connection_router.hl_client, "submit_signed_action", submit)
    return calls


def _sign(typed_data, wallet=MAIN):
    return Account.sign_message(encode_typed_data(full_message=typed_data), wallet.key).signature.hex()


class TestAccount:
    def test_starts_disconnected(self, api):
        state = api.get("/api/connection").json()

        assert state["source"] == "none"
        assert state["account_address"] is None
        assert state["trading_enabled"] is False

    def test_connect_is_read_only(self, connected):
        state = connected.get("/api/connection").json()

        assert state["account_address"] == MAIN.address.lower()
        assert state["network"] == "mainnet"
        assert state["trading_enabled"] is False

    @pytest.mark.parametrize("body, message", [
        ({"account_address": "0x1234"}, "valid address"),
        ({"account_address": MAIN.address, "network": "devnet"}, "Network"),
        ({"account_address": STRANGER.address}, "no account"),
        ({"account_address": API_WALLET.address}, "API wallet address"),
    ])
    def test_rejects(self, api, body, message):
        response = api.put("/api/connection", json=body)

        assert response.status_code == 400
        assert message in response.json()["detail"]
        assert api.get("/api/connection").json()["account_address"] is None

    def test_env_connection_wins_and_is_read_only(self, api, monkeypatch):
        monkeypatch.setenv("HYPERLIQUID_ENABLED", "true")
        monkeypatch.setenv("HYPERLIQUID_WALLET_ADDRESS", MAIN.address)
        connection_router.hl_client.reload()

        assert api.get("/api/connection").json()["source"] == "env"
        assert api.put("/api/connection", json={"account_address": MAIN.address}).status_code == 400
        assert api.delete("/api/connection").status_code == 400


class TestPastedApiWalletKey:
    def test_stores_an_approved_api_wallet_in_the_keychain_only(self, connected, keychain, data_dir):
        response = connected.post("/api/connection/api-wallet", json={"private_key": API_WALLET.key.hex()})

        assert response.status_code == 200
        state = response.json()
        assert state["trading_enabled"] is True
        assert state["api_wallet_address"] == API_WALLET.address.lower()
        assert list(keychain.items.values()) == ["0x" + API_WALLET.key.hex().removeprefix("0x")]
        key_hex = API_WALLET.key.hex().removeprefix("0x")
        assert key_hex not in response.text
        assert key_hex.encode() not in (data_dir / "tradelab.db").read_bytes()

    def test_refuses_the_main_wallet_key(self, connected, keychain):
        response = connected.post("/api/connection/api-wallet", json={"private_key": MAIN.key.hex()})

        assert response.status_code == 400
        assert "withdraw" in response.json()["detail"]
        assert keychain.items == {}

    def test_refuses_a_key_that_is_not_an_api_wallet(self, connected, keychain):
        response = connected.post("/api/connection/api-wallet", json={"private_key": STRANGER.key.hex()})

        assert response.status_code == 400
        assert keychain.items == {}

    def test_refuses_another_accounts_api_wallet(self, connected, roles, keychain):
        roles[API_WALLET.address.lower()] = {"role": "agent", "data": {"user": STRANGER.address.lower()}}

        response = connected.post("/api/connection/api-wallet", json={"private_key": API_WALLET.key.hex()})

        assert response.status_code == 400
        assert keychain.items == {}

    def test_remove_deletes_the_key(self, connected, keychain):
        connected.post("/api/connection/api-wallet", json={"private_key": API_WALLET.key.hex()})

        state = connected.delete("/api/connection/api-wallet").json()

        assert state["trading_enabled"] is False
        assert keychain.items == {}

    def test_switching_account_or_network_removes_the_key(self, connected, keychain):
        connected.post("/api/connection/api-wallet", json={"private_key": API_WALLET.key.hex()})

        connected.put("/api/connection", json={"account_address": MAIN.address, "network": "testnet"})

        assert keychain.items == {}
        assert connected.get("/api/connection").json()["trading_enabled"] is False

    def test_disconnect_forgets_everything(self, connected, keychain):
        connected.post("/api/connection/api-wallet", json={"private_key": API_WALLET.key.hex()})

        state = connected.delete("/api/connection").json()

        assert state["account_address"] is None
        assert keychain.items == {}

    def test_sub_account_uses_its_masters_api_wallet(self, api, keychain):
        api.put("/api/connection", json={"account_address": SUB_ACCOUNT})

        response = api.post("/api/connection/api-wallet", json={"private_key": API_WALLET.key.hex()})

        assert response.status_code == 200
        assert response.json()["trading_enabled"] is True

    def test_without_a_keychain_explains_the_env_fallback(self, connected, monkeypatch):
        import keyring
        from keyring.backends import fail
        keyring.set_keyring(fail.Keyring())

        response = connected.post("/api/connection/api-wallet", json={"private_key": API_WALLET.key.hex()})

        assert response.status_code == 400
        assert "backend/.env" in response.json()["detail"]


class TestWalletApproval:
    def test_matches_the_sdk_signature_and_stores_the_new_api_wallet(self, connected, submitted, keychain):
        # 421614 is the chain the SDK itself signs on, so its signature must equal the wallet's
        prepared = connected.post("/api/connection/api-wallet/prepare", json={"chain_id": 421614}).json()
        signature = _sign(prepared["typed_data"])

        sdk_action = {k: v for k, v in submitted_action(prepared).items()}
        sdk_signature = sign_agent(MAIN, sdk_action, is_mainnet=True)

        response = connected.post("/api/connection/api-wallet/approve", json={"nonce": prepared["nonce"], "signature": signature})

        assert response.status_code == 200
        assert response.json()["trading_enabled"] is True
        assert response.json()["api_wallet_address"] == prepared["api_wallet_address"]
        [call] = submitted
        assert call["signature"] == sdk_signature
        assert call["action"]["agentName"] == "TradeLab"
        assert call["action"]["hyperliquidChain"] == "Mainnet"
        assert call["nonce"] == prepared["nonce"]
        assert connection.agent_address_for(next(iter(keychain.items.values()))) == prepared["api_wallet_address"]

    def test_signs_on_the_wallets_current_chain(self, connected, submitted):
        prepared = connected.post("/api/connection/api-wallet/prepare", json={"chain_id": 42161}).json()

        assert prepared["typed_data"]["domain"]["chainId"] == 42161
        connected.post("/api/connection/api-wallet/approve", json={"nonce": prepared["nonce"], "signature": _sign(prepared["typed_data"])})
        assert submitted[0]["action"]["signatureChainId"] == "0xa4b1"

    def test_testnet_approvals_say_testnet(self, api, submitted):
        api.put("/api/connection", json={"account_address": MAIN.address, "network": "testnet"})

        prepared = api.post("/api/connection/api-wallet/prepare", json={"chain_id": 1}).json()

        assert prepared["typed_data"]["message"]["hyperliquidChain"] == "Testnet"

    def test_rejects_a_signature_from_another_wallet(self, connected, submitted, keychain):
        prepared = connected.post("/api/connection/api-wallet/prepare", json={"chain_id": 1}).json()

        response = connected.post("/api/connection/api-wallet/approve", json={
            "nonce": prepared["nonce"], "signature": _sign(prepared["typed_data"], STRANGER),
        })

        assert response.status_code == 400
        assert "must be signed by" in response.json()["detail"]
        assert submitted == []
        assert keychain.items == {}

    def test_an_approval_can_only_be_used_once(self, connected, submitted):
        prepared = connected.post("/api/connection/api-wallet/prepare", json={"chain_id": 1}).json()
        body = {"nonce": prepared["nonce"], "signature": _sign(prepared["typed_data"])}
        connected.post("/api/connection/api-wallet/approve", json=body)

        assert connected.post("/api/connection/api-wallet/approve", json=body).status_code == 400
        assert len(submitted) == 1

    def test_hyperliquid_rejection_stores_nothing(self, connected, monkeypatch, keychain):
        monkeypatch.setattr(connection_router.hl_client, "submit_signed_action",
                            lambda *a: {"status": "err", "response": "Too many agents"})
        prepared = connected.post("/api/connection/api-wallet/prepare", json={"chain_id": 1}).json()

        response = connected.post("/api/connection/api-wallet/approve", json={"nonce": prepared["nonce"], "signature": _sign(prepared["typed_data"])})

        assert response.status_code == 400
        assert "Too many agents" in response.json()["detail"]
        assert keychain.items == {}

    def test_sub_account_approval_is_signed_by_the_master(self, api, submitted):
        api.put("/api/connection", json={"account_address": SUB_ACCOUNT})

        prepared = api.post("/api/connection/api-wallet/prepare", json={"chain_id": 1}).json()

        assert prepared["signer"] == MAIN.address.lower()
        response = api.post("/api/connection/api-wallet/approve", json={"nonce": prepared["nonce"], "signature": _sign(prepared["typed_data"])})
        assert response.status_code == 200


def submitted_action(prepared):
    """The approveAgent action the SDK would build for the prepared message (before it adds chain fields)."""
    message = copy.deepcopy(prepared["typed_data"]["message"])
    return {"type": "approveAgent", "agentAddress": message["agentAddress"], "agentName": message["agentName"], "nonce": message["nonce"]}
