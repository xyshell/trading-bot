import pandas as pd
from pydantic import ValidationError
import pytest
from tradingbot.model import Position, Transaction


@pytest.fixture(scope="function")
def transaction():
    trans = Transaction(
        ticker="USDT/BTC",
        prc=65432.1,
        from_=("BTC", 0.01),
        to_=("USDT", 654),
        tcost=("USDT", 0.321),
        timestamp=pd.Timestamp("2024-01-01"),
    )
    return trans


def test_invalid_transaction():
    with pytest.raises(ValidationError):
        Transaction(
            ticker="USDT/BTC",
            prc=65432.1,
            from_=("BTC", 0.01),
            to_=("USDT", 654),
            tcost=("USDT", 0.1),
            timestamp=pd.Timestamp("2024-01-01"),
        )

    with pytest.raises(ValidationError):
        Transaction(
            ticker="USDT/ETH",
            prc=65432.1,
            from_=("BTC", 0.01),
            to_=("USDT", 654),
            tcost=("USDT", 0.1),
            timestamp=pd.Timestamp("2024-01-01"),
        )


def test_init():
    Transaction(
        ticker="USDT/BTC",
        prc=65432.1,
        from_=("BTC", 0.01),
        to_=("USDT", 654),
        tcost=("USDT", 0.321),
        timestamp=pd.Timestamp("2024-01-01"),
    )  # tcost charged in quote

    Transaction(
        ticker="USDT/BTC",
        prc=65432.1,
        from_=("BTC", 0.01),
        to_=("USDT", 588.8889),
        tcost=("BTC", 0.001),
        timestamp=pd.Timestamp("2024-01-01"),
    )  # tcost charged in base

    Transaction(
        ticker="USDT/BTC",
        prc=65432.1,
        from_=("BTC", 0.01),
        to_=("USDT", 654.321),
        tcost=("USDT", 0.0),
        timestamp=pd.Timestamp("2024-01-01"),
    )  # tcost not charged

    Transaction(
        ticker="USDT/BTC",
        prc=65432.1,
        from_=("BTC", 0.01),
        to_=("USDT", 600.00),
        tcost=("BNB", 0.2),
        timestamp=pd.Timestamp("2024-01-01"),
    )  # tcost charged in other asset


def test_split(transaction):
    from_pos, to_pos, tcost_pos = transaction.split()

    assert from_pos == Position(ticker="BTC", qty=0.01, entry_prc=65432.1)
    assert to_pos == Position(ticker="USDT", qty=654)
    assert tcost_pos == Position(ticker="USDT", qty=0.321)


def test_bool():
    transaction = Transaction(
        ticker="USDT/BTC",
        prc=65432.1,
        from_=("BTC", 0.0),
        to_=("USDT", 0.0),
        tcost=("USDT", 0.0),
        timestamp=pd.Timestamp("2024-01-01"),
    )
    assert not transaction
