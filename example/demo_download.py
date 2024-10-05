"""Dummy Strategy used for downloading data"""

import math
import itertools
import logging
import pandas as pd

import tradingbot as tb

logging.getLogger("tradingbot").setLevel(logging.DEBUG)


def download(datefrom, dateto, ticker, freq, source, batch):
    timedelta = (pd.Timestamp(dateto) - pd.Timestamp(datefrom)) / batch
    freq2load_len = {f: math.ceil(timedelta / pd.Timedelta(f)) for f in freq}
    data = {
        f"candlestick_{t}_{f}": tb.data.Candlestick(source, ticker=t, freq=f, load_len=freq2load_len[f])
        for t, f in itertools.product(ticker, freq)
    }

    class DummyStrategy(tb.Strategy):
        @tb.schedule([tb.trigger.StrategyFirstRun(), tb.trigger.StandardInterval(timedelta)])
        def next(self, context):
            pass

    bot = tb.Bot(
        mode="backtest",  # or "paper" or "live"
        start=datefrom,
        end=dateto,
    )
    bot.data = data
    bot.strategy = DummyStrategy()
    bot.exchange = tb.exchange.FakeSpotExchange(commission=0.001)
    bot.account = {"USD": 10_000}
    bot.run()


if __name__ == "__main__":
    download(
        datefrom="2000-01-01",
        dateto=pd.Timestamp.now(),
        ticker=["USD/MSFT"],
        freq=[
            "1d"
        ],  # choice of '1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo'. note: intraday data cannot extend last 60 days
        source="yahoo",
        batch=10,
    )
