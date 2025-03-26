from tradingbot import Bot
from tradingbot.strategy.smacross import SMACross, SMACrossFuture


def test_smacross_backtest():
    bot = Bot(mode="backtest", start="2024-09-01", end="2024-10-01")
    bot.add_strategy(SMACross())
    bot.run()

def test_smacrossfuture_backtest():
    bot = Bot(mode="backtest", start="2024-09-01", end="2024-10-01")
    bot.add_strategy(SMACrossFuture())
    bot.run()


# def test_multi_backtest():
#     bot = Bot(mode="backtest", start="2024-09-01", end="2024-10-01")
#     bot.add_strategy(SMACross(ticker="USDT/BTC", capital=10))
#     bot.add_strategy(SMACross(ticker="USDT/ETH", capital=10))
#     bot.run()
