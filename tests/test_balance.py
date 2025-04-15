from unittest.mock import patch

from tradingbot.exchange import CCXTExchange
from tradingbot.balance import Balance


@patch("tradingbot.exchange.ccxt.CCXTExchange.client")
def test_reflect(mock_client):
    mock_client.fetch_balance.return_value = {
        "free": {"USDT": 1009.9, "BTC": 0.19, "ETH": 0.2},
        "used": {"USDT": 0.0, "BTC": 0.0, "ETH": 0.1},
        "total": {"USDT": 1009.9, "BTC": 0.19, "ETH": 0.3},
    }

    exchange = CCXTExchange()
    balance = Balance().reflect(exchange, "total")
    assert balance["USDT"] == 1009.9
    assert balance["BTC"] == 0.19
    assert balance["ETH"] == 0.3

    balance = Balance().reflect(exchange, "free", {"ETH"})
    assert balance["ETH"] == 0.2


@patch("tradingbot.exchange.ccxt.CCXTExchange.client")
def test_evaluate(mock_client):
    mock_client.fetch_balance.return_value = {
        "free": {"BTC": 0.19},
        "used": {"BTC": 0.0},
        "total": {"BTC": 0.19},
    }
    mock_client.load_markets.return_value = {
        "USDT/BTC": {"quote": "USDT", "base": "BTC", "symbol": "BTC/USDT", "type": "spot"}
    }
    mock_client.fetch_tickers.return_value = {
        "BTC/USDT": {"last": 12345.6}
    }

    exchange = CCXTExchange()
    balance = Balance().reflect(exchange)
    evaluated = balance.evaluate(exchange, "USDT")
    assert evaluated["BTC"] == 12345.6 * 0.19

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