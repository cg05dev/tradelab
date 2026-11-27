"""Liquidation estimate used by the paper simulator."""

# Hyperliquid's maintenance margin for BTC: half the initial margin at its 40x maximum leverage.
# Other assets have their own, so for them this is an estimate. The planner uses the same value
# (frontend/src/trading.ts).
MAINTENANCE_MARGIN = 0.0125


def liquidation_price(entry: float, leverage: float, direction: str) -> float:
    """Where an isolated position opened at `entry` with `leverage` is liquidated."""
    threshold = 1 / leverage - MAINTENANCE_MARGIN
    return entry * (1 + threshold) if direction.lower() == "short" else entry * (1 - threshold)
