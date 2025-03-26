import pytest


from tradingbot.exchange import CCXTExchange
from tradingbot.balance import Balance


@pytest.mark.fetch
def test_reflect():
    exchange = CCXTExchange("okx")
    balance = Balance.reflect(exchange)
    assert balance.keys()


@pytest.mark.fetch
def test_value():
    exchange = CCXTExchange("okx")
    balance = Balance.reflect(exchange)
    valued = balance.value(exchange, "USDT")
    assert valued.keys() == balance.keys()