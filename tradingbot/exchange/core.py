import abc

import pandas as pd

from tradingbot.strategy import Strategy
from tradingbot.model import Account, Order


class Exchange:
    @property
    def strategy(self) -> Strategy:
        return self._strategy

    @strategy.setter
    def strategy(self, strategy: Strategy):
        self._strategy = strategy

    @abc.abstractmethod
    def execute(self, now: pd.Timestamp, order: Order):
        pass

    def update_order(self, now: pd.Timestamp, order: Order):
        pass

    def reflect_account(self, account: Account, ticker: str) -> Account:
        return account


class FutureExchange(Exchange):
    pass