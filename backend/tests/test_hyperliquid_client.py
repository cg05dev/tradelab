import math
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from hyperliquid.utils.signing import float_to_wire

from hyperliquid_client import HyperliquidClient, round_price


def _response(payload):
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


@patch("hyperliquid_client.requests.post")
def test_get_current_price_uses_public_all_mids(mock_post):
    mock_post.return_value = _response({"BTC": "63928.5"})

    price = HyperliquidClient().get_current_price("btc")

    assert price == 63928.5
    mock_post.assert_called_once()
    assert mock_post.call_args.kwargs["json"] == {"type": "allMids"}
    assert mock_post.call_args.kwargs["timeout"] == 10


@patch("hyperliquid_client.requests.post")
def test_get_current_price_returns_none_for_unknown_coin(mock_post):
    mock_post.return_value = _response({"BTC": "63928.5"})

    assert HyperliquidClient().get_current_price("UNKNOWN") is None


@patch("hyperliquid_client.requests.post", side_effect=RuntimeError("upstream unavailable"))
def test_get_current_price_returns_none_when_request_fails(_mock_post):
    assert HyperliquidClient().get_current_price("BTC") is None


class TestRoundPrice:
    @pytest.mark.parametrize("price, sz_decimals, expected", [
        (100_000.4, 5, 100_000),     # BTC: whole dollars
        (123_456.7, 5, 123_457),     # whole numbers are valid past 5 significant figures
        (99_999.7, 5, 100_000),
        (3_456.789, 4, 3_456.8),     # ETH: 5 significant figures
        (0.1503, 0, 0.1503),         # DOGE: used to round to 0
        (0.161_234_5, 0, 0.161_23),
        (0.001_234_56, 0, 0.001_235),  # 6 - szDecimals decimals caps it before 5 figures do
        (0.123_456, 2, 0.1235),
        (1.234_56, 2, 1.2346),
        (0, 3, 0),
        (-1, 3, 0),
    ])
    def test_examples(self, price, sz_decimals, expected):
        assert round_price(price, sz_decimals) == pytest.approx(expected, abs=0)

    def test_every_result_is_a_valid_hyperliquid_price(self):
        """Across magnitudes and szDecimals, results obey the exchange's rules and the SDK's wire format."""
        for sz_decimals in range(6):
            for exponent in range(-5, 7):
                for mantissa in (1.000_049, 1.234_567_89, 4.999_95, 9.876_543_21, 9.999_99):
                    price = mantissa * 10 ** exponent
                    rounded = round_price(price, sz_decimals)
                    if rounded == 0:
                        continue  # too small for this szDecimals; callers treat 0 as unplaceable
                    wire = Decimal(float_to_wire(rounded))  # raises if the float isn't wire-exact
                    decimals = max(-wire.normalize().as_tuple().exponent, 0)
                    if wire != wire.to_integral_value():
                        assert decimals <= 6 - sz_decimals, (price, sz_decimals, rounded)
                        assert len(wire.normalize().as_tuple().digits) <= 5, (price, sz_decimals, rounded)
                    # never further from the input than the coarsest allowed step
                    step = max(10.0 ** -(6 - sz_decimals), 10.0 ** (math.floor(math.log10(price)) - 4))
                    assert abs(rounded - price) <= step / 2 + 1e-12, (price, sz_decimals, rounded)
