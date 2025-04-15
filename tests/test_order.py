from unittest.mock import patch

import numpy as np
import pandas as pd
import pydantic
import pytest

from tradingbot.order import Order


def test_order_creation_market_buy():
    order = Order(
        action=Order.Action.BUY,
        ticker="USDT/BTC",
        amount=0.1,
        type=Order.Type.MARKET,
        created_at=pd.Timestamp("2024-01-01 00:00:00"),
        updated_at=pd.Timestamp("2024-01-01 00:00:00"),
    )
    assert order.status == Order.Status.NEW
    assert order.id_ is None
    assert np.isnan(order.exec_prc)
    assert order.msg == ""
    assert isinstance(order.created_at, pd.Timestamp)


def test_order_creation_limit_requires_price():
    with pytest.raises(pydantic.ValidationError):
        Order(
            action=Order.Action.BUY,
            ticker="USDT/BTC",
            amount=0.1,
            type=Order.Type.LIMIT,
            created_at=pd.Timestamp("2024-01-01 00:00:00"),
            updated_at=pd.Timestamp("2024-01-01 00:00:00"),
        )

    # Should pass with price
    order = Order(
        action=Order.Action.BUY,
        ticker="USDT/BTC",
        amount=0.1,
        type=Order.Type.LIMIT,
        param={"price": 30000},
        created_at=pd.Timestamp("2024-01-01 00:00:00"),
        updated_at=pd.Timestamp("2024-01-01 00:00:00"),
    )
    assert order.param["price"] == 30000


@patch("tradingbot.util.get_quote_asset", return_value="USDT")
@patch("tradingbot.util.get_base_asset", return_value="BTC")
def test_frm_and_to_asset(mock_get_base, mock_get_quote, ):
    order = Order(
        action=Order.Action.BUY,
        ticker="USDT/BTC",
        amount=1,
        type=Order.Type.MARKET,
        created_at=pd.Timestamp("2024-01-01 00:00:00"),
        updated_at=pd.Timestamp("2024-01-01 00:00:00"),
    )
    assert order.frm_asset == "USDT"
    assert order.to_asset == "BTC"

    sell_order = Order(
        action=Order.Action.SELL,
        ticker="USDT/BTC",
        amount=1,
        type=Order.Type.MARKET,
        created_at=pd.Timestamp("2024-01-01 00:00:00"),
        updated_at=pd.Timestamp("2024-01-01 00:00:00"),
    )
    assert sell_order.frm_asset == "BTC"
    assert sell_order.to_asset == "USDT"
