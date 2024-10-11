import traceback
from typing import Callable
import logging
import uuid
import warnings

import pandas as pd

import tradingbot.util as util
from tradingbot.model import Account, ModeType, DatetimeType
from tradingbot.pipeline import BacktestPipeline, PaperPipeline, LivePipeline
from tradingbot.data.core import Data, DataManager
from tradingbot.strategy import Strategy
from tradingbot.exchange import Exchange

logger = logging.getLogger(__name__)


class Bot:
    @util.validate
    def __init__(
        self,
        mode: ModeType,
        start: DatetimeType | None = None,
        end: DatetimeType | None = None,
        refresh_rate: float = 0.0,
        now_factory: Callable[[], pd.Timestamp] = util.utc_now_factory,
        **kwargs,
    ):
        """
        Args:
            mode (str): "backtest", "paper" or "live"
            start (str | datetime.datetime | pd.Timestamp, optional): start time. backtest mode only
            end (str | datetime.datetime | pd.Timestamp, optional): end time. backtest mode only
            refresh_rate (float, optional): refresh rate in seconds. paper or live mode only
            now_factory (Callable, optional): function to get current time. Defaults to pd.Timestamp.utcnow().tz_localize(None).
        """
        self._mode = mode
        self._pipeline = (
            BacktestPipeline(now_factory, start=start, end=end, **kwargs)
            if mode == "backtest"
            else PaperPipeline(now_factory, refresh_rate=refresh_rate, **kwargs)
            if mode == "paper"
            else LivePipeline(now_factory, refresh_rate=refresh_rate, **kwargs)
        )
        self._start = start
        self._end = end
        self._now_factory = now_factory

        self._data: dict[str, Data] = {}
        self._strategy: Strategy = None
        self._exchange: Exchange = None
        self._account: Account = None
        if data := kwargs.pop("data", None):
            self.data = data
        if strategy := kwargs.pop("strategy", None):
            self.strategy = strategy
        if exchange := kwargs.pop("exchange", None):
            self.exchange = exchange
        if account := kwargs.pop("account", None):
            self.account = account

        self._id = str(uuid.uuid4())
        logger.debug(f"Bot(ID={id(self)}) Created: Mode='{self._mode}'")

    @property
    def mode(self) -> ModeType:
        return self._mode

    @property
    def data(self) -> dict[str, Data]:
        return self._data

    @data.setter
    @util.validate
    def data(self, value: dict[str, Data]):
        self._data = DataManager(value, mode=self._mode)

    @property
    def strategy(self) -> Strategy | dict[str, Strategy]:
        return self._strategy

    @strategy.setter
    @util.validate
    def strategy(self, strategy: Strategy | dict[str, Strategy]):
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

    def run(self, plot: bool | dict = False, **kwargs) -> None:
        """Run the bot.
        Args:
            plot (bool | dict, optional): if True, plot results. Defaults to False.
        """
        strategy = self._strategy
        # set strategy
        strategy.data = self._data
        strategy.exchange = self._exchange
        strategy.account = self._account
        # set exchange
        self._exchange.strategy = strategy
        # run pipeline
        self._pipeline.run(strategy, plot=plot, **kwargs)

    def optimize(self, strategy: dict[str, Strategy], engine: str = "dask", errors: str = "warn", **kwargs) -> None:
        """optimize multiple strategies
        Args:
            errors (str, optional): "ignore", "warn" or "raise"
            **kwargs: passed to bot.run(**kwargs)
        """
        assert engine == "dask", f"only engine='dask' is supported, got {engine=}"
        import dask

        def _bot_run(bot, strategy, **kwargs) -> Strategy:
            bot.strategy = strategy
            try:
                bot.run(**kwargs)
            except Exception as exc:
                if errors == "warn":
                    msg = traceback.format_exc()
                    warnings.warn(f"{strategy} failed, due to {exc!r}\n{msg}")
                elif errors == "raise":
                    raise
                else:  # ignore
                    pass
            return bot.strategy

        jobs = [dask.delayed(_bot_run)(self, strategy, **kwargs) for strategy in strategy.values()]
        results = dask.compute(*jobs, scheduler="processes")

        for name, res in zip(strategy.keys(), results):
            strategy[name] = res

        self.strategy = strategy
