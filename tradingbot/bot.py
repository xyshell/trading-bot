import copy
import importlib
import os
import traceback
from typing import Callable
import logging
import uuid
import warnings

import pandas as pd
import sqlalchemy as sa

from tradingbot.exchange.fake import FakeExchange
import tradingbot.util as util
from tradingbot.model import Account, MarginAccount, ModeType, DatetimeType
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
        now_factory: Callable[[], pd.Timestamp] = util.utc_now_factory,
        *_,
        # backtest mode
        start: DatetimeType | None = None,
        end: DatetimeType | None = None,
        preload: bool = False,
        # live mode
        refresh_rate: float = 0.0,
        _reflect_account: bool = True,
        **kwargs,
    ):
        """
        Args:
            mode (str): "backtest" or "live"
            now_factory (Callable, optional): function to get current time. Defaults to pd.Timestamp.utcnow().tz_localize(None).
            
            # backtest mode
            preload (bool, optional): whether to preload data to speed up in backtest mode 
            start (str | datetime.datetime | pd.Timestamp, optional): backtest start time
            end (str | datetime.datetime | pd.Timestamp, optional): backtest end time

            # live mode
            refresh_rate (float, optional): refresh rate in seconds.
            _reflect_account (bool, optional): whether to reflect from actual account in live mode
        """
        self._mode = mode
        self._pipeline = (
            BacktestPipeline(now_factory, start=start, end=end, **kwargs)
            if mode == "backtest"
            else LivePipeline(now_factory, refresh_rate=refresh_rate, _reflect_account=_reflect_account, **kwargs)
        )
        self._start = start
        self._end = end
        self._now_factory = now_factory
        self._preload = preload
        self._reflect_account = _reflect_account

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
    def account(self) -> Account | MarginAccount:
        return self._account

    @account.setter
    @util.validate
    def account(self, wealth: dict | Account | MarginAccount):
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
        strategy.init_account = self._account
        strategy.account = self._account
        # set exchange
        self._exchange.strategy = strategy

        if self.mode == "backtest":
            assert isinstance(strategy.exchange, FakeExchange), "Can't use real exchange in backtest mode"
        # run pipeline
        self._pipeline.run(strategy, plot=plot, preload=self._preload, **kwargs)

    def optimize(
        self,
        strategy: dict[str, Strategy],
        engine: str = "dask",
        errors: str = "warn",
        persist: bool = True,
        if_exists: str = "ignore",
        remote: bool = False,
        restart: bool = False,
        block: bool = False,
        n_workers: int = os.cpu_count(),
        scheduler_url: str | None = None,
        **kwargs,
    ) -> None:
        """optimize multiple strategies
        Args:
            strategy (dict[str, Strategy]): strategies to optimize
            engine (str, optional): "dask". Defaults to "dask".
            errors (str, optional): "ignore", "warn" or "raise"
            persist (bool, optional): persist results to database. Defaults to True. if True, results are not returned.
            if_exists (str, optional): only when persist is True, what to do if the key already exists in opt result table.
                "ignore", "replace" or "raise". Defaults to "ignore".
            remote (bool, optional): if True, run on remote cluster. Defaults to False.
            restart (bool, optional): if True, restart cluster. Defaults to False.
            block (bool, optional): if True, block until finished. Defaults to False.
            scheduler_url (str, optional): dask scheduler url. Defaults to use config.toml dask_scheduler_url.
            n_workers (int, optional): only when scheduler_url is None, specify number of workers using LocalCluster. Defaults to os.cpu_count().
            **kwargs: passed to bot.run(**kwargs)
        """
        assert engine == "dask", f"only engine='dask' is supported, got {engine=}"
        from dask.distributed import Client, LocalCluster, fire_and_forget, wait
        from tradingbot import config

        scheduler_url = scheduler_url or config.general.dask_scheduler_url
        if not remote or not scheduler_url:
            client = Client(LocalCluster(n_workers=n_workers))
        else:
            client = Client(scheduler_url)
            if restart:
                client.restart()
        client.forward_logging("tradingbot")

        def _bot_run_persist(bot, strat, **kwargs) -> Strategy:
            key = f"{strat}_{bot._start:%Y%m%d}_{bot._end:%Y%m%d}"
            engine = Database.get_engine()
            table = Database.get_opt_table()
            if if_exists in {"ignore", "raise"}:
                sql = sa.select(table.c.key).where(table.c.key == key)
                with engine.connect() as conn:
                    res = conn.execute(sql).fetchall()
                if res and if_exists == "raise":
                    raise KeyError(f"{key} already exists.")
                elif res and if_exists == "ignore":
                    logger.info(f"{key} already exists, skipped")
                    return bot.strategy

            bot.strategy = strat
            try:
                logger.info(f"Optimizing: {key=}")
                with util.set_level(logging.getLogger("tradingbot"), logging.WARNING):
                    bot.run(**kwargs)
            except AssertionError as exc:
                logger.info(f"{key=} bypassed due to {exc!r}")
            except Exception as exc:
                if errors == "warn":
                    msg = traceback.format_exc()
                    warnings.warn(f"{strat} failed, due to {exc!r}\n{msg}")
                elif errors == "raise":
                    raise
                else:  # ignore
                    pass
            else:
                stats = bot.strategy.report["stats"]
                stats["strategy"] = str(stats["strategy"])
                sqlalchemy_dialect = importlib.import_module(f"sqlalchemy.dialects.{engine.dialect.name}")
                insert = sqlalchemy_dialect.insert
                insert_stmt = insert(table).values(
                    {"key": key, "strategy": strat.__class__.__name__, "stats": stats.to_json()}
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

        def _bot_run(bot, strat, **kwargs) -> Strategy:
            bot.strategy = strat
            for trigger in bot.strategy.next.trigger:
                trigger.checked.clear()
            try:
                logger.info(f"Optimizing: {strat}")
                with util.set_level(logging.getLogger("tradingbot"), logging.WARNING):
                    bot.run(**kwargs)
            except AssertionError as exc:
                logger.info(f"{strat} bypassed due to {exc!r}")
            except Exception as exc:
                if errors == "warn":
                    msg = traceback.format_exc()
                    warnings.warn(f"{strat} failed, due to {exc!r}\n{msg}")
                elif errors == "raise":
                    raise
                else:  # ignore
                    pass
            else:
                logger.info(f"Done: {strat}")
            finally:
                return bot.strategy

        func = _bot_run_persist if persist else _bot_run
        futures = [client.submit(func, copy.deepcopy(self), copy.deepcopy(strat), **kwargs) for strat in strategy.values()]
        if persist:
            for fut in futures:
                fire_and_forget(fut)
            if remote and block:
                wait(futures)
        else:
            results = client.gather(futures)
            for name, res in zip(strategy.keys(), results):
                strategy[name] = res
            self.strategy = strategy
        
        if client.cluster is not None:
            client.cluster.close()
        client.close()
