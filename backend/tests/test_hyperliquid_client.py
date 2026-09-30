from unittest.mock import Mock, patch

from hyperliquid_client import HyperliquidClient


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
