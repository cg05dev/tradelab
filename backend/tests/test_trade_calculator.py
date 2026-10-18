import pytest

from trade_calculator import TradeCalculator


@pytest.fixture
def calc():
    return TradeCalculator()


class TestPositionSize:
    def test_long_with_stop_loss_sizes_to_risk(self, calc):
        # $10k account, 1% risk = $100. A 5% stop means a $2,000 notional position.
        result = calc.calculate_position_size(10_000, 1.0, 100, 95, 10, "long")

        assert result.risk_amount == pytest.approx(100)
        assert result.sl_distance_pct == pytest.approx(0.05)
        assert result.position_size_dollars == pytest.approx(2_000)
        assert result.position_size_units == pytest.approx(20)
        assert result.margin_required == pytest.approx(200)

    def test_short_mirrors_long(self, calc):
        long = calc.calculate_position_size(10_000, 1.0, 100, 95, 10, "long")
        short = calc.calculate_position_size(10_000, 1.0, 100, 105, 10, "short")

        assert short.position_size_dollars == pytest.approx(long.position_size_dollars)
        assert short.margin_required == pytest.approx(long.margin_required)

    def test_loss_at_stop_equals_risk_amount(self, calc):
        result = calc.calculate_position_size(25_000, 2.0, 64_000, 62_400, 20, "long")
        loss_at_stop = result.position_size_units * (64_000 - 62_400)

        assert loss_at_stop == pytest.approx(result.risk_amount)

    def test_no_stop_loss_sizes_to_liquidation_distance(self, calc):
        result = calc.calculate_position_size(10_000, 1.0, 100, 0, 10, "long")

        # Liquidation is 8.75% away at 10x with 1.25% maintenance margin.
        assert result.sl_distance_pct == pytest.approx(0.0875)
        assert result.liquidation_price == pytest.approx(91.25)
        assert result.position_size_dollars == pytest.approx(100 / 0.0875)

    def test_stop_at_entry_gives_zero_size(self, calc):
        result = calc.calculate_position_size(10_000, 1.0, 100, 100, 10, "long")

        assert result.position_size_dollars == 0
        assert result.margin_required == 0


class TestLiquidationPrice:
    @pytest.mark.parametrize(
        "direction, expected",
        [("long", 91.25), ("short", 108.75), ("LONG", 91.25)],
    )
    def test_accounts_for_maintenance_margin(self, calc, direction, expected):
        assert calc.calculate_liquidation_price(100, 10, direction) == pytest.approx(expected)

    def test_maintenance_margin_override(self, calc):
        assert calc.calculate_liquidation_price(100, 10, "long", maintenance_margin=0.05) == pytest.approx(95)

    def test_higher_leverage_liquidates_closer(self, calc):
        low = calc.calculate_liquidation_price(100, 5, "long")
        high = calc.calculate_liquidation_price(100, 20, "long")

        assert low < high < 100


class TestRiskReward:
    def test_weighted_average_of_take_profits(self, calc):
        tps = [{"price": 110, "allocation": 0.5}, {"price": 120, "allocation": 0.5}]

        # Average reward 15 against risk 5.
        assert calc.calculate_rr_ratio(100, 95, tps, "long") == pytest.approx(3.0)

    def test_short(self, calc):
        tps = [{"price": 90, "allocation": 1.0}]

        assert calc.calculate_rr_ratio(100, 105, tps, "short") == pytest.approx(2.0)

    def test_allocations_are_normalized(self, calc):
        tps = [{"price": 110, "allocation": 0.2}, {"price": 120, "allocation": 0.2}]

        assert calc.calculate_rr_ratio(100, 95, tps, "long") == pytest.approx(3.0)

    def test_take_profits_on_wrong_side_are_ignored(self, calc):
        tps = [{"price": 90, "allocation": 0.5}, {"price": 110, "allocation": 0.5}]

        assert calc.calculate_rr_ratio(100, 95, tps, "long") == pytest.approx(2.0)

    @pytest.mark.parametrize("stop", [100, 105])
    def test_invalid_stop_returns_zero(self, calc, stop):
        tps = [{"price": 110, "allocation": 1.0}]

        assert calc.calculate_rr_ratio(100, stop, tps, "long") == 0

    def test_no_valid_take_profits_returns_zero(self, calc):
        assert calc.calculate_rr_ratio(100, 95, [], "long") == 0


class TestFeesAndSlippage:
    def test_taker_fees(self, calc):
        fees = calc.calculate_fees(10_000)

        assert fees.fee_type == "taker"
        assert fees.entry_fee == pytest.approx(3.5)
        assert fees.total_fees == pytest.approx(7.0)

    def test_maker_fees(self, calc):
        fees = calc.calculate_fees(10_000, is_maker=True)

        assert fees.fee_type == "maker"
        assert fees.total_fees == pytest.approx(2.0)

    def test_custom_fee_rates(self):
        fees = TradeCalculator(taker_fee=0.001).calculate_fees(1_000)

        assert fees.total_fees == pytest.approx(2.0)

    def test_slippage_default_without_volume(self, calc):
        assert calc.estimate_slippage(10_000, 0) == 0.001

    def test_slippage_scales_with_volume_ratio(self, calc):
        assert calc.estimate_slippage(1_000_000, 100_000_000) == pytest.approx(0.001)

    def test_slippage_has_floor(self, calc):
        assert calc.estimate_slippage(100, 1_000_000_000) == 0.0001


class TestBreakeven:
    def test_long_breakeven_above_entry(self, calc):
        price, distance = calc.calculate_breakeven(100, "long", total_fees=7, position_size_units=20)

        assert price == pytest.approx(100.35)
        assert distance == pytest.approx(0.0035)

    def test_short_breakeven_below_entry(self, calc):
        price, _ = calc.calculate_breakeven(100, "short", total_fees=7, position_size_units=20)

        assert price == pytest.approx(99.65)

    def test_zero_size(self, calc):
        assert calc.calculate_breakeven(100, "long", 7, 0) == (100, 0)


class TestLevelPnl:
    def test_take_profit_net_of_allocated_fees(self, calc):
        fees = calc.calculate_fees(2_000)
        pnl = calc.calculate_tp_pnl(2_000, 100, 110, 0.5, "long", fees)

        assert pnl["gross_profit"] == pytest.approx(100)
        assert pnl["allocated_fees"] == pytest.approx(fees.total_fees * 0.5)
        assert pnl["net_profit"] == pytest.approx(100 - fees.total_fees * 0.5)
        assert pnl["price_diff_pct"] == pytest.approx(10)

    def test_stop_loss_adds_fees_to_loss(self, calc):
        fees = calc.calculate_fees(2_000)
        pnl = calc.calculate_sl_pnl(2_000, 100, 95, 1.0, "long", fees)

        assert pnl["gross_loss"] == pytest.approx(100)
        assert pnl["net_loss"] == pytest.approx(100 + fees.total_fees)

    def test_short_stop_loss(self, calc):
        pnl = calc.calculate_sl_pnl(2_000, 100, 105, 1.0, "short")

        assert pnl["gross_loss"] == pytest.approx(100)


class TestCompleteTrade:
    def test_with_stop_loss(self, calc):
        details = calc.calculate_complete_trade(
            portfolio_size=10_000,
            risk_percentage=1.0,
            entry_price=100,
            stop_loss=95,
            take_profits=[{"price": 110, "allocation": 1.0}],
            leverage=10,
            direction="long",
        )

        assert details.position_size_dollars == pytest.approx(2_000)
        assert details.rr_ratio == pytest.approx(2.0)
        assert details.total_fees == pytest.approx(1.4)
        assert details.max_loss_amount == pytest.approx(100 + 1.4)
        assert details.effective_entry == pytest.approx(100.1)  # default 0.1% slippage
        assert len(details.tp_levels) == 1
        assert details.tp_levels[0]["profit"] == pytest.approx(200 - 1.4)

    def test_without_stop_loss_max_loss_is_margin_plus_fees(self, calc):
        details = calc.calculate_complete_trade(
            portfolio_size=10_000,
            risk_percentage=1.0,
            entry_price=100,
            stop_loss=0,
            take_profits=[],
            leverage=10,
            direction="long",
        )

        assert details.max_loss_amount == pytest.approx(details.margin_required + details.total_fees)
        assert details.rr_ratio == 0
