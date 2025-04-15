import pandas as pd

from tradingbot.transaction import Transaction


def test_init():
    Transaction(
        "BTC", 0.01, 
        "USDT", 654, 
        "USDT", 0.321, 
        "USDT/BTC",
        65432.1, 
        timestamp=pd.Timestamp("2024-01-01")
    )

# def test_bool():
#     trans = Transaction(
#         from_pos=Position(asset="BTC", qty=0.0, entry_prc=65432.1),
#         to_pos=Position(asset="USDT", qty=0.0),
#         tcost_pos=Position(asset="USDT", qty=0.0),
#     )
#     assert not trans
