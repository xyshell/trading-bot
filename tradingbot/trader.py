from enum import Enum
from functools import cached_property
import typing
import logging

import pandas as pd

from tradingbot.strategy.core import Strategy
import tradingbot.util as util
from tradingbot.order import Order
from tradingbot.exchange import RealExchange, FakeExchange


class Trader:
    """Trade uses exchange to implement trading instructions from strategy"""

    @util.validate
    def __init__(self, fake_exchange: FakeExchange, real_exchange: RealExchange | None = None, /):
        self._fake_exchange = fake_exchange
        self._real_exchange = real_exchange or fake_exchange
        self._mode = None
        self._strategy = None

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        self._mode = value
    
    @property
    def strategy(self) -> Strategy:
        return self._strategy
    
    @strategy.setter
    def strategy(self, value: Strategy) -> None:
        self._strategy = value

    @cached_property
    def exchange(self) -> RealExchange | FakeExchange:
        return self._real_exchange if self._mode == "live" else self._fake_exchange

    def __repr__(self):
        return f"Trader(exchange={self.exchange})"

    # @util.validate
    # def submit(self, order: Order, algo: Algo = Algo.PASSIVE) -> None:
    #     order.created_at = self.strategy.now
    #     order = self.exchange.execute(order)

    #     if order.status in {Order.Status.PENDING, Order.Status.PARTIAL_FILLED}:
    #         self.strategy.orders.append(order)
    #     elif order.status in {Order.Status.FILLED, Order.Status.REJECTED, Order.Status.CANCELED, Order.Status.EXPIRED}:
    #         self.strategy.order_history.append(order)

    #     if algo is Algo.PASSIVE:
    #         return
