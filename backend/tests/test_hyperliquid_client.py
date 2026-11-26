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


# The shape Hyperliquid's public API returned for clearinghouseState (values changed)
CLEARINGHOUSE_STATE = {
    "marginSummary": {"accountValue": "565.136441", "totalNtlPos": "0.0", "totalRawUsd": "565.136441", "totalMarginUsed": "12.5"},
    "crossMarginSummary": {"accountValue": "565.136441", "totalNtlPos": "0.0", "totalRawUsd": "565.136441", "totalMarginUsed": "12.5"},
    "crossMaintenanceMarginUsed": "0.0",
    "withdrawable": "552.636441",
    "assetPositions": [],
    "time": 1795720770763,
}
ACCOUNT = "0x" + "11" * 20
AGENT_KEY = "0x" + "22" * 32


def _connect(keychain, network="mainnet", with_key=True):
    import connection
    connection.save_account(ACCOUNT, network)
    if with_key:
        connection.save_agent_key(AGENT_KEY)
    client = HyperliquidClient()
    return client


# A unified account's spot state, as Hyperliquid returned it for a real account holding 4.98 USDC
SPOT_STATE = {"balances": [{"coin": "USDC", "token": 0, "total": "4.98", "hold": "0.0", "entryNtl": "0.0"}],
              "tokenToAvailableAfterMaintenance": [[0, "4.98"]]}
EMPTY_PERP_STATE = {**CLEARINGHOUSE_STATE, "withdrawable": "0.0",
                    "marginSummary": {"accountValue": "0.0", "totalNtlPos": "0.0", "totalRawUsd": "0.0", "totalMarginUsed": "0.0"}}


def _info_api(mode, perp=CLEARINGHOUSE_STATE, spot=SPOT_STATE):
    """A fake /info endpoint answering by request type."""
    answers = {"userAbstraction": mode, "clearinghouseState": perp, "spotClearinghouseState": spot}
    return lambda url, json, timeout: _response(answers[json["type"]])


def _position(coin, unrealized):
    return {"type": "oneWay", "position": {"coin": coin, "szi": "0.01", "unrealizedPnl": str(unrealized)}}


class TestAccountSummary:
    @patch("hyperliquid_client.requests.post")
    def test_standard_account_uses_the_perp_balance_and_caches(self, mock_post, keychain):
        mock_post.side_effect = _info_api("default")
        client = _connect(keychain, with_key=False)

        summary = client.get_account_summary()
        client.get_account_summary()

        assert summary["account_value"] == pytest.approx(565.136441)
        assert summary["withdrawable"] == pytest.approx(552.636441)
        assert summary["margin_used"] == pytest.approx(12.5)
        assert summary["account_mode"] == "default"
        assert mock_post.call_count == 2  # mode + perp state; the second summary came from the cache
        assert all(call.args[0] == "https://api.hyperliquid.xyz/info" for call in mock_post.call_args_list)
        assert {"type": "clearinghouseState", "user": ACCOUNT} in [c.kwargs["json"] for c in mock_post.call_args_list]

    @pytest.mark.parametrize("mode", ["unifiedAccount", "portfolioMargin"])
    @patch("hyperliquid_client.requests.post")
    def test_unified_account_uses_the_spot_usdc_balance(self, mock_post, keychain, mode):
        """A deposit into a unified account lands in spot; the perp state shows $0."""
        mock_post.side_effect = _info_api(mode, perp=EMPTY_PERP_STATE)

        summary = _connect(keychain, with_key=False).get_account_summary()

        assert summary["account_value"] == pytest.approx(4.98)
        assert summary["withdrawable"] == pytest.approx(4.98)
        assert summary["margin_used"] == 0
        assert summary["account_mode"] == mode

    @patch("hyperliquid_client.requests.post")
    def test_unified_account_does_not_add_unrealized_pnl_twice(self, mock_post, keychain):
        """Observed on a real unified account with an open BTC long: the spot USDC total already
        includes the position's unrealized P&L (4.915609 + -0.034440), so nothing is added to it."""
        spot = {"balances": [{"coin": "USDC", "token": 0, "total": "4.881169", "hold": "3.676045", "entryNtl": "0.0"},
                             {"coin": "HYPE", "token": 150, "total": "3.0", "hold": "0.0", "entryNtl": "90.0"}],
                "tokenToAvailableAfterMaintenance": [[0, "1.237104"]]}
        perp = {**EMPTY_PERP_STATE, "assetPositions": [_position("BTC", -0.03444)]}
        mock_post.side_effect = _info_api("unifiedAccount", perp=perp, spot=spot)

        summary = _connect(keychain, with_key=False).get_account_summary()

        assert summary["account_value"] == pytest.approx(4.881169)  # HYPE isn't counted
        assert summary["withdrawable"] == pytest.approx(1.237104)
        assert summary["margin_used"] == pytest.approx(3.676045)

    @patch("hyperliquid_client.requests.post")
    def test_unified_account_without_usdc_is_zero(self, mock_post, keychain):
        mock_post.side_effect = _info_api("unifiedAccount", perp=EMPTY_PERP_STATE, spot={"balances": []})

        assert _connect(keychain, with_key=False).get_account_summary()["account_value"] == 0

    @patch("hyperliquid_client.requests.post")
    def test_account_mode_is_cached_between_balance_refreshes(self, mock_post, keychain):
        mock_post.side_effect = _info_api("default")
        client = _connect(keychain, with_key=False)

        client.get_account_summary()
        client._account_summary = None  # balance cache expired
        client.get_account_summary()

        modes = [c for c in mock_post.call_args_list if c.kwargs["json"]["type"] == "userAbstraction"]
        assert len(modes) == 1


class TestConnectedClient:

    @patch("hyperliquid_client.requests.post")
    def test_testnet_uses_the_testnet_api(self, mock_post, keychain):
        mock_post.return_value = _response({"BTC": "1"})
        client = _connect(keychain, network="testnet", with_key=False)

        client.get_current_price("BTC")

        assert mock_post.call_args.args[0] == "https://api.hyperliquid-testnet.xyz/info"

    def test_address_only_is_read_only(self, keychain):
        client = _connect(keychain, with_key=False)
        with patch("hyperliquid_client.Info"), patch("hyperliquid_client.Exchange") as exchange:
            assert client.enabled is True
            assert client.can_trade is False
            exchange.assert_not_called()

    def test_api_wallet_trades_for_the_account(self, keychain):
        client = _connect(keychain)
        with patch("hyperliquid_client.Info"), patch("hyperliquid_client.Exchange") as exchange, \
                patch("hyperliquid_client.fetch_user_role", return_value={"role": "user"}):
            assert client.can_trade is True
        wallet, base_url = exchange.call_args.args
        assert wallet.key.hex().removeprefix("0x") == AGENT_KEY.removeprefix("0x")
        assert exchange.call_args.kwargs == {"account_address": ACCOUNT}

    def test_sub_account_trades_through_its_master(self, keychain):
        master = "0x" + "99" * 20
        client = _connect(keychain)
        with patch("hyperliquid_client.Info"), patch("hyperliquid_client.Exchange") as exchange, \
                patch("hyperliquid_client.fetch_user_role", return_value={"role": "subAccount", "data": {"master": master}}):
            assert client.can_trade is True
        assert exchange.call_args.kwargs == {"account_address": master, "vault_address": ACCOUNT}

    def test_reload_picks_up_new_settings(self, keychain):
        import connection
        client = HyperliquidClient()
        assert client.enabled is False

        connection.save_account(ACCOUNT, "mainnet")
        client.reload()

        assert client.wallet_address == ACCOUNT


class TestFeeRates:
    @patch("hyperliquid_client.requests.post")
    def test_applies_the_referral_discount_and_caches(self, mock_post, keychain):
        # What Hyperliquid returned for a real account; its fills were charged 0.0432%
        mock_post.return_value = _response({"userCrossRate": "0.00045", "userAddRate": "0.00015", "activeReferralDiscount": "0.04"})
        client = _connect(keychain, with_key=False)

        rates = client.get_fee_rates()
        client.get_fee_rates()

        assert rates == {"taker": pytest.approx(0.000432), "maker": pytest.approx(0.000144)}
        assert mock_post.call_count == 1
        assert mock_post.call_args.kwargs["json"] == {"type": "userFees", "user": ACCOUNT}

    def test_without_an_account_planning_uses_the_base_tier(self):
        import fees
        assert fees.current_rates(HyperliquidClient()) == {"taker": 0.00045, "maker": 0.00015, "stop_slippage": 0.0005, "source": "default"}

    def test_falls_back_to_the_base_tier_if_hyperliquid_is_unreachable(self):
        import fees
        from unittest.mock import Mock
        client = Mock(enabled=True)
        client.get_fee_rates.side_effect = RuntimeError("timeout")
        assert fees.current_rates(client)["source"] == "default"
