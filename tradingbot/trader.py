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
    """Trader implements trading instructions from strategy, by working with exchange
    """

    @util.validate
    def __init__(self, fake_exchange: FakeExchange, real_exchange: RealExchange | None = None, /):
        self._fake_exchange = fake_exchange
        self._real_exchange = real_exchange or fake_exchange
        self.mode: str  # "live", "paper" or "backtest"
        self.strategy: Strategy

    @cached_property
    def exchange(self) -> RealExchange | FakeExchange:
        return self._real_exchange if self.mode == "live" else self._fake_exchange

    def __repr__(self):
        return f"Trader(exchange={self.exchange})"

    def _get_action_ticker(self, frm: str, to: str) -> tuple[str, str]:
        markets = self.exchange.load_markets()
        if f"{frm}/{to}" in markets:
            ticker = f"{frm}/{to}"
            action = "buy"
        elif f"{to}/{frm}" in markets:
            ticker = f"{to}/{frm}"
            action = "sell"
        else:
            raise NotImplementedError(f"{frm} -> {to}")
    
        return action, ticker 

    @util.dispatch
    def implement(self, method: str, frm_qty: float, frm: str, to: str, param: dict):
        raise NotImplementedError(method)

    @implement.register((__qualname__, "market"))
    def _(self, method: str, frm_qty: float, frm: str, to: str, param: dict):
        action, ticker = self._get_action_ticker(frm, to)

        prc = self.strategy.data.ticker2close[ticker]
        order = Order(
            action=action, 
            ticker=ticker, 
            amount=frm_qty / prc if action == "buy" else frm_qty, 
            type="market", 
            created_at=self.strategy.now, 
            updated_at=self.strategy.now
        )
        order = self.exchange.execute("market", order)

    @implement.register((__qualname__, "limit"))
    def _(self, method: str, frm_qty: float, frm: str, to: str, param: dict):
        action, ticker = self._get_action_ticker(frm, to)

        prc = self.strategy.data.ticker2close[ticker]
        order = Order(
            action=action, 
            ticker=ticker, 
            amount=frm_qty / prc if action == "buy" else frm_qty, 
            type="limit", 
            param=param,
            created_at=self.strategy.now, 
            updated_at=self.strategy.now
        )
        order = self.exchange.execute("limit", order)

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
