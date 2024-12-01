import abc
import copy
import random
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

from tradingbot.exchange.fake import FakeExchange
from tradingbot.model import MarginPosition
from tradingbot.order import Order
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
    def _mark_to_market(strategy: Strategy):
        # update market price for position
        for pos in strategy.account.position:
            for ticker, candle in strategy.data.ticker2candle.items():
                # update market price
                if pos.ticker in ticker and pos.ticker == util.get_base_ticker(ticker):
                    pos.market_prc = candle["close"].iloc[-1]
                # check liquidation
                if isinstance(pos, MarginPosition):
                    if pos.margin[1] < 0:
                        pos.clear()

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

    def _prep(self, now: pd.Timestamp, strategy: Strategy):
        # update data
        self._update_data(now, strategy.data)
        # execute pending orders
        self._mark_to_market(strategy)
        for order in strategy.pending_order:
            strategy.exchange.execute(now, order)
            strategy.exchange.update_order(now, order)
        self._mark_to_market(strategy)

    def _post(self, now: pd.Timestamp, strategy: Strategy, new_orders: list[Order]):
        # execute new orders + pending orders
        self._mark_to_market(strategy)
        orders = util.to_list(new_orders) + strategy.pending_order
        for order in orders:
            order = strategy.exchange.execute(now, order)
            strategy.exchange.update_order(now, order)
        
        # archive position
        self._mark_to_market(strategy)
        strategy.account_history[now] = copy.deepcopy(strategy.account)

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

                # prepare
                self._prep(now, strategy)

                # call next
                new_orders = strategy.next(
                    context={"now": now, "trigger": triggered, "pending_order": strategy.pending_order}
                )

                # post-process
                self._post(now, strategy, new_orders)

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
    def __init__(self, now_factory: Callable[[], pd.Timestamp], refresh_rate: float = 0.0, reflect_account: bool = True, **kwargs):
        super().__init__(now_factory)
        self._refresh_rate = refresh_rate
        self._reflect_account = reflect_account

    def _get_now_generator(self):
        def now_generator():
            while True:
                yield self._now_factory()

        return now_generator

    def _prep(self, now: pd.Timestamp, strategy: Strategy) -> bool:
        # update data
        n = 3
        while n > 0:
            try:
                self._update_data(now, strategy.data)
            except Exception as e:
                strategy.logger.debug(f"Failed to update data. due to {e!r}. Retrying {n=}...")
                n -= 1
                time.sleep(random.randint(1, 5))
            else:
                break
        else:
            strategy.logger.error("Failed to update data after retries. Delaying to next run.")
            msg = traceback.format_exc()
            strategy.logger.debug(f"{msg}")
            return False

        # make sure status of pending orders are up-to-date
        for order in strategy.pending_order:
            strategy.exchange.update_order(now, order)
        self._mark_to_market(strategy)

        # reflect account
        if self._reflect_account and not isinstance(strategy.exchange, FakeExchange) and (ticker := strategy.param.get("ticker")):
            try:
                strategy.account = strategy.exchange.reflect_account(now, strategy.init_account, ticker)
            except Exception as e:
                strategy.logger.debug(f"Failed to reflect account. due to {e!r}. Ignored.")

        return True

    def _post(self, now: pd.Timestamp, strategy: Strategy, new_orders: list[Order]):
        # execute orders
        self._mark_to_market(strategy)
        orders = util.to_list(new_orders) + strategy.pending_order
        for order in orders:
            order = strategy.exchange.execute(now, order)
        self._mark_to_market(strategy)

        # archive position
        strategy.account_history[now] = copy.deepcopy(strategy.account)


    def run(self, strategy: Strategy, **kwargs):
        strategy.logger = util.get_strategy_logger(str(strategy))

        # reflect account
        if self._reflect_account and not isinstance(strategy.exchange, FakeExchange) and (ticker := strategy.param.get("ticker")):
            strategy.account = strategy.exchange.reflect_account(self._now_factory(), strategy.init_account, ticker)

        # start strategy
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

                    # prepare
                    if not self._prep(now, strategy): 
                        continue

                    # call next
                    new_orders = strategy.next(context={"now": now, "trigger": triggered, "pending_order": strategy.pending_order})

                    # post-process
                    self._post(now, strategy, new_orders)

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
