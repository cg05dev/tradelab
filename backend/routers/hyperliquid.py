"""Hyperliquid exchange integration: market data, positions and live order execution."""

import time
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from storage import load_mode

try:
    from hyperliquid_client import hl_client
except ImportError:
    hl_client = None

router = APIRouter(prefix="/api/hyperliquid", tags=["hyperliquid"])


def check_execution_allowed():
    """Check if execution is allowed based on current mode. Raises 403 if blocked."""
    mode = load_mode()
    if mode != "live":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "mode_blocked",
                "mode": mode,
                "reason": "Execution endpoints are blocked in paper mode. Switch to live mode to execute trades."
            }
        )

@router.get("/status")
def get_hyperliquid_status():
    """Get Hyperliquid integration status"""
    if not hl_client:
        return {"enabled": False, "connected": False, "message": "Hyperliquid client not available"}
    
    return {
        "enabled": hl_client.enabled,
        "connected": hl_client.info_client is not None,
        "testnet": hl_client.use_testnet if hl_client.enabled else None,
        "wallet_address": hl_client.wallet_address if hl_client.enabled else None
    }

@router.get("/price/{coin}")
def get_hyperliquid_price(coin: str):
    """Get current price for a coin"""
    if not hl_client:
        raise HTTPException(status_code=503, detail="Hyperliquid client not available")
    
    price = hl_client.get_current_price(coin.upper())
    if price is None:
        raise HTTPException(status_code=404, detail=f"Price not available for {coin}")
    
    return {"coin": coin.upper(), "price": price, "timestamp": datetime.now().isoformat()}

@router.get("/positions")
def get_hyperliquid_positions(coin: Optional[str] = None):
    """Get open positions from Hyperliquid"""
    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="Hyperliquid integration not enabled")
    
    if not hl_client.wallet_address:
        raise HTTPException(status_code=400, detail="Wallet address not configured")
    
    positions = hl_client.get_positions(coin.upper() if coin else None)
    return {"positions": positions, "count": len(positions)}

@router.get("/assets")
def get_hyperliquid_assets():
    """Get available assets and their max leverage from Hyperliquid"""
    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="Hyperliquid integration not enabled")
    
    asset_data = hl_client.get_asset_metadata()
    if asset_data is None:
        raise HTTPException(status_code=500, detail="Failed to fetch asset metadata")
    
    # Format for frontend
    assets = []
    for name, data in asset_data.items():
        assets.append({
            "symbol": name,
            "max_leverage": data["max_leverage"],
            "sz_decimals": data["sz_decimals"],
            "only_isolated": data["only_isolated"]
        })
    
    return {"assets": assets, "count": len(assets)}

class HyperliquidOrderRequest(BaseModel):
    coin: str
    is_buy: bool
    margin_amount: float  # Margin in USD
    leverage: int
    entry_price: float
    take_profits: Optional[List[Dict]] = []  # List of {price: float, allocation: float}
    stop_losses: Optional[List[Dict]] = []    # List of {price: float, allocation: float}
    is_isolated: bool = True

@router.post("/order")
def place_hyperliquid_order(request: HyperliquidOrderRequest):
    """Place a market order on Hyperliquid with built-in TP/SL"""
    # Check if execution is allowed in current mode
    check_execution_allowed()
    
    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="Hyperliquid integration not enabled")
    
    if not hl_client.exchange_client:
        raise HTTPException(status_code=400, detail="Exchange client not configured - check wallet credentials")
    
    try:
        # Get current real-time price from Hyperliquid
        current_price = hl_client.get_current_price(request.coin)
        if current_price is None:
            raise HTTPException(status_code=400, detail="Could not fetch current market price. Please try again.")
        
        print(f"[DEBUG] Using real-time price: {current_price} (frontend sent: {request.entry_price})")
        
        # Get asset metadata for szDecimals
        asset_data = hl_client.get_asset_metadata()
        sz_decimals = 5  # Default for most assets
        if asset_data and request.coin in asset_data:
            sz_decimals = asset_data[request.coin].get('sz_decimals', 5)
        
        # Calculate position size in coin units using real-time price
        # Position Size = (Margin × Leverage) / Current Price
        position_size_units = (request.margin_amount * request.leverage) / current_price
        
        # Round to the correct number of decimals for this asset
        position_size_units = round(position_size_units, sz_decimals)
        
        print(f"Order: {request.coin} | Size: {position_size_units} | Leverage: {request.leverage}x | Margin: ${request.margin_amount:.2f}")
        
        # Place market order
        # For market orders, we use the current price as limitPx with a small buffer
        print(f"[DEBUG] is_buy={request.is_buy}, direction={'BUY' if request.is_buy else 'SELL'}")
        limit_px = current_price * (1.002 if request.is_buy else 0.998)  # 0.2% buffer for market execution
        
        # Round price to valid tick size (whole dollars for BTC)
        limit_px = round(limit_px, 0)
        
        print(f"Sending order: {request.coin} @ {limit_px} (size: {position_size_units})")
        
        # Prepare order type
        order_type = {"limit": {"tif": "Ioc"}}  # Immediate-or-Cancel for market-like execution
        
        # Get first TP and SL prices from request
        tp_price = None
        sl_price = None
        
        print(f"[DEBUG] Received TPs: {request.take_profits}")
        print(f"[DEBUG] Received SLs: {request.stop_losses}")
        
        if request.take_profits and len(request.take_profits) > 0:
            tp_price = round(request.take_profits[0].get("price", 0), 0)
            print(f"[DEBUG] TP price extracted: {tp_price}")
            if tp_price <= 0:
                tp_price = None
        
        if request.stop_losses and len(request.stop_losses) > 0:
            sl_price = round(request.stop_losses[0].get("price", 0), 0)
            print(f"[DEBUG] SL price extracted: {sl_price}")
            if sl_price <= 0:
                sl_price = None
        
        # Set leverage BEFORE placing the order (per-coin setting)
        # Note: is_cross=True for cross margin, is_cross=False for isolated
        try:
            is_cross = not request.is_isolated  # is_isolated=True means NOT cross
            hl_client.exchange_client.update_leverage(request.leverage, request.coin, is_cross)
            margin_mode = "Cross" if is_cross else "Isolated"
            print(f"[DEBUG] Set leverage to {request.leverage}x ({margin_mode}) for {request.coin}")
        except Exception as e:
            print(f"[WARNING] Could not set leverage: {e}")
        
        # Place the main order
        result = hl_client.exchange_client.order(
            name=request.coin,
            is_buy=request.is_buy,
            sz=position_size_units,
            limit_px=limit_px,
            order_type=order_type,
            reduce_only=False,
            cloid=None
        )
        
        print(f"[DEBUG] Order result: {result}")
        
        # Check for errors in the response
        if result and result.get("status") == "ok":
            statuses = result.get("response", {}).get("data", {}).get("statuses", [])
            if statuses and len(statuses) > 0:
                if "error" in statuses[0]:
                    error_msg = statuses[0]["error"]
                    raise HTTPException(status_code=400, detail=f"Order failed: {error_msg}")
        
        # Check if order was successful
        if result and result.get("status") == "ok":
            # Place Take Profit orders
            if request.take_profits and len(request.take_profits) > 0:
                print(f"[DEBUG] Placing {len(request.take_profits)} Take Profit order(s)")
                for tp in request.take_profits:
                    try:
                        tp_price = round(tp.get("price", 0), 0)
                        allocation = tp.get("allocation", 0)
                        if tp_price <= 0 or allocation <= 0:
                            print(f"[WARNING] Skipping TP order - invalid price: {tp_price}, allocation: {allocation}")
                            continue
                        
                        tp_size = round(position_size_units * allocation, sz_decimals)
                        if tp_size <= 0:
                            print(f"[WARNING] TP size too small: {tp_size}, skipping")
                            continue
                        
                        tp_result = hl_client.exchange_client.order(
                            name=request.coin,
                            is_buy=not request.is_buy,
                            sz=tp_size,
                            limit_px=tp_price,
                            order_type={"limit": {"tif": "Gtc"}},
                            reduce_only=True,
                            cloid=None
                        )
                        print(f"[DEBUG] TP order result: {tp_result}")
                    except Exception as e:
                        print(f"[WARNING] Failed to place TP order: {e}")
            
            # Place Stop Loss orders using Hyperliquid trigger orders
            if request.stop_losses and len(request.stop_losses) > 0:
                print(f"[DEBUG] Placing {len(request.stop_losses)} Stop Loss trigger order(s)")
                for sl in request.stop_losses:
                    try:
                        sl_price = round(sl.get("price", 0), 0)
                        allocation = sl.get("allocation", 1.0)
                        if sl_price <= 0 or allocation <= 0:
                            print(f"[WARNING] Skipping SL - invalid price: {sl_price}, allocation: {allocation}")
                            continue
                        
                        # Calculate size to close
                        sl_size = round(position_size_units * allocation, sz_decimals)
                        if sl_size <= 0:
                            print(f"[WARNING] SL size too small: {sl_size}, skipping")
                            continue
                        
                        # Place stop order using the new method
                        sl_result = hl_client.place_stop_order(
                            coin=request.coin,
                            is_buy=request.is_buy,
                            size=sl_size,
                            trigger_price=sl_price,
                            is_long_position=request.is_buy  # is_buy=True means long
                        )
                        print(f"[DEBUG] SL order result: {sl_result}")
                    except Exception as e:
                        print(f"[WARNING] Failed to place SL order: {e}")
            
            return {
                "status": "success",
                "order_id": result.get("response", {}).get("data", {}).get("statuses", [{}])[0].get("resting", {}).get("oid", "unknown"),
                "position_size": position_size_units,
                "margin_used": request.margin_amount,
                "leverage": request.leverage,
                "message": f"Order placed: {position_size_units:.6f} {request.coin} at {request.leverage}x leverage"
            }
        else:
            error_msg = result.get("response", "Unknown error") if result else "No response"
            raise HTTPException(status_code=400, detail=f"Order failed: {error_msg}")
            
    except Exception as e:
        print(f"[ERROR] Error placing order: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error placing order: {str(e)}")

latest_btc_price = {"price": None, "timestamp": None}

@router.get("/ws-price")
def get_ws_price():
    """Get latest BTC price from WebSocket feed"""
    if not hl_client or not hl_client.enabled:
        raise HTTPException(status_code=503, detail="Hyperliquid integration not enabled")
    
    # For now, return REST API price (WebSocket will be implemented next)
    price = hl_client.get_current_price("BTC")
    if price:
        latest_btc_price["price"] = price
        latest_btc_price["timestamp"] = datetime.now().isoformat()
    
    return latest_btc_price

@router.post("/close/{coin}")
def close_hyperliquid_position(coin: str):
    """Close all positions for a given coin via market order and return fill price"""
    # Check if execution is allowed in current mode
    check_execution_allowed()
    
    if not hl_client:
        raise HTTPException(status_code=503, detail="Hyperliquid client not initialized")
    
    # Ensure client is initialized
    hl_client._ensure_initialized()
    
    if not hl_client.enabled:
        raise HTTPException(status_code=503, detail="Hyperliquid integration not enabled")

    if not hl_client.exchange_client:
        raise HTTPException(status_code=400, detail="Exchange client not configured - check wallet credentials")

    try:
        coin = coin.upper()
        
        print(f"[DEBUG] Wallet address being used: {hl_client.wallet_address}")
        
        # Debug: Get all positions to see what's available
        all_positions = hl_client.get_positions(None)
        print(f"[DEBUG] All positions: {all_positions}")
        
        # Check for specific position
        positions = hl_client.get_positions(coin)
        print(f"[DEBUG] Positions for {coin}: {positions}")
        
        if not positions or len(positions) == 0:
            # If no position found, check if maybe the coin format is different
            # Try to find matching position
            for pos in all_positions:
                pos_coin = pos.get('coin', '')
                if coin in pos_coin or pos_coin in coin:
                    print(f"[INFO] Found position with coin '{pos_coin}' matching '{coin}'")
                    # Use the actual coin name from Hyperliquid
                    coin = pos_coin
                    positions = [pos]
                    break
            
            if not positions or len(positions) == 0:
                # List available positions in error message
                available_coins = [p.get('coin') for p in all_positions]
                raise HTTPException(
                    status_code=400, 
                    detail=f"No open position found for {coin}. Available positions: {available_coins}"
                )
        
        position = positions[0]
        actual_coin = position.get('coin', coin)
        print(f"[INFO] Closing position for {actual_coin}: size={position.get('size')}, entry=${position.get('entry_price')}")
        
        # Close the position using the actual coin name from Hyperliquid
        result = hl_client.market_close(actual_coin)
        print(f"[DEBUG] market_close result: {result}")
        
        # Wait 2 seconds for the order to be processed
        print(f"[DEBUG] Waiting 2 seconds for position close to be confirmed...")
        time.sleep(2)
        
        # Verify position was actually closed by checking again
        print(f"[DEBUG] Checking if position was actually closed...")
        positions_after = hl_client.get_positions(actual_coin)
        print(f"[DEBUG] Positions after market_close: {positions_after}")
        
        # If position still exists, try alternative close method using market order
        if positions_after and len(positions_after) > 0:
            print(f"[WARN] Position still exists after market_close! Trying alternative close method...")
            
            # Get current position details
            remaining_position = positions_after[0]
            remaining_size = remaining_position.get('size', 0)
            position_direction = remaining_position.get('direction', 'long')
            
            print(f"[DEBUG] Remaining position: size={remaining_size}, direction={position_direction}")
            
            # Get current market price for the opposite trade
            current_price = hl_client.get_current_price(actual_coin)
            
            if current_price and remaining_size > 0:
                # Determine if we need to buy or sell to close
                # If position is long (size > 0), we need to sell (is_buy=False)
                # If position is short (size < 0), we need to buy (is_buy=True)
                is_buy_to_close = position_direction == 'short'
                
                print(f"[DEBUG] Attempting alternative close: is_buy={is_buy_to_close}, size={abs(remaining_size)}, price={current_price}")
                
                # Place a market order to close the remaining position
                try:
                    alt_result = hl_client.exchange_client.order(
                        name=actual_coin,
                        is_buy=is_buy_to_close,
                        sz=abs(remaining_size),
                        limit_px=round(current_price * (1.002 if is_buy_to_close else 0.998), 0),  # Small buffer
                        order_type={"limit": {"tif": "Ioc"}},  # Immediate-or-Cancel
                        reduce_only=True,
                        cloid=None
                    )
                    print(f"[DEBUG] Alternative close result: {alt_result}")
                    
                    # Wait another 2 seconds and verify again
                    time.sleep(2)
                    positions_final = hl_client.get_positions(actual_coin)
                    print(f"[DEBUG] Positions after alternative close: {positions_final}")
                    
                    if positions_final and len(positions_final) > 0:
                        print(f"[ERROR] Position STILL exists after alternative close attempt!")
                    else:
                        print(f"[INFO] Alternative close succeeded - position is now closed")
                        # Update result to show success
                        result = alt_result
                except Exception as alt_error:
                    print(f"[ERROR] Alternative close method failed: {alt_error}")
                    import traceback
                    traceback.print_exc()
        else:
            print(f"[INFO] Position successfully closed with market_close method")
        
        if result and result.get("status") == "error":
            error_msg = result.get("message", "Unknown error")
            raise HTTPException(status_code=400, detail=f"Close position failed: {error_msg}")
        
        # Parse the fill price from the response
        fill_price = None
        statuses = []
        print(f"[DEBUG] Full result structure: {result}")
        
        if result and result.get("status") == "ok":
            # Try to get filled price from response - multiple possible formats
            response_data = result.get("response", {})
            print(f"[DEBUG] Response data: {response_data}")
            
            # Try format 1: response.data.statuses[0].filled.avgPx
            if isinstance(response_data, dict):
                data = response_data.get("data", {})
                statuses = data.get("statuses", [])
                if statuses and len(statuses) > 0:
                    filled_data = statuses[0].get("filled", {})
                    avg_px = filled_data.get("avgPx")
                    if avg_px:
                        fill_price = float(avg_px)
                        print(f"[INFO] Got fill price from statuses[0].filled.avgPx: ${fill_price}")
            
            # Try format 2: response.data.statuses[0].totalSz (calculate avg price)
            if not fill_price and statuses:
                total_sz = statuses[0].get("totalSz")
                if total_sz and total_sz > 0:
                    # Use the close price as approximation
                    fill_price = hl_client.get_current_price(actual_coin)
                    print(f"[INFO] Using current price as fill price (filled {total_sz} units): ${fill_price}")
            
            # Try format 3: direct avgPx in result
            if not fill_price and "avgPx" in result:
                fill_price = float(result["avgPx"])
                print(f"[INFO] Got fill price from result.avgPx: ${fill_price}")
        
        if not fill_price:
            # Fallback to current market price if we can't get fill price
            fill_price = hl_client.get_current_price(actual_coin)
            print(f"[WARN] Could not extract fill price from result, using current price: ${fill_price}")

        return {
            "status": "success",
            "coin": actual_coin,
            "fill_price": fill_price,
            "result": result,
            "message": f"Position closed for {actual_coin} at ${fill_price:.2f}"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Error closing position: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error closing position: {str(e)}")
