from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from models import PositionSizeRequest, StopLoss, TakeProfit
from storage import load_mode, load_portfolio_size
from trade_calculator import trade_calc

router = APIRouter(prefix="/api/calculate", tags=["calculations"])


RISK_PCT = 0.02

@router.post("/position-size")
def calculate_position_size(request: PositionSizeRequest, mode: Optional[str] = None):
    """Calculate position size based on risk (matching original logic)"""
    current_mode = mode or load_mode()
    portfolio_size = load_portfolio_size(current_mode)
    risk_pct = request.risk_percentage / 100 if request.risk_percentage else RISK_PCT
    risk_amount = portfolio_size * risk_pct
    
    if request.entry_price == 0:
        return {
            "position_size_dollars": 0,
            "position_size_units": 0,
            "margin_required": 0,
            "risk_amount": 0,
            "message": "Please enter an entry price"
        }
    
    # If no stop loss, calculate based on liquidation price
    if request.stop_loss == 0 or request.stop_loss is None:
        # Calculate liquidation price based on leverage
        # For long: liquidation = entry * (1 - 1/leverage)
        # For short: liquidation = entry * (1 + 1/leverage)
        if request.direction.lower() == 'long':
            liquidation_price = request.entry_price * (1 - 1 / request.leverage)
        else:
            liquidation_price = request.entry_price * (1 + 1 / request.leverage)
        
        # Calculate price difference to liquidation
        price_diff = abs(request.entry_price - liquidation_price)
        if price_diff == 0:
            return {
                "position_size_dollars": 0,
                "position_size_units": 0,
                "margin_required": 0,
                "risk_amount": 0,
                "message": "Invalid leverage"
            }
        
        # Calculate liquidation percentage
        liquidation_percentage = price_diff / request.entry_price
        
        # Calculate position size (notional value in dollars)
        # This is: risk_amount / liquidation_percentage
        position_size_dollars = risk_amount / liquidation_percentage
        
        # Calculate position size in coin units
        position_size_units = position_size_dollars / request.entry_price
        
        # Calculate margin required (position size / leverage)
        margin_required = position_size_dollars / request.leverage
        
        # Verify: position_size should equal margin_required × leverage
        verified_position_size = margin_required * request.leverage
        
        return {
            "position_size_dollars": position_size_dollars,
            "position_size_units": position_size_units,
            "margin_required": margin_required,
            "risk_amount": risk_amount,
            "sl_percentage": liquidation_percentage * 100,
            "liquidation_price": liquidation_price,
            "verification": f"${margin_required:,.2f} margin × {request.leverage}x = ${verified_position_size:,.2f} position",
            "message": f"Margin: ${margin_required:,.2f} | Position: {position_size_units:.6f} units"
        }
    
    # Traditional stop loss calculation
    price_diff = abs(request.entry_price - request.stop_loss)
    if price_diff == 0:
        return {
            "position_size_dollars": 0,
            "position_size_units": 0,
            "margin_required": 0,
            "risk_amount": 0,
            "message": "Stop loss cannot equal entry price"
        }
    
    # Calculate stop loss percentage
    sl_percentage = price_diff / request.entry_price
    
    # Calculate position size (notional value in dollars)
    # This is: risk_amount / sl_percentage
    position_size_dollars = risk_amount / sl_percentage
    
    # Calculate position size in coin units
    position_size_units = position_size_dollars / request.entry_price
    
    # Calculate margin required (position size / leverage)
    margin_required = position_size_dollars / request.leverage
    
    # Verify: position_size should equal margin_required × leverage
    verified_position_size = margin_required * request.leverage
    
    return {
        "position_size_dollars": position_size_dollars,
        "position_size_units": position_size_units,
        "margin_required": margin_required,
        "risk_amount": risk_amount,
        "sl_percentage": sl_percentage * 100,
        "verification": f"${margin_required:,.2f} margin × {request.leverage}x = ${verified_position_size:,.2f} position",
        "message": f"Margin: ${margin_required:,.2f} | Position: {position_size_units:.6f} units"
    }

class RiskRewardRequest(BaseModel):
    entry_price: float
    stop_loss: float
    take_profits: List[TakeProfit]
    direction: str

@router.post("/risk-reward")
def calculate_risk_reward(request: RiskRewardRequest):
    """Calculate risk/reward ratio using trade calculator"""
    if not request.take_profits or len(request.take_profits) == 0:
        return {"rr_ratio": 0, "message": "No take profits set"}
    
    try:
        # Convert TakeProfit objects to dicts for calculator
        tp_dicts = [{"price": tp.price, "allocation": tp.allocation} for tp in request.take_profits]
        
        rr_ratio = trade_calc.calculate_rr_ratio(
            entry_price=request.entry_price,
            stop_loss=request.stop_loss,
            take_profits=tp_dicts,
            direction=request.direction
        )
        
        return {
            "rr_ratio": rr_ratio, 
            "message": f"Risk/Reward: 1:{rr_ratio:.2f}" if rr_ratio > 0 else "Invalid setup"
        }
    except Exception as e:
        return {"rr_ratio": 0, "message": f"Calculation error: {str(e)}"}

class ProfitLossRequest(BaseModel):
    entry_price: float
    stop_loss: float
    position_size: float
    take_profits: List[TakeProfit]
    stop_losses: List[StopLoss]
    direction: str
    leverage: Optional[float] = None

@router.post("/profit-loss")
def calculate_profit_loss(request: ProfitLossRequest):
    """Calculate profit and loss amounts for TPs and SLs based on position size"""
    if request.position_size <= 0:
        return {
            "take_profits": [],
            "stop_losses": [],
            "message": "Invalid position size"
        }
    
    # Calculate total allocations
    total_tp_allocation = sum(tp.allocation for tp in request.take_profits)
    total_sl_allocation = sum(sl.allocation for sl in request.stop_losses)
    
    # Calculate profit amounts for take profits
    tp_results = []
    for i, tp in enumerate(request.take_profits):
        if tp.price > 0:
            # Calculate profit per unit
            if request.direction == 'long':
                profit_per_unit = tp.price - request.entry_price
            else:
                profit_per_unit = request.entry_price - tp.price
            
            # Normalize allocation if total doesn't equal 100%
            if total_tp_allocation > 0:
                normalized_allocation = tp.allocation / total_tp_allocation
            else:
                normalized_allocation = tp.allocation
            
            # Calculate allocated position size
            allocated_position_size = request.position_size * normalized_allocation
            
            # Calculate position units
            position_units = allocated_position_size / request.entry_price
            
            # Calculate profit amount
            profit_amount = position_units * profit_per_unit
            
            tp_results.append({
                "index": i,
                "price": tp.price,
                "allocation": tp.allocation,
                "profit_amount": profit_amount,
                "normalized_allocation": normalized_allocation
            })
    
    # Calculate loss amounts for stop losses
    sl_results = []
    for i, sl in enumerate(request.stop_losses):
        if sl.price > 0:
            # Calculate loss per unit
            if request.direction == 'long':
                loss_per_unit = request.entry_price - sl.price
            else:
                loss_per_unit = sl.price - request.entry_price
            
            # Normalize allocation if total doesn't equal 100%
            if total_sl_allocation > 0:
                normalized_allocation = sl.allocation / total_sl_allocation
            else:
                normalized_allocation = sl.allocation
            
            # Calculate allocated position size
            allocated_position_size = request.position_size * normalized_allocation
            
            # Calculate position units
            position_units = allocated_position_size / request.entry_price
            
            # Calculate loss amount
            loss_amount = position_units * loss_per_unit
            
            sl_results.append({
                "index": i,
                "price": sl.price,
                "allocation": sl.allocation,
                "loss_amount": loss_amount,
                "normalized_allocation": normalized_allocation
            })
    
    # If no stop losses are set, add liquidation loss (equal to margin)
    if len(sl_results) == 0 and request.stop_loss == 0 and request.leverage and request.leverage > 0:
        margin = request.position_size / request.leverage
        sl_results.append({
            "index": 0,
            "price": 0,  # Liquidation price (not set)
            "allocation": 1.0,
            "loss_amount": margin,
            "normalized_allocation": 1.0,
            "is_liquidation": True
            })
    
    return {
        "take_profits": tp_results,
        "stop_losses": sl_results,
        "message": ""
    }

class TradeDetailsRequest(BaseModel):
    """Request model for comprehensive trade calculation"""
    portfolio_size: float
    risk_percentage: float
    entry_price: float
    stop_loss: float
    take_profits: List[TakeProfit]
    leverage: float
    direction: str
    market_volume_24h: Optional[float] = 0
    is_maker: Optional[bool] = False

@router.post("/trade-details")
def calculate_trade_details(request: TradeDetailsRequest):
    """Calculate comprehensive trade details including fees and slippage"""
    try:
        # Convert TakeProfit objects to dicts
        tp_dicts = [{"price": tp.price, "allocation": tp.allocation} for tp in request.take_profits]
        
        # Calculate complete trade details
        details = trade_calc.calculate_complete_trade(
            portfolio_size=request.portfolio_size,
            risk_percentage=request.risk_percentage,
            entry_price=request.entry_price,
            stop_loss=request.stop_loss,
            take_profits=tp_dicts,
            leverage=request.leverage,
            direction=request.direction,
            market_volume_24h=request.market_volume_24h or 0,
            is_maker=request.is_maker or False
        )
        
        return {
            "position_size_dollars": details.position_size_dollars,
            "position_size_units": details.position_size_units,
            "margin_required": details.margin_required,
            "leverage": details.leverage,
            "risk_amount": details.risk_amount,
            "risk_percentage": details.risk_percentage,
            "max_loss_amount": details.max_loss_amount,
            "entry_price": details.entry_price,
            "stop_loss": details.stop_loss,
            "liquidation_price": details.liquidation_price,
            "sl_distance_pct": details.sl_distance_pct * 100,
            "slippage_pct": details.slippage_pct * 100,
            "slippage_amount": details.slippage_amount,
            "effective_entry": details.effective_entry,
            "entry_fee": details.entry_fee,
            "exit_fee": details.exit_fee,
            "total_fees": details.total_fees,
            "rr_ratio": details.rr_ratio,
            "tp_levels": details.tp_levels,
            "breakeven_price": details.breakeven_price,
            "breakeven_distance_pct": details.breakeven_distance_pct * 100,
            "message": f"R/R: 1:{details.rr_ratio:.2f} | Breakeven: ${details.breakeven_price:.2f}"
        }
    except Exception as e:
        return {
            "error": str(e),
            "message": f"Calculation error: {str(e)}"
        }
