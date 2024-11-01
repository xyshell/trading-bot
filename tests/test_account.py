
from tradingbot.model import Account, Position


def test_create():
    account = Account.create({"USDT": 1000})
    assert account.position == [Position(ticker="USDT", qty=1000)]


def test_get():
    account = Account([Position(ticker="USDT", qty=1000)])
    assert account["USDT"].qty == 1000
    assert account["BTC"].qty == 0 and account["BTC"].entry_prc == 0
    assert "BTC" not in [pos.ticker for pos in account.position]


def test_add():
    account = Account([Position(ticker="BTC", qty=0.01, entry_prc=12345.6), Position(ticker="USDT", qty=1000)])

    account += Position(ticker="BTC", qty=0.02, entry_prc=65432.1)
    assert account["BTC"].qty == 0.03
    assert account["BTC"].entry_prc == (12345.6 * 0.01 + 65432.1 * 0.02) / 0.03

    account += Position(ticker="USDT", qty=2000)
    assert account["USDT"].qty == 3000
    assert account["USDT"].entry_prc == 0.0


def test_sub():
    account = Account([Position(ticker="BTC", qty=0.01, entry_prc=12345.6), Position(ticker="USDT", qty=1000)])

    account -= Position(ticker="BTC", qty=0.005, entry_prc=65432.1)
    assert account["BTC"].qty == 0.005
    assert account["BTC"].entry_prc == (12345.6 * 0.01 - 65432.1 * 0.005) / 0.005

    account -= Position(ticker="BTC", qty=0.02, entry_prc=65432.1)
    assert account["BTC"].qty == -0.015
    assert account["BTC"].entry_prc == 65432.1
    assert not account.all_sufficient()


def test_all_sufficient():
    account = Account([Position(ticker="BTC", qty=0.01, entry_prc=12345.6), Position(ticker="USDT", qty=1000)])
    assert account.all_sufficient()
