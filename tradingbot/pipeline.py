import abc
import copy
import time
import concurrent.futures
import logging
import os
from typing import Callable
import psutil

import pandas as pd

import tradingbot.util as util
from tradingbot.model import Order
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
    def _update_data(data: Data, now: pd.Timestamp, **kwargs):
        tic = time.time()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(data.update, now): data for data in data.values()}
            for future in concurrent.futures.as_completed(futures):
                data = futures[future]
                result = future.result()
                logger.debug(f"Data Update: complete for {data.__class__.__name__}({data.field}): {result=}")
        toc = time.time()
        logger.debug(f"Data Update: took {toc - tic:.2f} seconds")


class BacktestPipeline(Pipeline):
    def __init__(self, now_factory: Callable[[], pd.Timestamp], start: pd.Timestamp, end: pd.Timestamp, **kwargs):
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

    def run(self, strategy: Strategy, plot: bool | dict = False, **kwargs):
        strategy.start()

        now_generator = self._get_now_generator(strategy.next.trigger)
        for now in now_generator():
            tic = time.time()
            if now > self._end:
                break

            # check trigger status
            triggered = []
            for tri in strategy.next.trigger:
                if tri.check(now):
                    triggered.append(tri)

            if any(triggered):
                logger.info(f"Now Triggered ⌚'{now}': {strategy} by {triggered}")

                # prepare info
                self._update_data(strategy.data, now)

                # call strategy
                orders = strategy.next(context={"now": now, "trigger": triggered, "pending_order": strategy.pending_order})

                # execute orders
                orders = util.to_list(orders) + strategy.pending_order
                for order in orders:
                    strategy.exchange.execute(now, order)
                for order in orders:
                    if order.status in {Order.Status.FILLED, Order.Status.REJECTED, Order.Status.CANCELED, Order.Status.EXPIRED}:
                        strategy.order_history[now] = order
                    elif order.status is Order.Status.PARTIAL_FILLED:
                        strategy.pending_order.add(order)

            # collect result
            # update market price for position
            for pos in strategy.account.position:
                for ticker, candle in strategy.data.ticker2candle.items():
                    if pos.ticker in ticker and pos.ticker != util.get_quote_ticker(ticker):
                        pos.market_prc = candle["close"].iloc[-1]
            # archive position
            strategy.account_history[now] = copy.deepcopy(strategy.account)

            toc = time.time()
            memory_usage = psutil.Process(os.getpid()).memory_info().rss / 1024**2
            logger.debug(f"Run {now}: took {toc - tic:.2f} seconds. RAM usage: {memory_usage:.2f} MB")

        # build report
        Reporter.set(strategy)
        Reporter.display(strategy)

        strategy.stop()

        if plot:
            plot_kwargs = {} if isinstance(plot, bool) else plot
            strategy.plot(**plot_kwargs)


class PaperPipeline(Pipeline):
    def __init__(self, now_factory: Callable[[], pd.Timestamp], refresh_rate: float = 0.0, **kwargs):
        super().__init__(now_factory)
        self._refresh_rate = refresh_rate

    def _get_now_generator(self):
        def now_generator():
            while True:
                yield self._now_factory()

        return now_generator

    def run(self, strategy: Strategy):
        strategy.start()

        now_generator = self._get_now_generator()
        for now in now_generator():
            tic = time.time()

            # check trigger status
            triggered = []
            for tri in strategy.next.trigger:
                if tri.check(now):
                    triggered.append(tri)

            if any(triggered):
                logger.info(f"Now Triggered ⌚'{now}': {strategy} by {triggered}")

                # prepare info
                self._update_data(strategy.data, now)

                # call strategy
                orders = strategy.next(context={"now": now, "trigger": triggered, "pending_order": strategy.pending_order})

                # execute orders
                orders = util.to_list(orders) + strategy.pending_order
                for order in orders:
                    self.exchange.execute(now, order)
                for order in orders:
                    if order.status in {Order.Status.FILLED, Order.Status.REJECTED, Order.Status.CANCELED, Order.Status.EXPIRED}:
                        strategy.order_history[now] = order
                    elif order.status is Order.Status.PARTIAL_FILLED:
                        strategy.pending_order.add(order)

            # collect result
            # update market price for position
            for pos in strategy.account.position:
                for ticker, candle in strategy.data.ticker2candle.items():
                    if pos.ticker in ticker and pos.ticker != util.get_quote_ticker(ticker):
                        pos.market_prc = candle["close"].iloc[-1]
            # archive position
            strategy.account_history[now] = copy.deepcopy(strategy.account)

            toc = time.time()
            memory_usage = psutil.Process(os.getpid()).memory_info().rss / 1024**2
            logger.debug(f"Run {now}: took {toc - tic:.2f} seconds. RAM usage: {memory_usage:.2f} MB")
            time.sleep(self._refresh_rate)

        # build report
        Reporter.set(strategy)
        Reporter.display(strategy)

        strategy.stop()


class LivePipeline(PaperPipeline):
    pass
