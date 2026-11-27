"""Liquidation price of an isolated position, as Hyperliquid computes it.

Hyperliquid's maintenance margin is half the initial margin at the asset's maximum leverage
(1.25% for 40x BTC, 5% for a 10x asset), and an isolated position is liquidated when its margin
falls to that (https://hyperliquid.gitbook.io/hyperliquid-docs/trading/liquidations):

    liq_price = price - side * margin_available / position_size / (1 - mm * side)

With the margin at entry (notional / leverage) that is entry × (1 − 1/leverage) / (1 − mm) for a
long and entry × (1 + 1/leverage) / (1 + mm) for a short. Large positions on assets with margin
tiers have a higher maintenance margin, so for them this is an estimate. The planner uses the same
formula (frontend/src/trading.ts).
"""

from typing import Optional

# BTC's maximum leverage, assumed when an asset's isn't known
DEFAULT_MAX_LEVERAGE = 40


def maintenance_margin(max_leverage: Optional[float] = None) -> float:
    return 1 / (2 * (max_leverage or DEFAULT_MAX_LEVERAGE))


def liquidation_price(entry: float, leverage: float, direction: str, max_leverage: Optional[float] = None) -> float:
    """Where an isolated position opened at `entry` with `leverage` is liquidated."""
    mm = maintenance_margin(max_leverage)
    if direction.lower() == "short":
        return entry * (1 + 1 / leverage) / (1 + mm)
    return entry * (1 - 1 / leverage) / (1 - mm)
