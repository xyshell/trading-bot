from tradingbot import Bot
from tradingbot.strategy.smacross import SMACross, SMACrossFuture
from . import assert_report


def test_smacross_backtest(snapshot):
    bot = Bot(mode="backtest", start="2024-09-01", end="2024-10-01")
    bot.add_strategy(SMACross())
    bot.run()

    # report
    assert_report(bot.strategy.report, snapshot)

    # plot
    fig = bot.strategy.plot()
    import matplotlib.pyplot as plt
    plt.figure(fig.number)


def test_smacrossfuture_backtest():
    bot = Bot(mode="backtest", start="2024-09-01", end="2024-10-01")
    bot.add_strategy(SMACrossFuture())
    bot.run()


# def test_multi_backtest():
#     bot = Bot(mode="backtest", start="2024-09-01", end="2024-10-01")
#     bot.add_strategy(SMACross(ticker="USDT/BTC", capital=10))
#     bot.add_strategy(SMACross(ticker="USDT/ETH", capital=10))
#     bot.run()
