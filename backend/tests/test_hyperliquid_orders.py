"""Live order and close endpoints, against a mocked exchange (see conftest `hl`)."""

import pytest

from routers import hyperliquid


def _status(status):
    return {"status": "ok", "response": {"type": "order", "data": {"statuses": [status]}}}


def _filled(size, price, oid=42):
    return _status({"filled": {"totalSz": str(size), "avgPx": str(price), "oid": oid}})


RESTING = _status({"resting": {"oid": 7}})


@pytest.fixture
def live(client, hl, monkeypatch):
    """Live mode, BTC at 100k with 5 size decimals, and no waiting after closes."""
    monkeypatch.setattr(hyperliquid, "CLOSE_CONFIRM_DELAY_SECONDS", 0)
    client.post("/api/mode", json={"mode": "live"})
    hl.get_current_price.return_value = 100_000.0
    hl.get_asset_metadata.return_value = {"BTC": {"sz_decimals": 5}}
    hl.place_stop_order.return_value = RESTING
    return client


def _order(**overrides):
    order = {
        "coin": "BTC", "is_buy": True, "margin_amount": 200, "leverage": 10, "entry_price": 100_000,
        "take_profits": [{"price": 110_000, "allocation": 0.5}, {"price": 120_000, "allocation": 0.5}],
        "stop_losses": [{"price": 95_000, "allocation": 1.0}],
    }
    order.update(overrides)
    return order


def _sizes(mock):
    return [c.kwargs["sz"] for c in mock.call_args_list]


class TestPlaceOrder:
    def test_sizes_from_margin_and_protects_the_filled_size(self, live, hl):
        hl.exchange_client.order.side_effect = [_filled(0.02, 100_050), RESTING, RESTING]

        body = live.post("/api/hyperliquid/order", json=_order()).json()

        entry, tp1, tp2 = hl.exchange_client.order.call_args_list
        assert entry.kwargs["sz"] == pytest.approx(0.02)  # $200 margin x 10 / $100k
        assert entry.kwargs["reduce_only"] is False
        assert [tp1.kwargs["sz"], tp2.kwargs["sz"]] == pytest.approx([0.01, 0.01])
        assert all(c.kwargs["reduce_only"] and c.kwargs["is_buy"] is False for c in (tp1, tp2))
        assert hl.place_stop_order.call_args.kwargs["size"] == pytest.approx(0.02)
        assert body["status"] == "success"
        assert body["warnings"] == []
        assert body["avg_price"] == pytest.approx(100_050)
        assert body["notional"] == pytest.approx(0.02 * 100_050)
        assert body["order_id"] == 42

    @pytest.mark.parametrize("field", ["take_profits", "stop_losses"])
    def test_rejects_percent_allocations_before_trading(self, live, hl, field):
        response = live.post("/api/hyperliquid/order", json=_order(**{field: [{"price": 110_000, "allocation": 50}]}))

        assert response.status_code == 422
        hl.exchange_client.order.assert_not_called()

    def test_rejects_allocations_over_100_percent(self, live, hl):
        tps = [{"price": 110_000, "allocation": 0.7}, {"price": 120_000, "allocation": 0.5}]

        response = live.post("/api/hyperliquid/order", json=_order(take_profits=tps))

        assert response.status_code == 422
        hl.exchange_client.order.assert_not_called()

    def test_rejected_entry_is_a_400_and_places_no_protection(self, live, hl):
        hl.exchange_client.order.return_value = _status({"error": "Insufficient margin to place order."})

        response = live.post("/api/hyperliquid/order", json=_order())

        assert response.status_code == 400
        assert "Insufficient margin" in response.json()["detail"]
        assert hl.exchange_client.order.call_count == 1
        hl.place_stop_order.assert_not_called()

    def test_unfilled_entry_is_an_error(self, live, hl):
        hl.exchange_client.order.return_value = RESTING

        response = live.post("/api/hyperliquid/order", json=_order())

        assert response.status_code == 400
        assert hl.exchange_client.order.call_count == 1
        hl.place_stop_order.assert_not_called()

    def test_partial_fill_sizes_protection_to_what_filled(self, live, hl):
        hl.exchange_client.order.side_effect = [_filled(0.01, 100_000), RESTING, RESTING]

        body = live.post("/api/hyperliquid/order", json=_order()).json()

        assert _sizes(hl.exchange_client.order)[1:] == pytest.approx([0.005, 0.005])
        assert hl.place_stop_order.call_args.kwargs["size"] == pytest.approx(0.01)
        assert body["filled_size"] == pytest.approx(0.01)

    def test_rounded_target_sizes_never_exceed_the_position(self, live, hl):
        hl.exchange_client.order.side_effect = [_filled(0.02, 100_000)] + [RESTING] * 3
        third = 1 / 3
        tps = [{"price": 110_000 + i * 1_000, "allocation": third} for i in range(3)]

        live.post("/api/hyperliquid/order", json=_order(take_profits=tps))

        assert sum(_sizes(hl.exchange_client.order)[1:]) <= 0.02 + 1e-12

    def test_prices_below_a_dollar_keep_their_precision(self, live, hl):
        """Whole-dollar rounding used to turn every sub-$1 price into 0, so TP/SL orders were skipped."""
        hl.get_current_price.return_value = 0.15
        hl.get_asset_metadata.return_value = {"DOGE": {"sz_decimals": 0}}
        hl.exchange_client.order.side_effect = [_filled(13_333, 0.1503), RESTING]

        body = live.post("/api/hyperliquid/order", json=_order(
            coin="DOGE", entry_price=0.15,
            take_profits=[{"price": 0.161_234_5, "allocation": 1.0}],
            stop_losses=[{"price": 0.141_234_5, "allocation": 1.0}],
        )).json()

        entry, tp = hl.exchange_client.order.call_args_list
        assert entry.kwargs["limit_px"] == 0.1503  # 0.15 + 0.2% buffer
        assert entry.kwargs["sz"] == 13_333  # $200 x 10 / $0.15, whole coins
        assert tp.kwargs["limit_px"] == 0.161_23
        assert hl.place_stop_order.call_args.kwargs["trigger_price"] == 0.141_23
        assert body["status"] == "success"

    def test_btc_prices_stay_whole_dollars(self, live, hl):
        hl.get_current_price.return_value = 100_000.0
        hl.exchange_client.order.side_effect = [_filled(0.02, 100_200), RESTING]

        live.post("/api/hyperliquid/order", json=_order(take_profits=[{"price": 110_005.5, "allocation": 1.0}]))

        entry, tp = hl.exchange_client.order.call_args_list
        assert entry.kwargs["limit_px"] == 100_200
        assert tp.kwargs["limit_px"] == 110_006

    def test_rejected_stop_loss_is_reported_not_swallowed(self, live, hl):
        hl.exchange_client.order.side_effect = [_filled(0.02, 100_000), RESTING, RESTING]
        hl.place_stop_order.return_value = _status({"error": "Invalid TP/SL price"})

        response = live.post("/api/hyperliquid/order", json=_order())

        assert response.status_code == 200  # the position is open, so the caller must still journal it
        body = response.json()
        assert body["status"] == "partial"
        assert len(body["warnings"]) == 1
        assert "Stop loss 1" in body["warnings"][0]
        assert "no stop" in body["warnings"][0]

    def test_take_profit_exception_is_reported(self, live, hl):
        hl.exchange_client.order.side_effect = [_filled(0.02, 100_000), RuntimeError("timeout"), RESTING]

        body = live.post("/api/hyperliquid/order", json=_order()).json()

        assert body["status"] == "partial"
        assert "Take profit 1" in body["warnings"][0]
        assert "timeout" in body["warnings"][0]


class TestClosePosition:
    def test_requires_a_json_body(self, live, hl):
        assert live.post("/api/hyperliquid/close/BTC").status_code == 422
        response = live.post("/api/hyperliquid/close/BTC", content="{}", headers={"Content-Type": "text/plain"})
        assert response.status_code == 422
        hl.market_close.assert_not_called()

    def test_never_matches_a_different_coin(self, live, hl):
        hl.get_positions.return_value = [{"coin": "ETHFI", "size": 10.0}]

        response = live.post("/api/hyperliquid/close/ETH", json={})

        assert response.status_code == 400
        assert "ETHFI" in response.json()["detail"]
        hl.market_close.assert_not_called()

    def test_coin_match_ignores_case(self, live, hl):
        hl.get_positions.side_effect = [[{"coin": "kPEPE", "size": 1_000.0}], []]
        hl.market_close.return_value = _filled(1_000, 0.01)

        response = live.post("/api/hyperliquid/close/kpepe", json={})

        assert response.status_code == 200
        hl.market_close.assert_called_once_with("kPEPE", sz=None)

    def test_closes_only_the_requested_size(self, live, hl):
        hl.get_positions.side_effect = [[{"coin": "BTC", "size": 0.05}], [{"coin": "BTC", "size": 0.03}]]
        hl.market_close.return_value = _filled(0.02, 101_000)

        body = live.post("/api/hyperliquid/close/BTC", json={"size": 0.02}).json()

        hl.market_close.assert_called_once_with("BTC", sz=0.02)
        hl.exchange_client.order.assert_not_called()  # position reached its target, no fallback
        assert body["fill_price"] == pytest.approx(101_000)
        assert body["closed_size"] == pytest.approx(0.02)

    def test_size_beyond_the_position_closes_all_of_it(self, live, hl):
        hl.get_positions.side_effect = [[{"coin": "BTC", "size": 0.01}], []]
        hl.market_close.return_value = _filled(0.01, 101_000)

        live.post("/api/hyperliquid/close/BTC", json={"size": 0.02})

        hl.market_close.assert_called_once_with("BTC", sz=None)

    def test_fallback_buys_back_a_short_that_did_not_close(self, live, hl):
        hl.get_positions.side_effect = [[{"coin": "BTC", "size": -0.05}], [{"coin": "BTC", "size": -0.05}]]
        hl.market_close.return_value = _status({"error": "could not match"})
        hl.exchange_client.order.return_value = _filled(0.05, 99_000)

        body = live.post("/api/hyperliquid/close/BTC", json={}).json()

        fallback = hl.exchange_client.order.call_args.kwargs
        assert fallback["is_buy"] is True
        assert fallback["sz"] == pytest.approx(0.05)
        assert fallback["reduce_only"] is True
        assert body["fill_price"] == pytest.approx(99_000)

    def test_failed_close_is_an_error(self, live, hl):
        hl.get_positions.side_effect = [[{"coin": "BTC", "size": 0.05}], [{"coin": "BTC", "size": 0.05}]]
        hl.market_close.return_value = _status({"error": "could not match"})
        hl.get_current_price.return_value = None  # so the fallback can't run either

        response = live.post("/api/hyperliquid/close/BTC", json={})

        assert response.status_code == 400
        assert "could not match" in response.json()["detail"]
