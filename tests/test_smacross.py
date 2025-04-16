from tradingbot import Bot
from tradingbot.strategy.smacross import SMACross, SMACrossFuture
from tradingbot.trigger import StandardInterval, StrategyFirstRun
from . import assert_report


def test_smacross_backtest(snapshot):
    bot = Bot(mode="backtest", start="2024-09-01", end="2024-10-01")
    strat = SMACross(**{"ticker": "USDT/BTC", "freq": "1h", "fast": 10, "slow": 30})
    strat.next.trigger = [StrategyFirstRun(), StandardInterval(strat.param["freq"])]
    bot.add_strategy(strat)
    bot.run()

    # report
    assert_report(bot.strategy.report, snapshot)

    # plot
    fig = bot.strategy.plot()
    import matplotlib.pyplot as plt
    plt.figure(fig.number)
    # plt.show()


def test_smacrossfuture_backtest(snapshot):
    bot = Bot(mode="backtest", start="2024-09-01", end="2024-10-01")
    strat = SMACrossFuture(**{"ticker": "USDT/BTC:USDT", "freq": "1h", "fast": 10, "slow": 30})
    strat.next.trigger = [StrategyFirstRun(), StandardInterval(strat.param["freq"])]
    bot.add_strategy(strat)
    bot.run()

    # report
    assert_report(bot.strategy.report, snapshot)

    # plot
    fig = bot.strategy.plot()
    import matplotlib.pyplot as plt
    plt.figure(fig.number)
    # plt.show()


# def test_multi_backtest():
#     bot = Bot(mode="backtest", start="2024-09-01", end="2024-10-01")
#     bot.add_strategy(SMACross(ticker="USDT/BTC", capital=10))
#     bot.add_strategy(SMACross(ticker="USDT/ETH", capital=10))
#     bot.run()
