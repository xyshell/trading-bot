import copy
import os
import traceback
from typing import Callable
import logging
import uuid
import warnings

import dask.diagnostics
import pandas as pd
import sqlalchemy as sa

import tradingbot.util as util
from tradingbot.model import Account, ModeType, DatetimeType
from tradingbot.pipeline import BacktestPipeline, LivePipeline
from tradingbot.data.core import Data, DataManager
from tradingbot.strategy import Strategy
from tradingbot.exchange import Exchange
from tradingbot.database import Database

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
            mode (str): "backtest", or "live"
            start (str | datetime.datetime | pd.Timestamp, optional): start time. backtest mode only
            end (str | datetime.datetime | pd.Timestamp, optional): end time. backtest mode only
            refresh_rate (float, optional): refresh rate in seconds. live mode only
            now_factory (Callable, optional): function to get current time. Defaults to pd.Timestamp.utcnow().tz_localize(None).
        """
        self._mode = mode
        self._pipeline = (
            BacktestPipeline(now_factory, start=start, end=end, **kwargs)
            if mode == "backtest"
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

    def optimize(
        self,
        strategy: dict[str, Strategy],
        engine: str = "dask",
        errors: str = "warn",
        num_workers: int = os.cpu_count(),
        if_exists: str = "ignore",
        **kwargs,
    ) -> None:
        """optimize multiple strategies
        Args:
            strategy (dict[str, Strategy]): strategies to optimize
            engine (str, optional): "dask". Defaults to "dask".
            errors (str, optional): "ignore", "warn" or "raise"
            num_workers (int, optional): number of workers. Defaults to os.cpu_count().
            if_exists (str, optional): what to do if the key already exists in opt result table.
                "ignore", "replace" or "raise". Defaults to "ignore".
            **kwargs: passed to bot.run(**kwargs)
        """
        assert engine == "dask", f"only engine='dask' is supported, got {engine=}"
        import dask

        def _bot_run(bot, strategy, **kwargs) -> Strategy:
            key = f"{strategy}_{bot._start:%Y%m%d}_{bot._end:%Y%m%d}"
            engine = Database.get_engine()
            table = Database.get_opt_table()
            if if_exists in {"ignore", "raise"}:
                sql = sa.select(table.c.key).where(table.c.key == key)
                res = engine.connect().execute(sql).fetchall()
                if res and if_exists == "raise":
                    raise KeyError(f"{key} already exists.")
                elif res and if_exists == "ignore":
                    logger.info(f"{key} already exists, skipped")
                    return bot.strategy

            bot.strategy = strategy
            for trigger in bot.strategy.next.trigger:
                trigger.checked.clear()
            try:
                logger.info(f"Optimizing: {key=}")
                with util.set_level(logging.getLogger("tradingbot"), logging.WARNING):
                    bot.run(**kwargs)
            except AssertionError as exc:
                logger.info(f"{key=} bypassed due to {exc!r}")
            except Exception as exc:
                if errors == "warn":
                    msg = traceback.format_exc()
                    warnings.warn(f"{strategy} failed, due to {exc!r}\n{msg}")
                elif errors == "raise":
                    raise
                else:  # ignore
                    pass
            else:
                stats = bot.strategy.report["stats"]
                stats["strategy"] = str(stats["strategy"])
                insert_stmt = sa.dialects.sqlite.insert(table).values(
                    {"key": key, "strategy": strategy.__class__.__name__, "stats": stats.to_json()}
                )
                upsert_stmt = insert_stmt.on_conflict_do_update(
                    index_elements=[table.c.key], set_={col.key: col for col in table.columns if col not in [table.c.key]}
                )
                with engine.connect() as conn:
                    result = conn.execute(upsert_stmt)
                    conn.commit()
                    logger.debug(f"upsert affected {result.rowcount} rows in {table.name}")

                logger.info(f"Done: {key=}")
            finally:
                return bot.strategy

        jobs = [dask.delayed(_bot_run)(copy.deepcopy(self), copy.deepcopy(strat), **kwargs) for strat in strategy.values()]
        with dask.diagnostics.ProgressBar():
            results = dask.compute(*jobs, scheduler="processes", num_workers=num_workers)

        for name, res in zip(strategy.keys(), results):
            strategy[name] = res

        self.strategy = strategy
