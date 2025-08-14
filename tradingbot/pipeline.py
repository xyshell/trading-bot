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
from tradingbot.data.core import Data, DataManager
from tradingbot.strategy import Strategy
from tradingbot.trigger import StandardInterval
from tradingbot.reporter import Reporter
from tradingbot.exception import DataUpdateError, OrderUpdateError


logger = logging.getLogger(__name__)


class Pipeline(abc.ABC):
    def __init__(self, now_factory: Callable[[], pd.Timestamp], **kwargs):
        self._now_factory = now_factory

    @abc.abstractmethod
    def run(self, strategy: Strategy, **kwargs):
        pass

    @staticmethod
    @retry((requests.exceptions.ReadTimeout, requests.exceptions.ProxyError, requests.exceptions.ConnectionError), tries=3)
    def _update_data(now: pd.Timestamp, data: dict[str, Data], **kwargs):
        tic = time.time()
        if len(data) == 1:
            for da in data.values():
                result = da.update(now)
                logger.debug(f"Data Update: complete for {da.__class__.__name__}({da.field}): {result=}")
        else:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = {executor.submit(da.update, now): da for da in data.values()}
                for future in concurrent.futures.as_completed(futures):
                    data = futures[future]
                    result = future.result()
                    logger.debug(f"Data Update: complete for {data.__class__.__name__}({data.field}): {result=}")
        toc = time.time()
        logger.debug(f"Data Update: took {toc - tic:.2f} seconds")


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

    def _prep(self, now: pd.Timestamp, strategy: Strategy) -> None:
        """Prepare strategy for next run"""
        # update time
        strategy.now = now

        # update data
        self._update_data(now, strategy.data)

        # execute pending order
        for order in strategy.order:
            strategy.trader.exchange.execute(order.type.value, order)
        
        # update order
        for order in strategy.order:
            strategy.trader.exchange.update(order)

        # mark to market
        for ticker, pos_pair in strategy.balance.positions.items():
            candle = strategy.data.ticker2candle[ticker]
            high = candle["high"].iloc[-1]
            low = candle["low"].iloc[-1]
            close = candle["close"].iloc[-1]
            if long_pos := pos_pair.get("long"):
                long_pos.updated_at = now
                if low < long_pos.liquidation_prc:
                    long_pos.clear()
                else:
                    long_pos.mark_prc = close
            if short_pos := pos_pair.get("short"):
                short_pos.updated_at = now
                if high > short_pos.liquidation_prc:
                    short_pos.clear()
                else:
                    short_pos.mark_prc = close

    def _post(self, now: pd.Timestamp, strategy: Strategy) -> None:
        """Post process after strategy run"""
        # record balance
        strategy.balance_history[now] = copy.deepcopy(strategy.balance)
        evaluated_balance = strategy.balance.evaluate(strategy.trader.exchange, strategy.currency)
        strategy.store['_evaluated_balance'] = evaluated_balance
        
        # record store
        strategy.store_history[now] = copy.deepcopy(strategy.store)

    def run(self, strategy: Strategy, **kwargs) -> None:
        """Run strategy in backtest pipeline
        
        Args:
            strategy (Strategy): strategy to be run
        """
        start_tic = time.time()
        strategy.logger = util.get_strategy_logger(str(strategy), add_slack=False)
        strategy.data = DataManager(**strategy.data, mode="backtest")
        strategy.trader.strategy = strategy
        strategy.trader.exchange.strategy = strategy

        # strategy start
        strategy.start()

        # preload data
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
        logger.debug(f"Data Preload: took {toc - tic:.2f} seconds")

        now_generator = self._get_now_generator(strategy.next.trigger)
        for now in now_generator():
            if now > self._end:
                break

            tic = time.time()
            memory_usage = psutil.Process(os.getpid()).memory_info().rss / 1024**2

            # check trigger status
            triggered = []
            for tri in strategy.next.trigger:
                if tri.check(now):
                    triggered.append(tri)

            if any(triggered):
                logger.info(f"Now Triggered ⌚'{now}': {strategy} by {triggered}, RAM usage: {memory_usage:.2f} MB")
                strategy.trigger_msg = [str(trg) for trg in triggered]

                # prep
                self._prep(now, strategy)

                # next
                strategy.next()

                # post
                self._post(now, strategy)

            toc = time.time()
            logger.debug(f"Run {now}: took {toc - tic:.2f} seconds. RAM usage: {memory_usage:.2f} MB")

        strategy.stop()

        # build report
        Reporter.set(strategy)
        Reporter.display(strategy)

        # clear preload cache
        for da in strategy.data.values():
            del da._cached

        end_tic = time.time()
        logger.debug(f"BacktestPipeline.run took {(end_tic - start_tic):.2f} seconds.")


class LivePipeline(Pipeline):
    def __init__(self, now_factory: Callable[[], pd.Timestamp], response_rate: float = 0.0, reflect_balance: bool = True, **kwargs):
        super().__init__(now_factory)
        self._response_rate = response_rate
        self._reflect_balance = reflect_balance

    def _get_now_generator(self):
        def now_generator():
            while True:
                yield self._now_factory()

        return now_generator

    def _prep(self, now: pd.Timestamp, strategy: Strategy) -> None:
        """Prepare strategy for next run
        
        raises:
            DataUpdateError: if data update fails
            OrderUpdateError: if order update fails
        """
        # update time
        strategy.now = now

        # update data
        try:
            self._update_data(now, strategy.data)
        except Exception as e:
            exc_msg = f"Failed to update data at {now}, due to {e}"
            strategy.logger.debug(f"{traceback.format_exc()}")
            raise DataUpdateError(exc_msg)

        # update order
        try:
            for order in strategy.order:
                strategy.trader.exchange.update(order)
        except Exception as e:
            exc_msg = f"Failed to update order at {now}, due to {e}"
            strategy.logger.debug(f"{traceback.format_exc()}")
            raise OrderUpdateError(exc_msg)

    def _post(self, now: pd.Timestamp, strategy: Strategy) -> None:
        """Post process after strategy run"""
        # record balance
        strategy.balance_history[now] = copy.deepcopy(strategy.balance)
        strategy.store['_evaluated_balance'] = strategy.balance.evaluate(strategy.trader.exchange, strategy.currency)
        
        # record store
        strategy.store_history[now] = copy.deepcopy(strategy.store)

    def run(self, strategy: Strategy, **kwargs) -> None:
        """Run strategy in live pipeline

        Args:
            strategy (Strategy): strategy to be run
        """
        strategy.logger = util.get_strategy_logger(str(strategy))
        strategy.data = DataManager(**strategy.data, mode="live")
        strategy.trader.strategy = strategy
        strategy.trader.exchange.strategy = strategy

        # start
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
                    strategy.trigger_msg = [str(trg) for trg in triggered]

                    # prep
                    try:
                        self._prep(now, strategy)
                    except DataUpdateError as e:
                        strategy.logger.error(f"prep failed: {e}. Delaying to next run.")
                        continue
                    except OrderUpdateError as e:
                        strategy.logger.error(f"prep failed: {e}. Delaying to next run.")
                        continue

                    # next
                    strategy.next()

                    # post
                    self._post(now, strategy)

                toc = time.time()
                logger.debug(f"Run {now}: took {toc - tic:.2f} seconds. RAM usage: {memory_usage:.2f} MB")
                time.sleep(self._response_rate)

        except BaseException as e:
            strategy.logger.info(f"Stopping {strategy} due to {e!r}...")
            if isinstance(e, Exception):
                msg = traceback.format_exc()
                strategy.logger.error(msg)
            strategy.stop()
            # build report
            Reporter.set(strategy)
            Reporter.display(strategy)
            raise
