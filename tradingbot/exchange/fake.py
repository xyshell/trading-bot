import copy
import logging

import pandas as pd

import tradingbot.util as util
from tradingbot.model import Order, Transaction
from tradingbot.exchange.core import Exchange

logger = logging.getLogger(__name__)


class FakeSpotExchange(Exchange):
    """Fake exchange used for backtest and paper trading"""

    @util.validate
    def __init__(self, commission: float = 0.0, **kwargs) -> None:
        self._commission = commission

    def execute(self, now: pd.Timestamp, order: Order) -> Order:
        """
        Args:
            now (pd.Timestamp):
            order (Order):

        Returns:
            Order in {Order.Status.FILLED, Order.Status.REJECTED}
        """
        if order.status in (Order.Status.CANCELED, Order.Status.EXPIRED, Order.Status.REJECTED, Order.Status.FILLED):
            return order
        if order.type is not Order.Type.MARKET:
            raise NotImplementedError(f"Order type {order.type} is not supported yet.")

        exec_prc = self.strategy.ticker2data[order.ticker]["close"].iloc[-1]
        from_ticker, to_ticker = order.from_ticker, order.to_ticker
        quote_ticker, base_ticker = util.get_quote_ticker(order.ticker), util.get_base_ticker(order.ticker)

        match order.size_type:
            case Order.SizeType.PCTG:
                from_qty = self.strategy.account[from_ticker].qty * order.size
                _, to_qty = util.convert((from_ticker, from_qty), order.ticker, exec_prc)

            case Order.SizeType.BASE if to_ticker == base_ticker:
                to_qty = order.size
                _, from_qty = util.convert((to_ticker, to_qty), order.ticker, exec_prc)

            case Order.SizeType.QUOTE if to_ticker == quote_ticker:
                to_qty = order.size
                _, from_qty = util.convert((to_ticker, to_qty), order.ticker, exec_prc)

            case Order.SizeType.BASE if from_ticker == base_ticker:
                from_qty = order.size
                _, to_qty = util.convert((from_ticker, from_qty), order.ticker, exec_prc)

            case Order.SizeType.QUOTE if from_ticker == quote_ticker:
                from_qty = order.size
                _, to_qty = util.convert((from_ticker, from_qty), order.ticker, exec_prc)

            case _:
                raise NotImplementedError(f"Order size type {order.size_type} is not supported yet.")

        tcost = (to_ticker, to_qty * self._commission)  # charge tcost in to_ticker
        to_qty *= 1 - self._commission
        trans = Transaction(
            ticker=order.ticker, prc=exec_prc, from_=(from_ticker, from_qty), to_=(to_ticker, to_qty), tcost=tcost, timestamp=now
        )
        if not trans:
            order.status = Order.Status.REJECTED
            logger.debug(f"Order(ID={id(order)}) Rejected: {order}, due to trivial transaction, transaction={trans}")
            return order

        from_pos, to_pos, _ = trans.split()
        account = copy.deepcopy(self.strategy.account)
        account += to_pos
        account -= from_pos

        if not account.all_long():
            order.status = Order.Status.REJECTED
            logger.debug(f"Order(ID={id(order)}) Rejected: {order}, due to insufficient capital, positions={self.strategy.positions}")
            return order

        self.strategy.account = account
        self.strategy.transaction_history.append(trans)

        order.status = Order.Status.FILLED
        logger.debug(f"Order(ID={id(order)}) Filled: {order}, transaction={trans}")

        return order
