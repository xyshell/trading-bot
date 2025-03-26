
import pytest
from tradingbot.account import Account
from tradingbot.position import Position, SpotPosition


def test_init():
    account = Account(base_currency="USDT")
    assert account.positions == {}


def test_position():
    account = Account(base_currency="USDT")
    account.add_position(Position(asset="USDT", qty=1000))
    account.add_position(Position(asset="BTC", qty=0.01))

    assert "USDT" in account and "BTC" in account
    assert account["USDT"].qty == 1000
    assert account["BTC"].qty == 0.01

    with pytest.raises(KeyError):
        account["ETH"]

    account["BTC"] = Position(asset="BTC", qty=0.02)
    assert account["BTC"].qty == 0.02

    with pytest.raises(AssertionError):
        account["BTC"] = Position(asset="ETH", qty=0.02)

    for pos in account.positions.values():
        assert isinstance(pos, Position)

    new_account = account + Position(asset="USDT", qty=1000)
    assert new_account["USDT"].qty == 2000
    assert new_account is not account

    new_account2 = account - Position(asset="USDT", qty=500)
    assert new_account2["USDT"].qty == 500
    assert new_account2 is not account


def test_add_spot_position():
    account = Account(base_currency="USDT")
    account.add_position(Position(asset="USDT", qty=1000))
    account.add_position(SpotPosition(asset="BTC", qty=0.01, entry_cost=Position(asset="USDT", qty=12345.6)))

    assert account["BTC"].market_value == Position(asset="USDT", qty=12345.6)
    
    account.add_position(SpotPosition(asset="BTC", qty=0.01, entry_cost=Position(asset="USDT", qty=65432.1)))
    assert account["BTC"].entry_cost.qty == (12345.6 + 65432.1) / 2


def test_is_sufficient():
    account = Account(base_currency="USDT")
    account.add_position(Position(asset="USDT", qty=1000))
    account.add_position(SpotPosition(asset="BTC", qty=0.01, entry_cost=Position(asset="USDT", qty=12345.6)))

    assert account.is_sufficient()

    new_account = account - SpotPosition(asset="BTC", qty=0.02, entry_cost=Position(asset="USDT", qty=12345.6))
    assert not new_account.is_sufficient()
