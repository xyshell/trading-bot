import pandas as pd
import pytest
import tradingbot.util as util


def test_get_ticker():
    spot_ticker = "USDT/BTC"
    future_ticker = "USDT/BTC:USDT-250404"
    swap_ticker = "USDT/BTC:USDT"
    option_ticker = "USD/BTC:BTC-250404-83000-C"

    assert util.get_base_asset(spot_ticker) == "BTC"
    assert util.get_base_asset(future_ticker) == "BTC"
    assert util.get_base_asset(swap_ticker) == "BTC"
    assert util.get_base_asset(option_ticker) == "BTC"

    assert util.get_quote_asset(spot_ticker) == "USDT"
    assert util.get_quote_asset(future_ticker) == "USDT"
    assert util.get_quote_asset(swap_ticker) == "USDT"
    assert util.get_quote_asset(option_ticker) == "USD"
 
    with pytest.raises(AssertionError):
        util.get_margin_asset(spot_ticker)
    assert util.get_margin_asset(future_ticker) == "USDT"
    assert util.get_margin_asset(swap_ticker) == "USDT"
    assert util.get_margin_asset(option_ticker) == "BTC"

    with pytest.raises(AssertionError):
        util.get_expiry_date(spot_ticker)
    assert util.get_expiry_date(future_ticker) == pd.Timestamp("2025-04-04")
    with pytest.raises(AssertionError):
        assert util.get_expiry_date(swap_ticker)
    assert util.get_expiry_date(option_ticker) == pd.Timestamp("2025-04-04")

    with pytest.raises(AssertionError):
        util.get_strike_price(spot_ticker)
    with pytest.raises(AssertionError):
        util.get_strike_price(future_ticker)
    with pytest.raises(AssertionError):
        util.get_strike_price(swap_ticker)
    assert util.get_strike_price(option_ticker) == 83000
