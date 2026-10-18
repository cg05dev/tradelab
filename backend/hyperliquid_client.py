"""
Hyperliquid Exchange Client
Provides interface for real-time price data, position monitoring, and trade execution
"""

import logging
import os
import json
import requests
from typing import Optional, Dict, List
from datetime import datetime
from dotenv import load_dotenv

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


class HyperliquidClient:
    """Client for interacting with Hyperliquid exchange - Lazy initialization"""
    
    def __init__(self):
        self._initialized = False
        self._enabled = os.getenv('HYPERLIQUID_ENABLED', 'false').lower() == 'true'
        self._wallet_address = os.getenv('HYPERLIQUID_WALLET_ADDRESS', '')
        self._private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY', '')
        self._use_testnet = os.getenv('HYPERLIQUID_USE_TESTNET', 'false').lower() == 'true'
        
        # Clients - initialized lazily
        self._info_client = None
        self._exchange_client = None
    
    def _ensure_initialized(self):
        """Lazy initialization - only connect when actually needed"""
        if self._initialized:
            return
        
        if not HYPERLIQUID_AVAILABLE:
            logger.error("Hyperliquid SDK not installed. Run: pip install hyperliquid-python-sdk")
            self._enabled = False
            self._initialized = True
            return
        
        if not self._enabled:
            logger.info("Hyperliquid integration disabled (set HYPERLIQUID_ENABLED=true in .env)")
            self._initialized = True
            return
        
        try:
            # API URLs
            base_url = constants.TESTNET_API_URL if self._use_testnet else constants.MAINNET_API_URL
            
            # Validate that we got a proper URL, not something else
            if not base_url or not isinstance(base_url, str) or not base_url.startswith('http'):
                logger.error(f"Invalid Hyperliquid API URL: {base_url}")
                self._enabled = False
                self._initialized = True
                return
            
            # Initialize Info client (read-only, no auth needed)
            logger.info(f"Connecting to Hyperliquid {'Testnet' if self._use_testnet else 'Mainnet'}...")
            self._info_client = Info(base_url, skip_ws=True)
            logger.info("Info client connected")
            
            # Initialize Exchange client only if credentials are provided
            if self._wallet_address and self._private_key:
                # Create wallet from private key (required by SDK)
                wallet = eth_account.Account.from_key(self._private_key)
                self._signer_address = wallet.address  # Address derived from private key (for signing)
                # self._wallet_address remains the ENV value (main account to trade on behalf of)
                
                logger.debug(f"Main wallet address (from ENV): {self._wallet_address}")
                logger.debug(f"Signer address (derived from key): {self._signer_address}")
                logger.debug(f"Addresses match: {self._wallet_address.lower() == self._signer_address.lower()}")
                
                self._exchange_client = Exchange(
                    wallet,  # First param: wallet object (for signing)
                    base_url,  # Second param: base URL
                    account_address=self._wallet_address  # Keyword arg: main account to trade on behalf of
                )
                logger.info(f"Exchange client connected for {self._wallet_address[:10]}...")
                logger.info(f"Trading on behalf of: {self._wallet_address}")
            else:
                logger.info("Info client only (no trading credentials provided)")
            
            self._initialized = True
                
        except Exception as e:
            logger.error(f"Error connecting to Hyperliquid: {e}")
            self._enabled = False
            self._info_client = None
            self._exchange_client = None
            self._initialized = True
    
    @property
    def enabled(self):
        return self._enabled
    
    @property
    def wallet_address(self):
        return self._wallet_address
    
    @property
    def use_testnet(self):
        return self._use_testnet
    
    @property
    def info_client(self):
        self._ensure_initialized()
        return self._info_client
    
    @property
    def exchange_client(self):
        self._ensure_initialized()
        return self._exchange_client
    
    def get_current_price(self, coin: str = "BTC") -> Optional[float]:
        """Get the current mid price from Hyperliquid's public REST API."""
        try:
            base_url = constants.TESTNET_API_URL if self._use_testnet else constants.MAINNET_API_URL
            response = requests.post(
                f"{base_url}/info",
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
        
        if not self._wallet_address:
            logger.error("get_positions: Wallet address not set")
            return []
        
        try:
            logger.debug(f"Fetching user_state for wallet: {self._wallet_address}")
            user_state = self._info_client.user_state(self._wallet_address)
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
        """Place a stop order via direct API call"""
        self._ensure_initialized()
        
        if not self._exchange_client or not self._wallet_address or not self._private_key:
            return {"status": "error", "message": "Exchange client not configured"}
        
        try:
            # For a stop order, we need:
            # - If long position and SL: trigger when price <= SL, sell
            # - If short position and SL: trigger when price >= SL, buy
            
            # Create wallet for signing
            wallet = eth_account.Account.from_key(self._private_key)
            
            # Get current timestamp
            timestamp = int(datetime.now().timestamp() * 1000)
            
            # Build the order request
            # Stop order as trigger + market close
            order_request = {
                "action": {
                    "type": "order",
                    "orders": [
                        {
                            "coin": coin,
                            "isBuy": not is_long_position,  # Opposite to close position
                            "sz": str(size),
                            "limitPx": "0",  # Market order
                            "orderType": {"trigger": {"triggerPx": str(trigger_price), "tpsl": "sl"}},
                            "reduceOnly": True
                        }
                    ],
                    "grouping": "na",
                    "builder": None
                },
                "nonce": timestamp,
                "signature": None  # Will be signed below
            }
            
            # Sign the request (simplified - SDK should handle this)
            # For now, use the SDK's order method but with trigger type
            # Actually, let's try using the SDK with a special order type
            
            # Try using exchange client's ability to place trigger orders
            # Trigger orders in Hyperliquid use "trigger" order type
            # Must include isMarket field
            trigger_order_type = {"trigger": {"triggerPx": trigger_price, "tpsl": "sl", "isMarket": True}}
            
            logger.debug(f"trigger_order_type: {trigger_order_type}")
            logger.debug(f"Order parameters: coin={coin}, is_buy={not is_long_position}, size={size}, trigger_price={trigger_price}")
            
            # For trigger orders, we need a valid limit price (not 0)
            # Use the trigger price as the limit price
            limit_px = round(trigger_price, 0)
            
            result = self._exchange_client.order(
                name=coin,
                is_buy=not is_long_position,  # Close position
                sz=size,
                limit_px=limit_px,  # Valid price for the order
                order_type=trigger_order_type,
                reduce_only=True,
                cloid=None
            )
            
            logger.debug(f"Order result: {result}")
            return result
            
        except Exception as e:
            logger.exception(f"Error placing stop order: {e}")
            return {"status": "error", "message": str(e)}

    def market_close(self, coin: str) -> Dict:
        """Close all positions for a given coin via market order"""
        self._ensure_initialized()

        if not self._exchange_client or not self._wallet_address or not self._private_key:
            return {"status": "error", "message": "Exchange client not configured"}

        try:
            result = self._exchange_client.market_close(coin)
            return result
        except Exception as e:
            logger.exception(f"Error closing position for {coin}: {e}")
            return {"status": "error", "message": str(e)}


# Global client instance - created but not initialized until first use
hl_client = HyperliquidClient()
