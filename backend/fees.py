"""
Trading costs TradeLab plans with, so "risk 2%" means 2% of the account after costs.

A stopped-out trade pays the taker fee twice (the entry is an IOC order, the stop is a market
order) and fills somewhat past the stop. The planner (frontend/src/pages/PlanTrade.tsx) divides the
risk by the stop distance plus those costs, and the paper simulator charges the same rates.

Rates are the connected account's (Hyperliquid's userFees, which reflects volume tier, less the
referral discount), else Hyperliquid's base tier.
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)

# Hyperliquid's base-tier perp fees (fractions of notional)
DEFAULT_TAKER = 0.00045
DEFAULT_MAKER = 0.00015
# Assumed fill past the stop price for a stop-market order. One real BTC stop filled 0.03% past
# it; thin markets slip more.
STOP_SLIPPAGE = 0.0005


def default_rates() -> Dict:
    return {"taker": DEFAULT_TAKER, "maker": DEFAULT_MAKER, "stop_slippage": STOP_SLIPPAGE, "source": "default"}


def current_rates(client) -> Dict:
    """The connected account's rates, or the defaults when there's no account or they can't be fetched."""
    if client and getattr(client, "enabled", False):
        try:
            return {**client.get_fee_rates(), "stop_slippage": STOP_SLIPPAGE, "source": "account"}
        except Exception as e:
            logger.warning(f"Could not fetch Hyperliquid fee rates, using the defaults: {e}")
    return default_rates()

