from tradingbot.model import Order


def test_limit_order():
    Order(action="BUY", ticker="USDT/BTC", size_type="BASE", size=0.001, type="LIMIT", param={"price": 12345.6})


def test_market_order():
    Order(action="BUY", ticker="USDT/BTC", size_type="BASE", size=0.001, type="MARKET")
