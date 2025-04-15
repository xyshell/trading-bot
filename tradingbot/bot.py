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
from dask.distributed import Client, LocalCluster, fire_and_forget, wait

import tradingbot.util as util
from tradingbot.util import ModeType, DatetimeType
from tradingbot.pipeline import Pipeline, BacktestPipeline, LivePipeline
from tradingbot.strategy import Strategy
from tradingbot.database import Database
from tradingbot.config import get_config


logger = logging.getLogger(__name__)


class Bot:

    @util.validate
    def __init__(
        self,
        mode: ModeType,
        now_factory: Callable[[], pd.Timestamp] = util.utc_now_factory,
        *_,
        # for backtest mode
        start: DatetimeType | None = None,
        end: DatetimeType | None = None,
        # live mode
        response_rate: float = 0.0,
        **kwargs,
    ):
        """
        Args:
            mode (str): "backtest" or "live"
            now_factory (Callable, optional): function to get current time. Defaults to pd.Timestamp.utcnow().tz_localize(None).

            # backtest mode
            start (str | datetime.datetime | pd.Timestamp, optional): backtest start time
            end (str | datetime.datetime | pd.Timestamp, optional): backtest end time

            # live mode
            response_rate (float, optional): refresh rate in seconds.
        """
        self._mode = mode
        self._now_factory = now_factory
        self._start = start
        self._end = end
        self._response_rate = response_rate

        self._strategies: list[Strategy] = []
        self._id = str(uuid.uuid4())
        logger.debug(f"Bot(ID={id(self)}) Created: Mode='{self._mode}'")

    @property
    def mode(self) -> ModeType:
        return self._mode

    @util.validate
    def add_strategy(self, strategy: Strategy) -> None:
        strategy.mode = self._mode
        strategy.trader.mode = self._mode
        for data in strategy.data.values():
            data.mode = self._mode
        self._strategies.append(strategy)

    @property
    def strategies(self) -> list[Strategy]:
        return self._strategies

    @property
    def strategy(self) -> Strategy:
        return self._strategies[0]

    def run(self, cluster=None, **kwargs) -> None:
        """Run the bot
        
        Args:
            cluster (Cluster, optional): run the bot on a dask cluster instance if specified.
        """
        pipeline = (
            BacktestPipeline(
                self._now_factory, 
                start=self._start, 
                end=self._end, 
            )
            if self._mode == "backtest"
            else LivePipeline(
                self._now_factory,
                response_rate=self._response_rate,
            )
        )

        def task(pipeline: Pipeline, strategy: Strategy) -> Strategy:
            pipeline.run(strategy)
            return strategy

        if cluster is None:
            for i, strat in enumerate(self._strategies):
                self._strategies[i] = task(pipeline, strat)
        else:
            strategy_str = [str(strat) for strat in self._strategies]
            assert len(set(strategy_str)) == len(self._strategies), f"str(strategy) must be unique, got {strategy_str}"

            self._dask_client = Client(cluster)
            self._dask_client.forward_logging("tradingbot")
            logger.info(f"Cluster Dashboard: {cluster.dashboard_link}")

            futures = {str(strat): self._dask_client.submit(task, pipeline, strat) for strat in self._strategies}
            results = self._dask_client.gather(futures)
            self._strategies = [results[str(strat)] for strat in self._strategies]

    def optimize(
        self,
        strategy: dict[str, Strategy],
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
            errors (str, optional): "ignore", "warn" or "raise"
            persist (bool, optional): persist results to database. Defaults to True. if True, results are not returned.
            if_exists (str, optional): only when persist is True, what to do if the key already exists in opt result table.
                "ignore", "replace" or "raise". Defaults to "ignore".
            remote (bool, optional): if True, run on remote cluster. Defaults to False.
            restart (bool, optional): if True, restart cluster. Defaults to False.
            block (bool, optional): if True, block until finished. Defaults to False.
            scheduler_url (str, optional): dask scheduler url. Defaults to use config.toml cluster_url.
            n_workers (int, optional): only when scheduler_url is None, specify number of workers using LocalCluster. Defaults to os.cpu_count().
            **kwargs: passed to bot.run(**kwargs)
        """
        config = get_config()

        scheduler_url = scheduler_url or config.general.cluster_url
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
                insert_stmt = insert(table).values({"key": key, "strategy": strat.__class__.__name__, "stats": stats.to_json()})
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
