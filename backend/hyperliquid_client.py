"""
Hyperliquid Exchange Client
Provides interface for real-time price data, position monitoring, and trade execution
"""

import logging
import math
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

import connection

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Hyperliquid SDK imports
try:
    from hyperliquid.info import Info
    from hyperliquid.exchange import Exchange
    from hyperliquid.utils import constants
    import eth_account
    HYPERLIQUID_AVAILABLE = True
except ImportError:
    HYPERLIQUID_AVAILABLE = False
    Info = None
    Exchange = None
    constants = None
    eth_account = None

# Perp prices may have at most 6 - szDecimals decimal places (8 - szDecimals for spot, unused here)
PERP_MAX_DECIMALS = 6
PRICE_SIG_FIGS = 5


def round_price(price: float, sz_decimals: int) -> float:
    """
    Round a price to the nearest one Hyperliquid accepts for a perp with `sz_decimals`.

    Prices may have at most 5 significant figures and at most 6 - szDecimals decimal places, but a
    whole number is always valid however many digits it has (123456 is fine, 12345.6 is not). This
    matches the SDK's own rounding, except that the SDK also cuts large whole numbers to 5 figures.
    Rounds once, to whichever limit is tighter, so the result is the nearest valid price.
    """
    if price <= 0:
        return 0.0
    if price >= 10 ** PRICE_SIG_FIGS:
        return float(round(price))
    sig_fig_decimals = PRICE_SIG_FIGS - 1 - math.floor(math.log10(price))
    return round(price, min(sig_fig_decimals, max(PERP_MAX_DECIMALS - sz_decimals, 0)))


API_URLS = {"mainnet": "https://api.hyperliquid.xyz", "testnet": "https://api.hyperliquid-testnet.xyz"}


def fetch_user_role(address: str, network: str) -> Dict:
    """
    Hyperliquid's role for an address on a network: {"role": "user" | "agent" | "subAccount" | "vault" |
    "missing", ...}. An agent (API wallet) carries data.user, its account; a sub-account carries
    data.master. "missing" means Hyperliquid has never seen the address. Raises if the lookup fails.
    """
    response = requests.post(f"{API_URLS[network]}/info", json={"type": "userRole", "user": address.lower()}, timeout=10)
    response.raise_for_status()
    role = response.json()
    if not isinstance(role, dict) or "role" not in role:
        raise ValueError(f"Unexpected userRole response: {role}")
    return role


class HyperliquidClient:
    """
    Client for Hyperliquid. It reads which account to use, and the API wallet key to sign with, from
    `connection` the first time it's needed; call reload() after either changes.

    With just an account address it is read-only (balance, positions). With an API wallet key it can
    also trade. If the account is a sub-account, orders are signed by an API wallet of its master
    account and sent on the sub-account's behalf.
    """

    # The UI polls the portfolio every second; don't send each poll to Hyperliquid
    ACCOUNT_CACHE_SECONDS = 3
    MODE_CACHE_SECONDS = 60  # the account mode only changes when the user switches it on Hyperliquid
    # Account modes (userAbstraction) whose balances live in the spot clearinghouse. In these modes,
    # Hyperliquid's docs say the perp clearinghouseState balances are "not meaningful".
    UNIFIED_MODES = {"unifiedAccount", "portfolioMargin"}

    def __init__(self):
        self._lock = threading.Lock()
        self.reload()

    def reload(self):
        """Forget the current connection and clients; the next call reconnects with the saved settings."""
        with getattr(self, "_lock", threading.Lock()):
            self._initialized = False
            self._connection: Optional[connection.Connection] = None
            self._info_client = None
            self._exchange_client = None
            self._account_role: Optional[Dict] = None
            self._account_summary: Optional[Tuple[float, Dict]] = None
            self._account_mode_cache: Optional[Tuple[float, str, str]] = None

    @property
    def connection(self) -> "connection.Connection":
        if self._connection is None:
            self._connection = connection.load()
        return self._connection

    @property
    def base_url(self) -> str:
        return API_URLS[self.connection.network]

    def _ensure_initialized(self):
        """Lazy initialization - only connect when actually needed"""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._initialized = True

            if not HYPERLIQUID_AVAILABLE:
                logger.error("Hyperliquid SDK not installed. Run: pip install hyperliquid-python-sdk")
                return

            conn = self.connection
            try:
                logger.info(f"Connecting to Hyperliquid {conn.network}...")
                self._info_client = Info(self.base_url, skip_ws=True)
            except Exception as e:
                logger.error(f"Error connecting to Hyperliquid: {e}")
                return

            if not (conn.account_address and conn.agent_key):
                logger.info("Read-only: no API wallet configured" if conn.account_address else "No account connected")
                return

            try:
                wallet = eth_account.Account.from_key(conn.agent_key)
                role = self._fetch_role(conn.account_address)
                if role.get("role") == "subAccount":
                    # A sub-account has no API wallets of its own: its master's sign on its behalf
                    self._exchange_client = Exchange(
                        wallet, self.base_url,
                        account_address=role["data"]["master"], vault_address=conn.account_address,
                    )
                else:
                    self._exchange_client = Exchange(wallet, self.base_url, account_address=conn.account_address)
                logger.info(f"Trading enabled for {conn.account_address} with API wallet {wallet.address}")
            except Exception as e:
                logger.error(f"Could not set up trading: {e}")
                self._exchange_client = None

    @property
    def enabled(self) -> bool:
        """An account is connected (read-only at least)."""
        return HYPERLIQUID_AVAILABLE and bool(self.connection.account_address)

    @property
    def can_trade(self) -> bool:
        return self.exchange_client is not None

    @property
    def wallet_address(self) -> Optional[str]:
        return self.connection.account_address

    @property
    def use_testnet(self) -> bool:
        return self.connection.testnet

    @property
    def info_client(self):
        self._ensure_initialized()
        return self._info_client

    @property
    def exchange_client(self):
        self._ensure_initialized()
        return self._exchange_client

    def _fetch_role(self, address: str) -> Dict:
        """fetch_user_role on the connected network, cached for the connected account until reload()."""
        if address == self.connection.account_address and self._account_role is not None:
            return self._account_role
        role = fetch_user_role(address, self.connection.network)
        if address == self.connection.account_address:
            self._account_role = role
        return role

    def _info(self, request: Dict):
        response = requests.post(f"{self.base_url}/info", json=request, timeout=10)
        response.raise_for_status()
        return response.json()

    def _account_mode(self, address: str) -> str:
        """The account's mode (userAbstraction): "unifiedAccount", "portfolioMargin", "disabled",
        "default" or "dexAbstraction". Cached for a minute."""
        cached = self._account_mode_cache
        if cached and cached[1] == address and time.monotonic() - cached[0] < self.MODE_CACHE_SECONDS:
            return cached[2]
        mode = self._info({"type": "userAbstraction", "user": address})
        if not isinstance(mode, str):
            raise ValueError(f"Unexpected userAbstraction response: {mode}")
        self._account_mode_cache = (time.monotonic(), address, mode)
        return mode

    def get_account_summary(self) -> Dict:
        """
        The connected account's trading balance: account_value (equity, including unrealized P&L),
        withdrawable and margin_used, in USD, plus account_mode. Cached for a few seconds. Raises if
        it can't be fetched.

        - Standard accounts keep perp collateral in the perp clearinghouse, whose accountValue is the
          equity.
        - Unified and portfolio-margin accounts keep USDC in the spot balance, which collateralizes perps
          directly. Its total already moves with open positions' unrealized P&L (observed on a live
          position: total minus unrealizedPnl stayed constant as the price moved), so it is the equity.
          Other collateral tokens (portfolio margin) aren't counted.
        """
        cached = self._account_summary
        if cached and time.monotonic() - cached[0] < self.ACCOUNT_CACHE_SECONDS:
            return cached[1]
        address = self.connection.account_address
        if not address:
            raise ValueError("No Hyperliquid account connected")
        mode = self._account_mode(address)
        if mode in self.UNIFIED_MODES:
            spot = self._info({"type": "spotClearinghouseState", "user": address})
            usdc = next((b for b in spot.get("balances", []) if b.get("coin") == "USDC"), None)
            total = float(usdc["total"]) if usdc else 0.0
            hold = float(usdc["hold"]) if usdc else 0.0
            available = dict(spot.get("tokenToAvailableAfterMaintenance") or []).get(0)
            summary = {
                "account_value": total,
                "withdrawable": float(available) if available is not None else max(total - hold, 0.0),
                "margin_used": hold,
            }
        else:
            perp = self._info({"type": "clearinghouseState", "user": address})
            margin = perp["marginSummary"]
            summary = {
                "account_value": float(margin["accountValue"]),
                "withdrawable": float(perp["withdrawable"]),
                "margin_used": float(margin["totalMarginUsed"]),
            }
        summary["account_mode"] = mode
        summary["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._account_summary = (time.monotonic(), summary)
        return summary

    def last_account_summary(self) -> Optional[Dict]:
        """The most recent successful get_account_summary(), however old, or None."""
        return self._account_summary[1] if self._account_summary else None

    def submit_signed_action(self, action: Dict, signature: Dict, nonce: int) -> Dict:
        """Send an action signed elsewhere (e.g. by the user's browser wallet) to /exchange."""
        payload = {"action": action, "nonce": nonce, "signature": signature, "vaultAddress": None, "expiresAfter": None}
        response = requests.post(f"{self.base_url}/exchange", json=payload, timeout=10)
        response.raise_for_status()
        return response.json()

    def get_current_price(self, coin: str = "BTC") -> Optional[float]:
        """Get the current mid price from Hyperliquid's public REST API."""
        try:
            response = requests.post(
                f"{self.base_url}/info",
                json={"type": "allMids"},
                timeout=10,
            )
            response.raise_for_status()
            all_mids = response.json()

            if not isinstance(all_mids, dict):
                logger.error(f"Unexpected response format from Hyperliquid API: {type(all_mids)}")
                return None

            price = all_mids.get(coin.upper())
            return float(price) if price is not None else None
        except Exception as e:
            logger.error(f"Error getting price for {coin}: {e}")
            return None
    
    def get_asset_metadata(self) -> Optional[Dict]:
        """Get asset metadata including max leverage from Hyperliquid"""
        self._ensure_initialized()
        
        if not self._info_client:
            return None
        
        try:
            meta = self._info_client.meta()
            if not meta:
                return None
            
            # The meta response is a list with universe data
            # Structure: [[universe_data, market_data], ...]
            if isinstance(meta, list) and len(meta) > 0:
                # Get the first perp dex data
                first_dex = meta[0]
                if isinstance(first_dex, list) and len(first_dex) > 0:
                    universe_data = first_dex[0]
                    universe = universe_data.get('universe', [])
                else:
                    universe = []
            else:
                universe = meta.get('universe', []) if isinstance(meta, dict) else []
            
            asset_data = {}
            for asset in universe:
                name = asset.get('name', '')
                if name:
                    asset_data[name] = {
                        'max_leverage': asset.get('maxLeverage', 0),
                        'sz_decimals': asset.get('szDecimals', 0),
                        'only_isolated': asset.get('onlyIsolated', False)
                    }
            
            return asset_data
        except Exception as e:
            logger.error(f"Error getting asset metadata: {e}")
            return None
    
    def get_positions(self, coin: Optional[str] = None) -> List[Dict]:
        """Get open positions"""
        self._ensure_initialized()
        
        if not self._info_client:
            logger.error("get_positions: Info client not initialized")
            return []
        
        address = self.connection.account_address
        if not address:
            logger.error("get_positions: no account connected")
            return []
        
        try:
            logger.debug(f"Fetching user_state for wallet: {address}")
            user_state = self._info_client.user_state(address)
            logger.debug(f"user_state response: {user_state}")
            
            if not user_state:
                logger.error("user_state is None")
                return []
            
            if 'assetPositions' not in user_state:
                logger.error(f"'assetPositions' not in user_state. Keys: {user_state.keys()}")
                return []
            
            asset_positions = user_state.get('assetPositions', [])
            logger.debug(f"assetPositions count: {len(asset_positions)}")
            logger.debug(f"assetPositions: {asset_positions}")
            
            positions = []
            for pos_data in asset_positions:
                position = pos_data.get('position', {})
                logger.debug(f"Processing position: {position}")
                
                if coin and position.get('coin') != coin:
                    logger.debug(f"Skipping position, coin mismatch: {position.get('coin')} != {coin}")
                    continue
                
                positions.append({
                    'coin': position.get('coin'),
                    'size': float(position.get('szi', 0)),
                    'entry_price': float(position.get('entryPx', 0)),
                    'position_value': float(position.get('positionValue', 0)),
                    'unrealized_pnl': float(position.get('unrealizedPnl', 0)),
                    'liquidation_price': float(position.get('liquidationPx', 0)) if position.get('liquidationPx') else None,
                    'margin_used': float(position.get('marginUsed', 0)),
                    'max_leverage': float(position.get('maxLeverage', 0))
                })
            
            logger.debug(f"Returning {len(positions)} positions")
            return positions
            
        except Exception as e:
            logger.exception(f"Error getting positions: {e}")
            return []
    
    def place_stop_order(self, coin: str, is_buy: bool, size: float, trigger_price: float, is_long_position: bool) -> Dict:
        """Place a reduce-only stop-market order. `trigger_price` must already be a valid price (see round_price)."""
        self._ensure_initialized()
        
        if not self._exchange_client:
            return {"status": "error", "message": "Exchange client not configured"}
        
        try:
            # A long's stop sells when the price falls to the trigger; a short's buys when it rises to it.
            # isMarket fills at market once triggered. The SDK still requires a limit price, so the
            # trigger price is used, and must already be valid (see round_price).
            trigger_order_type = {"trigger": {"triggerPx": trigger_price, "tpsl": "sl", "isMarket": True}}
            logger.debug(f"Stop order: coin={coin}, is_buy={not is_long_position}, size={size}, trigger_price={trigger_price}")

            result = self._exchange_client.order(
                name=coin,
                is_buy=not is_long_position,  # Close position
                sz=size,
                limit_px=trigger_price,
                order_type=trigger_order_type,
                reduce_only=True,
                cloid=None
            )
            
            logger.debug(f"Order result: {result}")
            return result
            
        except Exception as e:
            logger.exception(f"Error placing stop order: {e}")
            return {"status": "error", "message": str(e)}

    def market_close(self, coin: str, sz: Optional[float] = None) -> Dict:
        """Close `sz` units of the position in `coin` via market order, or all of it when `sz` is None"""
        self._ensure_initialized()

        if not self._exchange_client:
            return {"status": "error", "message": "Exchange client not configured"}

        try:
            result = self._exchange_client.market_close(coin, sz=sz)
            return result
        except Exception as e:
            logger.exception(f"Error closing position for {coin}: {e}")
            return {"status": "error", "message": str(e)}


# Global client instance - created but not initialized until first use
hl_client = HyperliquidClient()
