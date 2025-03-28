import pytest

from tradingbot.exchange import CCXTExchange
from tradingbot.balance import Balance


@pytest.mark.fetch  # TODO: mock
def test_reflect():
    exchange = CCXTExchange("okx")
    balance = Balance().reflect(exchange)
    assert balance.keys()


@pytest.mark.fetch  # TODO: mock
def test_evaluate():
    exchange = CCXTExchange("okx")
    balance = Balance().reflect(exchange)
    evaluated = balance.evaluate(exchange, "USDT")
    assert evaluated.keys() == balance.keys()

"""
Balance({
    "USDT": 10_000,
    "BTC": 0.01,
    ...
    positions = [
        "USDT/BTC:USDT": [
            {
                # attrs
                "side": "long"
                "size": 0.1
                "init_margin": 94.82  # currency can be inferred from settlement
                "margin": 94.80
                "leverage": 10
                # computed attrs
                "liquidation_prc": 94.80 / 0.1

            }
        ]
    ]
})
"""