import collections
import copy
import time
from typing import Callable, Dict, Type
import concurrent.futures
import logging
import uuid
import warnings

import numpy as np
import pandas as pd

from tradingbot.data.candlestick import Candlestick
import tradingbot.util as util
from tradingbot.model import Account, ModeType, DatetimeType, Order
from tradingbot.data.core import Data
from tradingbot.strategy import Strategy
from tradingbot.exchange import Exchange
from tradingbot.trigger import StandardInterval
from tradingbot.reporter import Reporter

logger = logging.getLogger(__name__)


class Bot:
    @util.validate
    def __init__(
        self,
        mode: ModeType,
        start: DatetimeType,
        end: DatetimeType,
        refresh_rate: float = 0.0,
        now_factory: Callable = lambda: pd.Timestamp.utcnow().tz_localize(None),
        **kwargs,
    ):
        """
        Args:
            mode (str): "backtest", "paper" or "live"
            start (str | datetime.datetime | pd.Timestamp, optional): start time. backtest mode only
            end (str | datetime.datetime | pd.Timestamp, optional): end time. backtest mode only
            refresh_rate (float, optional): refresh rate in seconds.
            now_factory (Callable, optional): function to get current time. Defaults to pd.Timestamp.utcnow. paper and live mode only
        """
        self._mode = mode
        self._start = start
        self._end = min(end, now_factory())
        self._refresh_rate = refresh_rate
        self._now_factory = now_factory

        self._data: Dict[str, Data] = {}
        self._strategy: Strategy = None
        self._exchange: Exchange = None
        self._account: Account = None
        self._reporter: Type[Reporter] = None
        if data := kwargs.pop("data", None):
            self.data = data
        if strategy := kwargs.pop("strategy", None):
            self.strategy = strategy
        if exchange := kwargs.pop("exchange", None):
            self.exchange = exchange
        if account := kwargs.pop("account", None):
            self.account = account
        if reporter := kwargs.pop("reporter", None):
            self.reporter = reporter

        self._id = str(uuid.uuid4())
        logger.debug(f"Bot(ID={id(self)}) Created: Mode='{self._mode}'")

    @property
    def mode(self) -> ModeType:
        return self._mode

    @property
    def data(self) -> Dict[str, Data]:
        return self._data

    @data.setter
    @util.validate
    def data(self, data: Dict[str, Data]):
        self._data = data
        for data in self._data.values():
            data.mode = self._mode
        candlestick_data = [data for data in self._data.values() if isinstance(data, Candlestick)]
        assert candlestick_data, "Data must contain at least one tb.data.Candlestick()"

        ticker2min_freq = collections.defaultdict(lambda: pd.Timedelta.max)
        ticker2data = {}  # reference ticker to the candlestick with highest frequency
        for data in candlestick_data:
            if pd.Timedelta(data.freq) < ticker2min_freq[data.ticker]:
                ticker2min_freq[data.ticker] = pd.Timedelta(data.freq)
                ticker2data[data.ticker] = data
        self._ticker2data = ticker2data

    @property
    def strategy(self) -> Strategy:
        return self._strategy

    @strategy.setter
    @util.validate
    def strategy(self, strategy: Strategy):
        self._strategy = strategy

    @property
    def exchange(self) -> Exchange:
        return self._exchange

    @exchange.setter
    @util.validate
    def exchange(self, exchange: Exchange):
        self._exchange = exchange

    @property
    def account(self) -> Account:
        return self._account

    @account.setter
    @util.validate
    def account(self, wealth: dict | Account) -> Account:
        self._account = Account.create(wealth) if isinstance(wealth, dict) else wealth

    @property
    def reporter(self) -> Type[Reporter]:
        return self._reporter

    @reporter.setter
    @util.validate
    def reporter(self, reporter: Type[Reporter] | None):
        self._reporter = reporter

    def get_now_generator(self):
        if self._mode == "backtest":
            standard_interval = list(filter(lambda x: isinstance(x, StandardInterval), self._strategy.next.trigger))
            freq = min(trigger.interval for trigger in standard_interval)

            def now_generator():
                for datetime in pd.date_range(start=self._start, end=self._end, freq=freq):
                    yield datetime
        else:

            def now_generator():
                yield self._now_factory()

        return now_generator

    def update_data(self, now: pd.Timestamp, **kwargs):
        tic = time.time()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(data.update, now): data for data in self.data.values()}
            for future in concurrent.futures.as_completed(futures):
                data = futures[future]
                result = future.result()
                logger.debug(f"Data Update: complete for {data.__class__.__name__}({data.field}): {result=}")
        toc = time.time()
        logger.debug(f"Data Update: took {toc - tic:.2f} seconds")

    def plot(self, engine="matplotlib", **kwargs):
        assert engine == "matplotlib", f"{engine=} not supported"

        import mplfinance as mpf

        # analyze results
        port_report = self.strategy.report["portfolio"]
        order_report = self.strategy.report["order"].query("status == 'FILLED'")
        sample_freq = util.inferred_freq2freq(port_report.index.inferred_freq)
        candlestick = next(data for data in self.data.values() if isinstance(data, Candlestick) and data.freq == sample_freq)
        candlestick_df = candlestick.load(now=port_report.index[-1], load_len=len(port_report))
        df = pd.merge_asof(port_report, candlestick_df, right_on="close_time", left_index=True)
        buy_sell = order_report["action"].to_frame()
        buy_sell["one"] = 1
        df = pd.concat([df, buy_sell.pivot(columns="action", values="one")], axis=1)
        df["BUY"] = (df["BUY"] * df["close"]) if "BUY" in df.columns else np.nan
        df["SELL"] = (df["SELL"] * df["close"]) if "SELL" in df.columns else np.nan
        if "volume" not in df.columns and "base_volume" in df.columns:
            df.rename(columns={"base_volume": "volume"}, inplace=True)
        df.drop_duplicates(subset=["ticker", "close_time"], keep="last", inplace=True)
        # fmt: off
        fig, axlist = mpf.plot(
            df,
            type="candle",
            style="charles",
            volume=True,
            volume_alpha=0.3,
            title="Backtest Report",
            main_panel=1,
            volume_panel=2,
            figsize=(15.5, 7),
            tight_layout=True,
            scale_padding={"left": 0.2, "right": 1.0, "top": 0.5, "bottom": 0.5},
            xrotation=0,
            datetime_format="%y/%m/%d %H:%M",
            addplot=[
                mpf.make_addplot(df["nav"], panel=0, alpha=1.0, color="b", label="NAV"),
                *[mpf.make_addplot(df[col], panel=0, alpha=0.4, secondary_y=False, label=col) for col in port_report.columns if col != "nav"],
                mpf.make_addplot(df["BUY"], panel=1, type="scatter", markersize=50, marker="^", color="#6cfa5f", secondary_y=False, label="BUY"),
                mpf.make_addplot(df["SELL"], panel=1, type="scatter", markersize=50, marker="v", color="#fa5f7e", secondary_y=False, label="SELL"),
            ],
            warn_too_much_data=len(df),
            returnfig=True
        )
        with util.set_level(logging.getLogger("matplotlib.legend"), logging.ERROR), warnings.catch_warnings():
            warnings.filterwarnings(
                action="ignore", category=UserWarning, message="No artists with labels found to put in legend"
            )
            for ax in axlist:
                _ = ax.tick_params(axis="x", labelsize=5)
                _ = ax.tick_params(axis="y", labelsize=5)
                _ = ax.legend(loc="upper left", fontsize=6)
        # fmt: on

    def run(self, plot: bool | dict = False):  # TODO: class hierarchy of pipeline for different modes
        now_generator = self.get_now_generator()

        strategy = self._strategy

        # set strategy
        strategy.data = self._data
        strategy.ticker2data = self._ticker2data
        strategy.exchange = self._exchange
        strategy.account = self._account

        # set exchange
        self._exchange.strategy = strategy

        while True:
            strategy.start()

            for now in now_generator():
                tic = time.time()
                if self._mode == "backtest" and now > self._end:
                    break

                # check trigger status
                triggered = []
                for tri in strategy.next.trigger:
                    if tri.check(now):
                        triggered.append(tri)

                if any(triggered):
                    logger.info(f"Now Triggered ⌚'{now}': {strategy} by {triggered}")

                    # prepare info
                    self.update_data(now)

                    # call strategy
                    orders = strategy.next(context={"now": now, "trigger": triggered, "pending_order": self.strategy.pending_order})

                    # execute orders
                    orders = util.to_list(orders) + self.strategy.pending_order
                    for order in orders:
                        self.exchange.execute(now, order)
                    for order in orders:
                        if order.status in {Order.Status.FILLED, Order.Status.REJECTED, Order.Status.CANCELED, Order.Status.EXPIRED}:
                            self.strategy.order_history[now] = order
                        elif order.status is Order.Status.PARTIAL_FILLED:
                            self.strategy.pending_order.add(order)

                # collect result
                # update market price for position
                for pos in self.strategy.account.position:
                    for ticker, data in self._ticker2data.items():
                        if pos.ticker in ticker and pos.ticker != util.get_quote_ticker(ticker):
                            pos.market_prc = data["close"].iloc[-1]
                # archive position
                self.strategy.account_history[now] = copy.deepcopy(self.strategy.account)

                toc = time.time()
                logger.debug(f"Run {now}: took {toc - tic:.2f} seconds")
                time.sleep(0 if self._mode == "backtest" else self._refresh_rate)

            # build report
            Reporter.set(self.strategy)
            Reporter.display(self.strategy)

            strategy.stop()
            break

        if plot:
            plot = {} if isinstance(plot, bool) else plot
            self.plot(**plot)
