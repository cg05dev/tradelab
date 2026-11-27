"""Liquidation prices match Hyperliquid's formula (risk.py)."""

import pytest

from risk import liquidation_price, maintenance_margin


@pytest.mark.parametrize("max_leverage, expected", [(40, 0.0125), (20, 0.025), (10, 0.05), (3, 1 / 6), (None, 0.0125)])
def test_maintenance_margin_is_half_the_initial_margin_at_max_leverage(max_leverage, expected):
    assert maintenance_margin(max_leverage) == pytest.approx(expected)


@pytest.mark.parametrize("direction", ["long", "short"])
@pytest.mark.parametrize("leverage, max_leverage", [(10, 40), (3, 3), (20, 20), (5, 10)])
def test_at_the_liquidation_price_margin_equals_maintenance_margin(direction, leverage, max_leverage):
    """The definition: an isolated position's equity has fallen to the maintenance margin of its value."""
    entry, units = 100.0, 2.0
    price = liquidation_price(entry, leverage, direction, max_leverage)
    side = 1 if direction == "long" else -1

    equity = entry * units / leverage + side * (price - entry) * units

    assert equity == pytest.approx(maintenance_margin(max_leverage) * price * units)


def test_examples():
    assert liquidation_price(100, 10, "long") == pytest.approx(91.139, abs=1e-3)
    assert liquidation_price(100, 10, "short") == pytest.approx(108.642, abs=1e-3)
    assert liquidation_price(100, 5, "long", max_leverage=10) == pytest.approx(84.211, abs=1e-3)
    assert liquidation_price(100, 5, "SHORT", max_leverage=10) == pytest.approx(114.286, abs=1e-3)
