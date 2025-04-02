import pandas as pd

from tradingbot.order import Order


def test_limit_order():
    gtc_order = Order(action="BUY", ticker="USDT/BTC", size_type="BASE", size=0.001, type="LIMIT", param={"price": 12345.6})
    assert gtc_order.param["good_till"] == pd.Timedelta.max

    expired_order = Order(
        action="BUY", ticker="USDT/BTC", size_type="BASE", size=0.001, type="LIMIT", 
        param={"price": 12345.6, "good_till": "1h"},
            created_at=pd.Timestamp.utcnow() - pd.Timedelta(hours=2),
    )
    assert expired_order.created_at < pd.Timestamp.utcnow() - expired_order.param["good_till"]


def test_market_order():
    Order(action="BUY", ticker="USDT/BTC", size_type="BASE", size=0.001, type="MARKET")
