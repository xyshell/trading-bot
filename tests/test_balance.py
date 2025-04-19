from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingbot.exchange import CCXTExchange
from tradingbot.balance import Balance
from tradingbot.position import Position


NOW = pd.Timestamp("2024-01-01 00:00:00")


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
    exchange.strategy = MagicMock()
    exchange.strategy.now = NOW

    balance = Balance().reflect(exchange)
    evaluated = balance.evaluate(exchange, "USDT")
    assert evaluated["BTC"] == 12345.6 * 0.19


def make_position(amount: float, side: str = "long", entry: float = 20000, mark: float = 21000, margin: float = 1000, fee: float = 5) -> Position:
    return Position(
        ticker="BTC/USDT:USDT",
        side=side,
        amount=amount,
        leverage=5,
        entry_prc=entry,
        mark_prc=mark,
        margin=margin,
        fee=fee,
        created_at=NOW,
        updated_at=NOW,
        contract_size=1.0
    )


def test_add_spot_balance():
    b = Balance()
    b["USDT"] = 1000.0
    assert b["USDT"] == 1000.0


def test_add_position_new_side():
    b = Balance()
    pos = make_position(1.0)
    b.add_position(pos)
    assert b["BTC/USDT:USDT"]["long"].amount == 1.0


def test_add_position_combine():
    b = Balance()
    b.add_position(make_position(1.0, entry=20000))
    b.add_position(make_position(2.0, entry=22000))
    combined = b["BTC/USDT:USDT"]["long"]
    expected_entry = (1 * 20000 + 2 * 22000) / 3
    assert combined.amount == 3.0
    assert combined.entry_prc == pytest.approx(expected_entry)


def test_add_and_close_out_position():
    b = Balance()

    # Step 1: Open a long position at 20,000 with 500 margin and 3 USDT fee
    open_pos = make_position(1.0, entry=20000, margin=500, fee=3)
    b.add_position(open_pos)

    # Step 2: Close the long position at 20,000 with 2 USDT fee
    close_pos = make_position(-1.0, entry=20000, margin=0, fee=2)
    b.close_position(close_pos)

    # Step 3: After full closure, the position should no longer exist
    assert b["BTC/USDT:USDT"]["long"].amount == pytest.approx(0.0)


def test_add_position_hedged():
    b = Balance()
    b.add_position(make_position(1.0, side="long"))
    b.add_position(make_position(-1.0, side="short"))

    assert "BTC/USDT:USDT" in b
    assert "long" in b["BTC/USDT:USDT"]
    assert "short" in b["BTC/USDT:USDT"]
    assert b["BTC/USDT:USDT"]["long"].amount == pytest.approx(1.0)
    assert b["BTC/USDT:USDT"]["short"].amount == pytest.approx(-1.0)


def test_close_position_partial():
    b = Balance()
    b.add_position(make_position(1.0))
    closing = make_position(-0.5, entry=21000)
    b.close_position(closing)
    assert b["BTC/USDT:USDT"]["long"].amount == pytest.approx(0.5)


def test_close_position_fully():
    b = Balance(USDT=500.0)
    b.add_position(make_position(1.0, margin=1000, fee=5))
    b.close_position(make_position(-1.0, entry=21000, margin=1000, fee=5))
    assert b["BTC/USDT:USDT"]["long"].amount == pytest.approx(0.0)


def test_close_position_exceed_error():
    b = Balance()
    b.add_position(make_position(1.0))
    with pytest.raises(ValueError):
        b.close_position(make_position(-1.1))


def test_close_position_missing_error():
    b = Balance()
    with pytest.raises(KeyError):
        b.close_position(make_position(-1.0))


def test_set_negative_spot_balance_raises():
    b = Balance()
    with pytest.raises(ValueError):
        b["USDT"] = -10.0
