"""
Trade Calculator Module
Handles all trade-related calculations including:
- Position size (dollar value and coin units)
- Margin required
- Liquidation price
- Slippage estimation
- Fees (maker/taker)
- Risk/Reward ratio
- Profit/Loss calculations
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class PositionSizeResult:
    """Result of position size calculation"""
    position_size_dollars: float  # Notional value in USD
    position_size_units: float    # Size in coin units (e.g., BTC)
    margin_required: float        # Margin required (position / leverage)
    risk_amount: float            # Dollar amount at risk
    risk_percentage: float        # Risk as % of portfolio
    sl_distance_pct: float        # Stop loss distance as %
    liquidation_price: Optional[float] = None
    liquidation_distance_pct: Optional[float] = None


@dataclass
class FeeResult:
    """Fee calculation result"""
    entry_fee: float
    exit_fee: float
    total_fees: float
    fee_type: str  # 'maker' or 'taker'


@dataclass
class TradeDetails:
    """Complete trade details with all calculations"""
    # Position
    position_size_dollars: float
    position_size_units: float
    margin_required: float
    leverage: float
    
    # Risk
    risk_amount: float
    risk_percentage: float
    max_loss_amount: float
    
    # Prices
    entry_price: float
    stop_loss: float
    liquidation_price: Optional[float]
    sl_distance_pct: float
    
    # Slippage
    slippage_pct: float
    slippage_amount: float
    effective_entry: float
    
    # Fees
    entry_fee: float
    exit_fee: float
    total_fees: float
    
    # Risk/Reward
    rr_ratio: float
    
    # Take Profits
    tp_levels: List[Dict]
    
    # Breakeven
    breakeven_price: float
    breakeven_distance_pct: float


class TradeCalculator:
    """Comprehensive trade calculator for position sizing and trade analysis"""
    
    # Default fees (can be overridden)
    DEFAULT_TAKER_FEE = 0.00035  # 0.035%
    DEFAULT_MAKER_FEE = 0.0001   # 0.01%
    
    # Maintenance margin requirements (varies by exchange)
    DEFAULT_MAINTENANCE_MARGIN = 0.005  # 0.5%
    
    def __init__(self, 
                 taker_fee: float = DEFAULT_TAKER_FEE,
                 maker_fee: float = DEFAULT_MAKER_FEE,
                 maintenance_margin: float = DEFAULT_MAINTENANCE_MARGIN):
        self.taker_fee = taker_fee
        self.maker_fee = maker_fee
        self.maintenance_margin = maintenance_margin
    
    def calculate_position_size(self,
                               portfolio_size: float,
                               risk_percentage: float,
                               entry_price: float,
                               stop_loss: float,
                               leverage: float,
                               direction: str) -> PositionSizeResult:
        """
        Calculate position size based on risk parameters
        
        Args:
            portfolio_size: Total portfolio size in USD
            risk_percentage: Risk as percentage of portfolio (e.g., 1.0 for 1%)
            entry_price: Entry price
            stop_loss: Stop loss price (0 to use liquidation)
            leverage: Leverage multiplier (e.g., 10 for 10x)
            direction: 'long' or 'short'
        
        Returns:
            PositionSizeResult with all calculated values
        """
        # Calculate risk amount
        risk_amount = portfolio_size * (risk_percentage / 100)
        
        # Determine stop loss distance
        if stop_loss == 0:
            # Use liquidation price as stop loss
            liquidation_price = self.calculate_liquidation_price(
                entry_price, leverage, direction
            )
            price_diff = abs(entry_price - liquidation_price)
            sl_distance_pct = price_diff / entry_price
            liquidation_distance_pct = sl_distance_pct
        else:
            # Use provided stop loss
            price_diff = abs(entry_price - stop_loss)
            sl_distance_pct = price_diff / entry_price
            liquidation_price = self.calculate_liquidation_price(
                entry_price, leverage, direction
            )
            liquidation_distance_pct = abs(entry_price - liquidation_price) / entry_price
        
        # Calculate position size (notional value in dollars)
        # Risk = Position Size * Stop Loss Distance
        # Therefore: Position Size = Risk / Stop Loss Distance
        if sl_distance_pct == 0:
            position_size_dollars = 0
        else:
            position_size_dollars = risk_amount / sl_distance_pct
        
        # Calculate position size in coin units
        position_size_units = position_size_dollars / entry_price
        
        # Calculate margin required
        margin_required = position_size_dollars / leverage
        
        return PositionSizeResult(
            position_size_dollars=position_size_dollars,
            position_size_units=position_size_units,
            margin_required=margin_required,
            risk_amount=risk_amount,
            risk_percentage=risk_percentage,
            sl_distance_pct=sl_distance_pct,
            liquidation_price=liquidation_price,
            liquidation_distance_pct=liquidation_distance_pct
        )
    
    def calculate_liquidation_price(self, 
                                   entry_price: float, 
                                   leverage: float, 
                                   direction: str,
                                   maintenance_margin: Optional[float] = None) -> float:
        """
        Calculate liquidation price accounting for maintenance margin
        
        Args:
            entry_price: Entry price
            leverage: Leverage multiplier
            direction: 'long' or 'short'
            maintenance_margin: Optional override for maintenance margin rate
        
        Returns:
            Liquidation price
        """
        mm = maintenance_margin or self.maintenance_margin
        
        # Formula: Liquidation = Entry * (1 ± (1/Leverage - MM))
        # Long: Entry * (1 - (1/Leverage - MM))
        # Short: Entry * (1 + (1/Leverage - MM))
        
        liquidation_threshold = (1 / leverage) - mm
        
        if direction.lower() == 'long':
            liquidation_price = entry_price * (1 - liquidation_threshold)
        else:
            liquidation_price = entry_price * (1 + liquidation_threshold)
        
        return liquidation_price
    
    def estimate_slippage(self, 
                         position_size_dollars: float, 
                         market_volume_24h: float,
                         market_impact_factor: float = 0.1) -> float:
        """
        Estimate slippage based on position size relative to market volume
        
        Args:
            position_size_dollars: Position size in USD
            market_volume_24h: 24-hour trading volume in USD
            market_impact_factor: Factor to adjust impact (default 0.1)
        
        Returns:
            Slippage as percentage (e.g., 0.001 for 0.1%)
        """
        if market_volume_24h == 0:
            return 0.001  # Default 0.1% if no volume data
        
        # Simple model: slippage increases with position size relative to volume
        volume_ratio = position_size_dollars / market_volume_24h
        slippage = volume_ratio * market_impact_factor
        
        # Minimum slippage of 0.01%
        return max(slippage, 0.0001)
    
    def calculate_fees(self, 
                      position_size_dollars: float, 
                      is_maker: bool = False) -> FeeResult:
        """
        Calculate trading fees
        
        Args:
            position_size_dollars: Position size in USD
            is_maker: True if using maker orders (limit orders), False for taker
        
        Returns:
            FeeResult with entry, exit, and total fees
        """
        fee_rate = self.maker_fee if is_maker else self.taker_fee
        fee_type = 'maker' if is_maker else 'taker'
        
        # Fees on entry and exit
        entry_fee = position_size_dollars * fee_rate
        exit_fee = position_size_dollars * fee_rate
        total_fees = entry_fee + exit_fee
        
        return FeeResult(
            entry_fee=entry_fee,
            exit_fee=exit_fee,
            total_fees=total_fees,
            fee_type=fee_type
        )
    
    def calculate_rr_ratio(self,
                          entry_price: float,
                          stop_loss: float,
                          take_profits: List[Dict],
                          direction: str) -> float:
        """
        Calculate Risk/Reward ratio
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profits: List of dicts with 'price' and 'allocation' keys
            direction: 'long' or 'short'
        
        Returns:
            Risk/Reward ratio (e.g., 2.5 means 1:2.5 risk/reward)
        """
        # Calculate risk (distance to stop loss)
        if direction.lower() == 'long':
            risk = entry_price - stop_loss
        else:
            risk = stop_loss - entry_price
        
        if risk <= 0:
            return 0
        
        # Calculate weighted average reward
        total_reward = 0
        total_allocation = 0
        
        for tp in take_profits:
            if direction.lower() == 'long':
                reward_distance = tp['price'] - entry_price
            else:
                reward_distance = entry_price - tp['price']
            
            if reward_distance > 0:
                total_reward += reward_distance * tp['allocation']
                total_allocation += tp['allocation']
        
        if total_allocation == 0:
            return 0
        
        # Normalize by total allocation
        avg_reward = total_reward / total_allocation
        rr_ratio = avg_reward / risk
        
        return rr_ratio
    
    def calculate_tp_pnl(self,
                        position_size_dollars: float,
                        entry_price: float,
                        tp_price: float,
                        allocation: float,
                        direction: str,
                        fees: Optional[FeeResult] = None) -> Dict:
        """
        Calculate P&L for a specific take profit level
        
        Args:
            position_size_dollars: Total position size in USD
            entry_price: Entry price
            tp_price: Take profit price
            allocation: Allocation percentage (0-1)
            direction: 'long' or 'short'
            fees: Optional FeeResult to subtract fees
        
        Returns:
            Dict with profit details
        """
        # Allocated position size
        allocated_size = position_size_dollars * allocation
        
        # Position units
        position_units = allocated_size / entry_price
        
        # Price difference
        if direction.lower() == 'long':
            price_diff = tp_price - entry_price
        else:
            price_diff = entry_price - tp_price
        
        # Gross profit
        gross_profit = position_units * price_diff
        
        # Net profit (subtract allocated fees)
        if fees:
            allocated_fees = fees.total_fees * allocation
            net_profit = gross_profit - allocated_fees
        else:
            net_profit = gross_profit
            allocated_fees = 0
        
        # ROI on margin
        margin_used = allocated_size / (position_size_dollars / allocated_size) if allocated_size > 0 else 0
        roi_pct = (net_profit / margin_used * 100) if margin_used > 0 else 0
        
        return {
            'allocated_size': allocated_size,
            'position_units': position_units,
            'gross_profit': gross_profit,
            'allocated_fees': allocated_fees,
            'net_profit': net_profit,
            'roi_pct': roi_pct,
            'price_diff': price_diff,
            'price_diff_pct': (price_diff / entry_price) * 100
        }
    
    def calculate_sl_pnl(self,
                        position_size_dollars: float,
                        entry_price: float,
                        sl_price: float,
                        allocation: float,
                        direction: str,
                        fees: Optional[FeeResult] = None) -> Dict:
        """
        Calculate P&L for a specific stop loss level
        
        Returns:
            Dict with loss details
        """
        # Allocated position size
        allocated_size = position_size_dollars * allocation
        
        # Position units
        position_units = allocated_size / entry_price
        
        # Price difference
        if direction.lower() == 'long':
            price_diff = entry_price - sl_price
        else:
            price_diff = sl_price - entry_price
        
        # Gross loss
        gross_loss = position_units * price_diff
        
        # Net loss (add allocated fees)
        if fees:
            allocated_fees = fees.total_fees * allocation
            net_loss = gross_loss + allocated_fees
        else:
            net_loss = gross_loss
            allocated_fees = 0
        
        return {
            'allocated_size': allocated_size,
            'position_units': position_units,
            'gross_loss': gross_loss,
            'allocated_fees': allocated_fees,
            'net_loss': net_loss,
            'price_diff': price_diff,
            'price_diff_pct': (price_diff / entry_price) * 100
        }
    
    def calculate_breakeven(self,
                           entry_price: float,
                           direction: str,
                           total_fees: float,
                           position_size_units: float) -> Tuple[float, float]:
        """
        Calculate breakeven price
        
        Args:
            entry_price: Entry price
            direction: 'long' or 'short'
            total_fees: Total fees in dollars
            position_size_units: Position size in coin units
        
        Returns:
            Tuple of (breakeven_price, distance_percentage)
        """
        if position_size_units == 0:
            return entry_price, 0
        
        # Price movement needed to cover fees
        price_movement = total_fees / position_size_units
        
        if direction.lower() == 'long':
            breakeven_price = entry_price + price_movement
        else:
            breakeven_price = entry_price - price_movement
        
        distance_pct = abs(breakeven_price - entry_price) / entry_price
        
        return breakeven_price, distance_pct
    
    def calculate_complete_trade(self,
                                portfolio_size: float,
                                risk_percentage: float,
                                entry_price: float,
                                stop_loss: float,
                                take_profits: List[Dict],
                                leverage: float,
                                direction: str,
                                market_volume_24h: float = 0,
                                is_maker: bool = False) -> TradeDetails:
        """
        Calculate complete trade details with all metrics
        
        Returns:
            TradeDetails with all calculations
        """
        # 1. Calculate position size
        pos_result = self.calculate_position_size(
            portfolio_size, risk_percentage, entry_price, stop_loss, 
            leverage, direction
        )
        
        # 2. Estimate slippage
        slippage_pct = self.estimate_slippage(
            pos_result.position_size_dollars, market_volume_24h
        )
        slippage_amount = pos_result.position_size_dollars * slippage_pct
        
        # Calculate effective entry with slippage
        if direction.lower() == 'long':
            effective_entry = entry_price * (1 + slippage_pct)
        else:
            effective_entry = entry_price * (1 - slippage_pct)
        
        # 3. Calculate fees
        fees = self.calculate_fees(pos_result.position_size_dollars, is_maker)
        
        # 4. Calculate R/R ratio
        rr_ratio = self.calculate_rr_ratio(entry_price, stop_loss, take_profits, direction)
        
        # 5. Calculate TP levels with P&L
        tp_levels = []
        for tp in take_profits:
            pnl = self.calculate_tp_pnl(
                pos_result.position_size_dollars,
                entry_price,
                tp['price'],
                tp['allocation'],
                direction,
                fees
            )
            tp_levels.append({
                'price': tp['price'],
                'allocation': tp['allocation'],
                'profit': pnl['net_profit'],
                'roi_pct': pnl['roi_pct'],
                'distance_pct': pnl['price_diff_pct']
            })
        
        # 6. Calculate breakeven
        breakeven_price, breakeven_distance_pct = self.calculate_breakeven(
            entry_price, direction, fees.total_fees, pos_result.position_size_units
        )
        
        # Calculate max loss (at stop loss)
        if stop_loss > 0:
            sl_pnl = self.calculate_sl_pnl(
                pos_result.position_size_dollars,
                entry_price,
                stop_loss,
                1.0,  # Full position
                direction,
                fees
            )
            max_loss_amount = sl_pnl['net_loss']
        else:
            # At liquidation
            max_loss_amount = pos_result.margin_required + fees.total_fees
        
        return TradeDetails(
            position_size_dollars=pos_result.position_size_dollars,
            position_size_units=pos_result.position_size_units,
            margin_required=pos_result.margin_required,
            leverage=leverage,
            risk_amount=pos_result.risk_amount,
            risk_percentage=pos_result.risk_percentage,
            max_loss_amount=max_loss_amount,
            entry_price=entry_price,
            stop_loss=stop_loss,
            liquidation_price=pos_result.liquidation_price,
            sl_distance_pct=pos_result.sl_distance_pct,
            slippage_pct=slippage_pct,
            slippage_amount=slippage_amount,
            effective_entry=effective_entry,
            entry_fee=fees.entry_fee,
            exit_fee=fees.exit_fee,
            total_fees=fees.total_fees,
            rr_ratio=rr_ratio,
            tp_levels=tp_levels,
            breakeven_price=breakeven_price,
            breakeven_distance_pct=breakeven_distance_pct
        )


# Global calculator instance
trade_calc = TradeCalculator()
