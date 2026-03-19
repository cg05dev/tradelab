"""
Hyperliquid Exchange Client
Provides interface for real-time price data, position monitoring, and trade execution
"""

import os
import json
import requests
from typing import Optional, Dict, List
from datetime import datetime
from dotenv import load_dotenv

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
            print("[ERROR] Hyperliquid SDK not installed. Run: pip install hyperliquid-python-sdk")
            self._enabled = False
            self._initialized = True
            return
        
        if not self._enabled:
            print("[INFO] Hyperliquid integration disabled (set HYPERLIQUID_ENABLED=true in .env)")
            self._initialized = True
            return
        
        try:
            # API URLs
            base_url = constants.TESTNET_API_URL if self._use_testnet else constants.MAINNET_API_URL
            
            # Validate that we got a proper URL, not something else
            if not base_url or not isinstance(base_url, str) or not base_url.startswith('http'):
                print(f"[ERROR] Invalid Hyperliquid API URL: {base_url}")
                self._enabled = False
                self._initialized = True
                return
            
            # Initialize Info client (read-only, no auth needed)
            print(f"Connecting to Hyperliquid {'Testnet' if self._use_testnet else 'Mainnet'}...")
            self._info_client = Info(base_url, skip_ws=True)
            print("[OK] Info client connected")
            
            # Initialize Exchange client only if credentials are provided
            if self._wallet_address and self._private_key:
                # Create wallet from private key (required by SDK)
                wallet = eth_account.Account.from_key(self._private_key)
                derived_address = wallet.address
                env_address = self._wallet_address
                
                print(f"[DEBUG] ENV wallet address: {env_address}")
                print(f"[DEBUG] Derived wallet address from private key: {derived_address}")
                print(f"[DEBUG] Addresses match: {env_address.lower() == derived_address.lower()}")
                
                # Use checksum address from wallet object (not the raw env var)
                self._wallet_address = derived_address
                self._exchange_client = Exchange(
                    wallet,  # First param: wallet object
                    base_url,  # Second param: base URL
                    account_address=self._wallet_address  # Keyword arg
                )
                print(f"[OK] Exchange client connected for {self._wallet_address[:10]}...")
                print(f"[INFO] Using checksum address: {self._wallet_address}")
            else:
                print("[INFO] Info client only (no trading credentials provided)")
            
            self._initialized = True
                
        except Exception as e:
            print(f"[ERROR] Error connecting to Hyperliquid: {e}")
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
        """Get current price for a coin via REST API"""
        self._ensure_initialized()
        
        if not self._info_client:
            return None
        
        try:
            all_mids = self._info_client.all_mids()
            
            # Handle case where all_mids returns an error or empty response
            if not all_mids:
                return None
            
            # Handle dict format: {"BTC": "45000.5", "ETH": "3200.1", ...}
            if isinstance(all_mids, dict):
                price = all_mids.get(coin)
                if price:
                    return float(price)
                return None
            
            # Handle list format (legacy): [{"coin": "BTC", "mid": "45000.5"}, ...]
            if isinstance(all_mids, list):
                for mid in all_mids:
                    if isinstance(mid, dict) and mid.get('coin') == coin:
                        return float(mid.get('mid', 0))
                return None
            
            print(f"[ERROR] Unexpected response format from Hyperliquid API: {type(all_mids)}")
            return None
        except Exception as e:
            print(f"[ERROR] Error getting price for {coin}: {e}")
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
            print(f"[ERROR] Error getting asset metadata: {e}")
            return None
    
    def get_positions(self, coin: Optional[str] = None) -> List[Dict]:
        """Get open positions"""
        self._ensure_initialized()
        
        if not self._info_client:
            print("[ERROR] get_positions: Info client not initialized")
            return []
        
        if not self._wallet_address:
            print("[ERROR] get_positions: Wallet address not set")
            return []
        
        try:
            print(f"[DEBUG] Fetching user_state for wallet: {self._wallet_address}")
            user_state = self._info_client.user_state(self._wallet_address)
            print(f"[DEBUG] user_state response: {user_state}")
            
            if not user_state:
                print("[ERROR] user_state is None")
                return []
            
            if 'assetPositions' not in user_state:
                print(f"[ERROR] 'assetPositions' not in user_state. Keys: {user_state.keys()}")
                return []
            
            asset_positions = user_state.get('assetPositions', [])
            print(f"[DEBUG] assetPositions count: {len(asset_positions)}")
            print(f"[DEBUG] assetPositions: {asset_positions}")
            
            positions = []
            for pos_data in asset_positions:
                position = pos_data.get('position', {})
                print(f"[DEBUG] Processing position: {position}")
                
                if coin and position.get('coin') != coin:
                    print(f"[DEBUG] Skipping position, coin mismatch: {position.get('coin')} != {coin}")
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
            
            print(f"[DEBUG] Returning {len(positions)} positions")
            return positions
            
        except Exception as e:
            print(f"[ERROR] Error getting positions: {e}")
            import traceback
            traceback.print_exc()
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
            
            print(f"[DEBUG] trigger_order_type: {trigger_order_type}")
            print(f"[DEBUG] Order parameters: coin={coin}, is_buy={not is_long_position}, size={size}, trigger_price={trigger_price}")
            
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
            
            print(f"[DEBUG] Order result: {result}")
            return result
            
        except Exception as e:
            print(f"[ERROR] Error placing stop order: {e}")
            import traceback
            traceback.print_exc()
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
            print(f"[ERROR] Error closing position for {coin}: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "message": str(e)}


# Global client instance - created but not initialized until first use
hl_client = HyperliquidClient()
