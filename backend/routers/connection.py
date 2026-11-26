"""
Connect a Hyperliquid account from the app instead of backend/.env.

1. Connect the account (its address, from the browser wallet or typed in). That's read-only: it lets
   TradeLab show the balance and positions.
2. Enable trading with an API wallet, which can place orders but cannot withdraw. Either:
   - the browser wallet approves a new API wallet that TradeLab creates (prepare, then approve), so
     the account's own key never leaves the wallet, or
   - the user pastes the key of an API wallet they made on Hyperliquid's API page.
   Either way the key is checked against Hyperliquid and kept only in the OS keychain.
"""

import logging
import secrets
import threading
import time
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import connection
from connection import ConnectionSettingError

logger = logging.getLogger(__name__)

try:
    from hyperliquid_client import fetch_user_role, hl_client
except ImportError:
    hl_client = None
    fetch_user_role = None

router = APIRouter(prefix="/api/connection", tags=["connection"])

# The API wallet TradeLab creates is named, so approving it doesn't replace the unnamed API wallet
# Hyperliquid's own site uses. Approving a new "TradeLab" wallet supersedes the previous one.
API_WALLET_NAME = "TradeLab"
APPROVAL_TTL_SECONDS = 300

# Same fields, in the same order, as the SDK's sign_agent
APPROVE_AGENT_TYPE = "HyperliquidTransaction:ApproveAgent"
APPROVE_AGENT_FIELDS = [
    {"name": "hyperliquidChain", "type": "string"},
    {"name": "agentAddress", "type": "address"},
    {"name": "agentName", "type": "string"},
    {"name": "nonce", "type": "uint64"},
]

# Approvals waiting for the wallet's signature, by nonce. Holds the new API wallet's key in memory
# only until the approval completes or expires.
_pending: Dict[int, Dict] = {}
_pending_lock = threading.Lock()


def _state() -> Dict:
    conn = hl_client.connection
    return {
        "source": conn.source,
        "env_managed": conn.source == "env",
        "network": conn.network,
        "account_address": conn.account_address,
        "trading_enabled": bool(conn.agent_key),
        "api_wallet_address": conn.agent_address,
        "keychain_available": connection.keychain_available(),
    }


def _bad_request(e: Exception):
    raise HTTPException(status_code=400, detail=str(e))


def _role(address: str, network: str) -> Dict:
    try:
        return fetch_user_role(address, network)
    except Exception as e:
        logger.warning(f"userRole lookup failed for {address} on {network}: {e}")
        raise HTTPException(status_code=502, detail=f"Couldn't reach Hyperliquid {network} to check {address}. Try again.")


def _signer_for(account_address: str, network: str) -> str:
    """The address whose API wallets may trade `account_address`: itself, or a sub-account's master."""
    role = _role(account_address, network)
    if role.get("role") == "subAccount":
        return role["data"]["master"].lower()
    return account_address


def _require_hl():
    if not hl_client or not fetch_user_role:
        raise HTTPException(status_code=503, detail="Hyperliquid SDK not installed")


@router.get("")
def get_connection():
    _require_hl()
    return _state()


class AccountRequest(BaseModel):
    account_address: str
    network: str = connection.DEFAULT_NETWORK


@router.put("")
def connect_account(request: AccountRequest):
    """Connect an account read-only. Switching account or network removes the stored API wallet key."""
    _require_hl()
    try:
        address = connection.normalize_address(request.account_address)
        if request.network not in connection.NETWORKS:
            raise ConnectionSettingError(f"Network must be one of: {', '.join(connection.NETWORKS)}")
    except ConnectionSettingError as e:
        _bad_request(e)

    role = _role(address, request.network).get("role")
    if role == "missing":
        raise HTTPException(
            status_code=400,
            detail=f"Hyperliquid {request.network} has no account at {address}. Check the network, or deposit first.",
        )
    if role == "agent":
        raise HTTPException(
            status_code=400,
            detail="That's an API wallet address. Connect the main account (or sub-account) it trades for instead.",
        )
    if role == "vault":
        raise HTTPException(status_code=400, detail="Vault accounts aren't supported.")

    try:
        connection.save_account(address, request.network)
    except ConnectionSettingError as e:
        _bad_request(e)
    hl_client.reload()
    return _state()


@router.delete("")
def disconnect():
    """Remove the account, network and API wallet key from TradeLab."""
    _require_hl()
    try:
        connection.forget()
    except ConnectionSettingError as e:
        _bad_request(e)
    hl_client.reload()
    return _state()


class ApiWalletKeyRequest(BaseModel):
    private_key: str


@router.post("/api-wallet")
def save_api_wallet_key(request: ApiWalletKeyRequest):
    """Store a pasted API wallet key, after checking it is an approved API wallet of the account."""
    _require_hl()
    conn = hl_client.connection
    if conn.source == "env":
        _bad_request(ConnectionSettingError("This connection is configured in backend/.env."))
    if not conn.account_address:
        raise HTTPException(status_code=400, detail="Connect an account first.")
    try:
        key = connection.normalize_private_key(request.private_key)
    except ConnectionSettingError as e:
        _bad_request(e)

    key_address = connection.agent_address_for(key)
    signer = _signer_for(conn.account_address, conn.network)
    if key_address in (conn.account_address, signer):
        raise HTTPException(
            status_code=400,
            detail="That's your account's own private key, which can withdraw funds. TradeLab won't store it. "
                   "Create an API wallet on Hyperliquid (More → API) and paste that key, or use Enable trading.",
        )

    role = _role(key_address, conn.network)
    if role.get("role") != "agent":
        raise HTTPException(
            status_code=400,
            detail=f"{key_address} isn't an approved API wallet on Hyperliquid {conn.network}. Approve it on "
                   "Hyperliquid's API page first, or check the network.",
        )
    owner = str((role.get("data") or {}).get("user") or "").lower()
    if owner != signer:
        raise HTTPException(status_code=400, detail=f"That API wallet belongs to {owner}, not {signer}.")

    try:
        connection.save_agent_key(key)
    except ConnectionSettingError as e:
        _bad_request(e)
    hl_client.reload()
    return _state()


@router.delete("/api-wallet")
def remove_api_wallet_key():
    """Delete the API wallet key from the keychain. It stays approved on Hyperliquid until removed there."""
    _require_hl()
    if hl_client.connection.source == "env":
        _bad_request(ConnectionSettingError("This connection is configured in backend/.env."))
    connection.delete_agent_key()
    hl_client.reload()
    return _state()


class PrepareApprovalRequest(BaseModel):
    # The chain the browser wallet is on. Hyperliquid accepts a signature made on any chain, so the
    # user doesn't have to switch networks; hyperliquidChain is what pins it to mainnet or testnet.
    chain_id: int = Field(gt=0)


@router.post("/api-wallet/prepare")
def prepare_api_wallet_approval(request: PrepareApprovalRequest):
    """
    Create a new API wallet and return the EIP-712 message that approves it, for the browser wallet
    to sign with eth_signTypedData_v4. Nothing is sent to Hyperliquid until /approve.
    """
    _require_hl()
    conn = hl_client.connection
    if conn.source == "env":
        _bad_request(ConnectionSettingError("This connection is configured in backend/.env."))
    if not conn.account_address:
        raise HTTPException(status_code=400, detail="Connect an account first.")
    if not connection.keychain_available():
        raise HTTPException(
            status_code=400,
            detail="No system keychain is available to store the API wallet key. On a machine without one, "
                   "set the HYPERLIQUID_* variables in backend/.env instead.",
        )

    signer = _signer_for(conn.account_address, conn.network)
    agent_key = "0x" + secrets.token_hex(32)
    nonce = int(time.time() * 1000)
    action = {
        "type": "approveAgent",
        "signatureChainId": hex(request.chain_id),
        "hyperliquidChain": "Testnet" if conn.testnet else "Mainnet",
        "agentAddress": connection.agent_address_for(agent_key),
        "agentName": API_WALLET_NAME,
        "nonce": nonce,
    }
    typed_data = {
        "domain": {
            "name": "HyperliquidSignTransaction",
            "version": "1",
            "chainId": request.chain_id,
            "verifyingContract": "0x0000000000000000000000000000000000000000",
        },
        "types": {
            APPROVE_AGENT_TYPE: APPROVE_AGENT_FIELDS,
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
        },
        "primaryType": APPROVE_AGENT_TYPE,
        # Only the typed fields: wallets show the message to the user, and the hash is the same
        "message": {f["name"]: action[f["name"]] for f in APPROVE_AGENT_FIELDS},
    }

    now = time.monotonic()
    with _pending_lock:
        for stale in [n for n, p in _pending.items() if p["expires"] < now]:
            del _pending[stale]
        _pending[nonce] = {
            "agent_key": agent_key, "action": action, "typed_data": typed_data, "signer": signer,
            "account": conn.account_address, "network": conn.network, "expires": now + APPROVAL_TTL_SECONDS,
        }
    return {"nonce": nonce, "typed_data": typed_data, "signer": signer, "api_wallet_address": action["agentAddress"]}


class ApproveRequest(BaseModel):
    nonce: int
    signature: str  # 0x-prefixed 65-byte signature from eth_signTypedData_v4


def _split_signature(signature: str) -> Dict:
    raw = bytes.fromhex(signature.removeprefix("0x"))
    if len(raw) != 65:
        raise ValueError("expected a 65-byte signature")
    v = raw[64] if raw[64] >= 27 else raw[64] + 27
    return {"r": hex(int.from_bytes(raw[:32], "big")), "s": hex(int.from_bytes(raw[32:64], "big")), "v": v}


@router.post("/api-wallet/approve")
def approve_api_wallet(request: ApproveRequest):
    """Submit the wallet-signed approval to Hyperliquid and, once accepted, store the API wallet key."""
    _require_hl()
    with _pending_lock:
        pending = _pending.pop(request.nonce, None)
    if not pending or pending["expires"] < time.monotonic():
        raise HTTPException(status_code=400, detail="This approval expired or was already used. Start again.")

    conn = hl_client.connection
    if (conn.account_address, conn.network) != (pending["account"], pending["network"]):
        raise HTTPException(status_code=400, detail="The connected account changed during approval. Start again.")

    from eth_account import Account
    from eth_account.messages import encode_typed_data

    try:
        signature = _split_signature(request.signature)
        signed_by = Account.recover_message(
            encode_typed_data(full_message=pending["typed_data"]), signature=request.signature
        ).lower()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Couldn't read the wallet's signature: {e}")
    if signed_by != pending["signer"]:
        raise HTTPException(
            status_code=400,
            detail=f"The approval was signed by {signed_by}, but it must be signed by {pending['signer']}. "
                   "Switch to that account in your wallet and try again.",
        )

    try:
        result = hl_client.submit_signed_action(pending["action"], signature, request.nonce)
    except Exception as e:
        logger.warning(f"approveAgent submission failed: {e}")
        raise HTTPException(status_code=502, detail=f"Couldn't reach Hyperliquid: {e}")
    if not isinstance(result, dict) or result.get("status") != "ok":
        detail = result.get("response") if isinstance(result, dict) else result
        raise HTTPException(status_code=400, detail=f"Hyperliquid rejected the approval: {detail}")

    try:
        connection.save_agent_key(pending["agent_key"])
    except ConnectionSettingError as e:
        _bad_request(e)
    hl_client.reload()
    return _state()
