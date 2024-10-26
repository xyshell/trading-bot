import copy
import logging

import pandas as pd

import tradingbot.util as util
from tradingbot.model import Order, Transaction
from tradingbot.exchange.core import Exchange

logger = logging.getLogger(__name__)


class FakeExchange(Exchange):
    pass

class FakeSpotExchange(FakeExchange):
    """Fake spot exchange used for backtest and paper trading"""

    @util.validate
    def __init__(self, commission: float = 0.0, **kwargs) -> None:
        self._commission = commission

    def update_orders(self, now: pd.Timestamp, orders: list[Order]):
        for order in orders:
            if order.status in {Order.Status.FILLED, Order.Status.REJECTED, Order.Status.CANCELED, Order.Status.EXPIRED}:
                self.strategy.order_history[now] = order
                if order in self.strategy.pending_order:
                    self.strategy.pending_order.remove(order)
            elif order.status in {Order.Status.PARTIAL_FILLED, Order.Status.PENDING}:
                if order not in self.strategy.pending_order:
                    self.strategy.pending_order.append(order)

    def execute(self, now: pd.Timestamp, order: Order) -> Order:
        """
        Args:
            now (pd.Timestamp):
            order (Order):

        Returns:
            Order
        """
        if order.status in (Order.Status.CANCELED, Order.Status.EXPIRED, Order.Status.REJECTED, Order.Status.FILLED):
            return order
        if order.type not in {Order.Type.LIMIT, Order.Type.MARKET}:
            raise NotImplementedError(f"Order type {order.type} is not supported yet.")

        candle = self.strategy.data.ticker2candle[order.ticker]

        match order.type:
            case Order.Type.MARKET:
                exec_prc = candle["close"].iloc[-1]
            case Order.Type.LIMIT if order.status is Order.Status.NEW:
                if order.action is Order.Action.BUY and order.param["price"] >= candle["close"].iloc[-1]:
                    exec_prc = candle["close"].iloc[-1]
                elif order.action is Order.Action.SELL and order.param["price"] <= candle["close"].iloc[-1]:
                    exec_prc = candle["close"].iloc[-1]
                else:
                    order.status = Order.Status.PENDING
                    return order
            case Order.Type.LIMIT if order.status is Order.Status.PENDING:
                high = candle["high"].iloc[-1]
                low = candle["low"].iloc[-1]
                if low <= order.param["price"] <= high:
                    exec_prc = order.param["price"]
                else:
                    return order

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
            logger.debug(f"Order(ID={id(order)}) Rejected: {order}, due to insufficient capital, account={self.strategy.account}")
            return order

        self.strategy.account = account
        self.strategy.transaction_history.append(trans)

        order.status = Order.Status.FILLED
        logger.debug(f"Order(ID={id(order)}) Filled: {order}, transaction={trans}")
        return order
