"""
Which Hyperliquid account TradeLab reads and trades, on which network, and the API wallet key it
signs orders with.

- The account address and network are ordinary settings in the database.
- The API wallet's private key is kept in the OS keychain (macOS Keychain, Windows Credential
  Manager, Secret Service/KWallet on Linux) and never written to the database or to logs.
- An API wallet can place and cancel orders for the account but cannot withdraw. TradeLab never
  asks for, or accepts, the account's own private key.

Installs configured the old way, with HYPERLIQUID_* variables in backend/.env, keep working: when
HYPERLIQUID_ENABLED=true and HYPERLIQUID_WALLET_ADDRESS are set, they win, and the settings screen
shows the connection as managed by .env.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Optional

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

import storage

NETWORKS = ("mainnet", "testnet")
DEFAULT_NETWORK = "mainnet"

ACCOUNT_SETTING = "hyperliquid_account"
NETWORK_SETTING = "hyperliquid_network"

KEYCHAIN_SERVICE = "TradeLab"
KEYCHAIN_ITEM = "hyperliquid-api-wallet"

_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
_PRIVATE_KEY = re.compile(r"(0x)?[0-9a-fA-F]{64}")


class ConnectionSettingError(ValueError):
    """A connection setting was rejected; the message is safe to show to the user."""


@dataclass(frozen=True)
class Connection:
    source: str                         # "settings", "env", or "none" when no account is set
    network: str                        # "mainnet" or "testnet"
    account_address: Optional[str]      # the account TradeLab reads and trades, lowercase
    agent_key: Optional[str] = field(default=None, repr=False)  # API wallet private key

    @property
    def testnet(self) -> bool:
        return self.network == "testnet"

    @property
    def agent_address(self) -> Optional[str]:
        return agent_address_for(self.agent_key) if self.agent_key else None


def normalize_address(address: str) -> str:
    address = (address or "").strip()
    if not _ADDRESS.fullmatch(address):
        raise ConnectionSettingError("That isn't a valid address: expected 0x followed by 40 hex characters.")
    return address.lower()


def normalize_private_key(key: str) -> str:
    key = (key or "").strip()
    if not _PRIVATE_KEY.fullmatch(key):
        raise ConnectionSettingError("That isn't a valid private key: expected 64 hex characters, optionally starting with 0x.")
    return key if key.startswith("0x") else "0x" + key


def agent_address_for(private_key: str) -> str:
    import eth_account  # installed with the Hyperliquid SDK
    return eth_account.Account.from_key(private_key).address.lower()


def _env_connection() -> Optional[Connection]:
    if os.getenv("HYPERLIQUID_ENABLED", "false").lower() != "true":
        return None
    address = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "").strip()
    if not address:
        return None
    return Connection(
        source="env",
        network="testnet" if os.getenv("HYPERLIQUID_USE_TESTNET", "false").lower() == "true" else "mainnet",
        account_address=address.lower(),
        agent_key=os.getenv("HYPERLIQUID_PRIVATE_KEY", "").strip() or None,
    )


def load() -> Connection:
    env = _env_connection()
    if env:
        return env
    network = storage.get_setting(NETWORK_SETTING)
    network = network if network in NETWORKS else DEFAULT_NETWORK
    account = storage.get_setting(ACCOUNT_SETTING)
    if not account:
        return Connection(source="none", network=network, account_address=None)
    return Connection(source="settings", network=network, account_address=account, agent_key=_keychain_get())


def is_env_managed() -> bool:
    return _env_connection() is not None


def _require_settings_managed():
    if is_env_managed():
        raise ConnectionSettingError(
            "This connection is configured in backend/.env. Remove the HYPERLIQUID_* variables there "
            "to manage it from the app."
        )


def save_account(account_address: str, network: str):
    """Set the account and network. Switching either one removes the stored API wallet key, since an
    API wallet belongs to one account on one network."""
    _require_settings_managed()
    if network not in NETWORKS:
        raise ConnectionSettingError(f"Network must be one of: {', '.join(NETWORKS)}")
    account_address = normalize_address(account_address)
    current = load()
    if (current.account_address, current.network) != (account_address, network):
        delete_agent_key()
    storage.set_settings({ACCOUNT_SETTING: account_address, NETWORK_SETTING: network})


def forget():
    """Disconnect completely: remove the account, network and API wallet key."""
    _require_settings_managed()
    delete_agent_key()
    storage.set_settings({ACCOUNT_SETTING: None, NETWORK_SETTING: None})


def save_agent_key(private_key: str):
    _require_settings_managed()
    if not load().account_address:
        raise ConnectionSettingError("Connect an account before adding an API wallet.")
    try:
        keyring.set_password(KEYCHAIN_SERVICE, KEYCHAIN_ITEM, normalize_private_key(private_key))
    except KeyringError as e:
        raise ConnectionSettingError(
            f"Couldn't save the key to your system keychain ({e}). TradeLab only stores API wallet keys "
            "in the keychain; on a machine without one, set the HYPERLIQUID_* variables in backend/.env instead."
        )


def delete_agent_key():
    try:
        keyring.delete_password(KEYCHAIN_SERVICE, KEYCHAIN_ITEM)
    except PasswordDeleteError:
        pass  # nothing stored
    except KeyringError:
        pass  # no keychain, so nothing can be stored either


def _keychain_get() -> Optional[str]:
    try:
        return keyring.get_password(KEYCHAIN_SERVICE, KEYCHAIN_ITEM)
    except KeyringError:
        return None


def keychain_available() -> bool:
    try:
        keyring.get_password(KEYCHAIN_SERVICE, "availability-check")
        return True
    except KeyringError:
        return False
