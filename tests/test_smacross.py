from tradingbot import Bot
from tradingbot.strategy.smacross import SMACross, SMACrossFuture

def test_smacross_backtest(snapshot):
    bot = Bot(mode="backtest", start="2024-09-01", end="2024-10-01")
    bot.add_strategy(SMACross())
    bot.run()

    # report
    report = bot.strategy.report
    assert len(report['asset']) == len(report['portfolio']) == snapshot  # timeline count
    assert report['asset'].iloc[-1].drop("timestamp").mean().round(4) == snapshot  # ending asset
    assert report['portfolio'].iloc[-1].drop("timestamp").mean().round(4) == snapshot  # ending nav
    assert report['transaction']['timestamp'].mean() == snapshot  # historical transaction
    assert report['trade']['duration'].mean() == snapshot  # historical trade
    # selected agg metrics
    assert report['summary']["trade_num"] == snapshot
    assert report['summary']["ir"].round(4) == snapshot
    assert report['summary']["expectancy"].round(4) == snapshot

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
