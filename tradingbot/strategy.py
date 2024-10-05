import abc

import pandas as pd

from tradingbot.model import Account, Order, Transaction


class Strategy(abc.ABC):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "param"):
            cls.param = {}

    def __init__(self, **kwargs):
        self.param = self.__class__.param.copy()
        self.param.update(kwargs)

        self.pending_order: list[Order] = []  # keep track of all pending orders
        self.order_history: dict[pd.Timestamp, Order] = {}  # record all filled orders
        self.transaction_history: list[Transaction] = []  # record all transactions
        self.account: Account  # keep track of all positions
        self.account_history: dict[pd.Timestamp, list[Account]] = {}  # record all positions
        self.report: dict[str, pd.DataFrame] = {}  # save report

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.param})"

    def start(self):
        pass

    @abc.abstractmethod
    def next(self):
        pass

    def stop(self):
        pass
