import abc
import copy
import time
import concurrent.futures
import logging
import os
import traceback
from typing import Callable
import psutil

import pandas as pd
import requests
from retry import retry

import tradingbot.util as util
from tradingbot.data.core import Data
from tradingbot.strategy import Strategy
from tradingbot.trigger import StandardInterval
from tradingbot.reporter import Reporter


logger = logging.getLogger(__name__)


class Pipeline(abc.ABC):
    def __init__(self, now_factory: Callable[[], pd.Timestamp], **kwargs):
        self._now_factory = now_factory

    @abc.abstractmethod
    def run(self):
        pass

    @staticmethod
    @retry((requests.exceptions.ReadTimeout, requests.exceptions.ProxyError, requests.exceptions.ConnectionError), tries=3)
    def _update_data(now: pd.Timestamp, data: Data, **kwargs):
        tic = time.time()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(data.update, now): data for data in data.values()}
            for future in concurrent.futures.as_completed(futures):
                data = futures[future]
                result = future.result()
                logger.debug(f"Data Update: complete for {data.__class__.__name__}({data.field}): {result=}")
        toc = time.time()
        logger.debug(f"Data Update: took {toc - tic:.2f} seconds")

    @staticmethod
    def _update_position(strategy: Strategy):
        # update market price for position
        for pos in strategy.account.position:
            for ticker, candle in strategy.data.ticker2candle.items():
                if pos.ticker in ticker and pos.ticker == util.get_base_ticker(ticker):
                    pos.market_prc = candle["close"].iloc[-1]


class BacktestPipeline(Pipeline):
    @util.validate
    def __init__(self, now_factory: Callable[[], pd.Timestamp], start: pd.Timestamp, end: pd.Timestamp, **kwargs):
        """
        Args:
            now_factory (Callable): function to get current time
            start (str | datetime.datetime | pd.Timestamp): start time
            end (str | datetime.datetime | pd.Timestamp): end time
        """
        super().__init__(now_factory)
        self._start = start
        self._end = min(end, now_factory())

    def _get_now_generator(self, trigger: list[StandardInterval]):
        standard_interval = list(filter(lambda tri: isinstance(tri, StandardInterval), trigger))
        freq = min(tri.interval for tri in standard_interval)

        def now_generator():
            for datetime in pd.date_range(start=self._start, end=self._end, freq=freq):
                yield datetime

        return now_generator

    def run(self, strategy: Strategy, plot: bool | dict = False, preload: bool = False, **kwargs):
        """
        Args:
            plot (bool | dict, optional): whether to plot and plot kwargs
            preload (bool, optional): whether to preload data to speed up
        """
        start_tic = time.time()
        strategy.logger = logger
        strategy.start()

        # preload data if needed
        if preload:
            for da in strategy.data.values():
                da.preload = True

            def preload_helper(data: Data):
                pre_history = data.load(self._start)
                history = data.load(self._end, since=self._start)
                data._cached = pd.concat([pre_history, history], ignore_index=True)

            tic = time.time()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = {executor.submit(preload_helper, da): da for da in strategy.data.values()}
                for future in concurrent.futures.as_completed(futures):
                    future.result()
            toc = time.time()
            logger.info(f"Data Preload: took {toc - tic:.2f} seconds")

        # clear trigger status
        for tri in strategy.next.trigger:
            tri.checked.clear()

        now_generator = self._get_now_generator(strategy.next.trigger)
        for now in now_generator():
            tic = time.time()
            memory_usage = psutil.Process(os.getpid()).memory_info().rss / 1024**2

            if now > self._end:
                break

            # check trigger status
            triggered = []
            for tri in strategy.next.trigger:
                if tri.check(now):
                    triggered.append(tri)

            if any(triggered):
                strategy.logger.info(f"Now Triggered ⌚'{now}': {strategy} by {triggered}, RAM usage: {memory_usage:.2f} MB")

                # prepare info
                self._update_data(now, strategy.data)

                # update status of pending orders
                strategy.exchange.update_orders(now, strategy.pending_order)

                # update position
                self._update_position(strategy)

                # call strategy
                new_orders = strategy.next(context={"now": now, "trigger": triggered, "pending_order": strategy.pending_order})

                # execute orders
                orders = util.to_list(new_orders) + strategy.pending_order
                for order in orders:
                    order = strategy.exchange.execute(now, order)
                strategy.exchange.update_orders(now, orders)

                # update position after execution
                self._update_position(strategy)

                # archive position
                strategy.account_history[now] = copy.deepcopy(strategy.account)

            toc = time.time()
            logger.debug(f"Run {now}: took {toc - tic:.2f} seconds. RAM usage: {memory_usage:.2f} MB")

        # clear preload cache
        if preload:
            for da in strategy.data.values():
                del da._cached

        # build report
        Reporter.set(strategy)
        Reporter.display(strategy)

        strategy.stop()
        end_tic = time.time()
        print(f"BacktestPipeline.run took {(end_tic - start_tic):.2f} seconds.")

        if plot:
            plot_kwargs = {} if isinstance(plot, bool) else plot
            strategy.plot(**plot_kwargs)


class LivePipeline(Pipeline):
    def __init__(self, now_factory: Callable[[], pd.Timestamp], refresh_rate: float = 0.0, **kwargs):
        super().__init__(now_factory)
        self._refresh_rate = refresh_rate

    def _get_now_generator(self):
        def now_generator():
            while True:
                yield self._now_factory()

        return now_generator

    def run(self, strategy: Strategy, **kwargs):
        strategy.logger = util.get_strategy_logger(str(strategy))
        strategy.start()

        now_generator = self._get_now_generator()
        try:
            for now in now_generator():
                tic = time.time()
                memory_usage = psutil.Process(os.getpid()).memory_info().rss / 1024**2

                # check trigger status
                triggered = []
                for tri in strategy.next.trigger:
                    if tri.check(now):
                        triggered.append(tri)

                if any(triggered):
                    strategy.logger.debug(f"Now Triggered ⌚'{now}': {strategy} by {triggered}, RAM usage: {memory_usage:.2f} MB")

                    try:
                        # prepare info
                        self._update_data(now, strategy.data)
                    except Exception as e:
                        strategy.logger.error(f"Failed to update data. due to {e!r}. Delaying to next run.")
                        msg = traceback.format_exc()
                        strategy.logger.debug(f"{msg}")
                        continue

                    # update status of pending orders
                    strategy.exchange.update_orders(now, strategy.pending_order)

                    # update position
                    self._update_position(strategy)

                    # call strategy
                    new_orders = strategy.next(context={"now": now, "trigger": triggered, "pending_order": strategy.pending_order})

                    # execute orders
                    orders = util.to_list(new_orders) + strategy.pending_order
                    for order in orders:
                        order = strategy.exchange.execute(now, order)
                    strategy.exchange.update_orders(now, orders)

                    # update position after execution
                    self._update_position(strategy)

                    # archive position
                    strategy.account_history[now] = copy.deepcopy(strategy.account)

                toc = time.time()
                logger.debug(f"Run {now}: took {toc - tic:.2f} seconds. RAM usage: {memory_usage:.2f} MB")
                time.sleep(self._refresh_rate)

        except BaseException as e:
            strategy.logger.info(f"Stopping {strategy} due to {e!r}...")
            # build report
            Reporter.set(strategy)
            Reporter.display(strategy)
            strategy.stop()
            if isinstance(e, Exception):
                msg = traceback.format_exc()
                strategy.logger.error(msg)
            raise
