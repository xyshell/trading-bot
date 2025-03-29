import abc
from collections import defaultdict
import copy
import logging

import pandas as pd

from tradingbot.position import Position, SpotPosition
import tradingbot.util as util
from tradingbot.transaction import Transaction
from tradingbot.order import Order


logger = logging.getLogger(__name__)


class Exchange:

    def __init__(self):
        from tradingbot.strategy.core import Strategy

        self.strategy: Strategy

    def __repr__(self):
        return f"{self.__class__.__name__}()"
    
    @abc.abstractmethod
    def execute(self, order: Order):
        """Execute an order"""
        pass

    @abc.abstractmethod
    def update(self, order: Order):
        """Update status of an order"""
        pass

    @abc.abstractmethod
    def fetch_tickers(self, tickers: list[str]) -> dict:
        """fetch latest info for tickers
        
        Args:
            tickers (list[str]): e.g. ["USDT/BTC", "USDT/ETH"]

        Returns:
            dict: {
                "USDT/BTC": {
                    "last": 12345.6
                    ...
                }
                ...
            }
        """
        pass


class RealExchange(Exchange):
    pass


class FakeExchange(Exchange):
    """Fake exchange used for backtest and paper trading"""

    @util.validate
    def __init__(self, commission: float = 0.0, **kwargs) -> None:
        from tradingbot.strategy.core import Strategy

        self._commission = commission
        self.strategy: Strategy

    def __repr__(self):
        return f"{self.__class__.__name__}(commission={self._commission})"
    
    def update_order(self, order: Order):
        if order.status in {Order.Status.FILLED, Order.Status.REJECTED, Order.Status.CANCELED, Order.Status.EXPIRED}:
            self.strategy.order_history.append((self.strategy.now, order))
            if order in self.strategy.open_order:
                self.strategy.open_order.remove(order)
        elif order.status in {Order.Status.PARTIAL_FILLED, Order.Status.PENDING}:
            if order not in self.strategy.open_order:
                self.strategy.open_order.append(order)

    def _order2qty(self, order: Order, exec_prc: float) -> tuple[float, float]:
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

        return from_qty, to_qty

    def _reconcile(self, order: Order, exec_prc: float) -> Order:
        from_ticker, to_ticker = order.from_ticker, order.to_ticker
        from_qty, to_qty = self._order2qty(order, exec_prc)

        if order.market == "spot":
            if from_ticker == self.strategy.account.base_currency:  # enter market
                from_pos = Position(asset=from_ticker, qty=from_qty)
                to_pos = SpotPosition(asset=to_ticker, qty=to_qty * (1 - self._commission), entry_cost=from_pos)
                tcost_pos = Position(asset=to_ticker, qty=to_qty * self._commission)  # charge tcost in to_ticker, i.e. get less
            elif to_ticker == self.strategy.account.base_currency:  # exit market
                from_pos = Position(asset=from_ticker, qty=from_qty)
                to_pos = Position(asset=to_ticker, qty=to_qty * (1 - self._commission))
                tcost_pos = Position(asset=to_ticker, qty=to_qty * self._commission)  # charge tcost in to_ticker, i.e. get less
        else:
            raise NotImplementedError
        

        trans = Transaction(from_pos=from_pos, to_pos=to_pos, tcost_pos=tcost_pos, timestamp=self.strategy.now)
        if not trans:
            order.status = Order.Status.REJECTED
            order.updated_at = self.strategy.now
            logger.debug(f"Order(ID={id(order)}) Rejected: {order}, due to trivial transaction, transaction={trans}")
            return order

        account = self.strategy.account
        account += to_pos
        account -= from_pos

        if order.market == "spot" and not account.is_sufficient():
            order.status = Order.Status.REJECTED
            order.updated_at = self.strategy.now
            logger.debug(f"Order(ID={id(order)}) Rejected: {order}, due to insufficient capital, account={self.strategy.account}")
            return order

        self.strategy.account = account
        self.strategy.transaction_history.append(trans)

        order.status = Order.Status.FILLED
        order.updated_at = self.strategy.now
        order.filled_at = self.strategy.now
        logger.debug(f"Order(ID={id(order)}) Filled: {order}, transaction={trans}")
        return order

    def _execute_market(self, order: Order) -> Order:
        assert order.type is Order.Type.MARKET, f"Invalid order type: {order.type}"
        assert order.action in {Order.Action.BUY, Order.Action.SELL}, f"Invalid order action: {order.action}"
        if order.status in (Order.Status.CANCELED, Order.Status.EXPIRED, Order.Status.REJECTED, Order.Status.FILLED):
            return order

        exec_prc = self.strategy.data.ticker2close[order.ticker]
        order = self._reconcile(order, exec_prc)
        return order

    def _execute_limit(self, order: Order) -> Order:
        assert order.type is Order.Type.LIMIT, f"Invalid order type: {order.type}"
        assert order.action in {Order.Action.BUY, Order.Action.SELL}, f"Invalid order action: {order.action}"
        if order.status in (Order.Status.CANCELED, Order.Status.EXPIRED, Order.Status.REJECTED, Order.Status.FILLED):
            return order

        candle = self.strategy.data.ticker2candle[order.ticker]
        match order.type:
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

        order = self._reconcile(order, exec_prc)
        return order

    def execute(self, order: Order, **kwargs) -> Order:
        """
        Args:
            now (pd.Timestamp):
            order (Order):

        Returns:
            Order
        """
        if order.type is Order.Type.LIMIT:
            return self._execute_limit(order)
        elif order.type is Order.Type.MARKET:
            return self._execute_market(order)
        raise NotImplementedError

    def fetch_tickers(self, tickers: list[str]) -> dict:
        """Fetch latest info for tickers
        
        Args:
            tickers (list[str]): e.g. ["USDT/BTC", "USDT/ETH"]

        Returns:
            dict: {
                "USDT/BTC": {
                    "last": 12345.6
                    ...
                }
                ...
            }
        """
        ticker2close = self.strategy.data.ticker2close

        res = defaultdict(dict)
        for ticker in ticker2close:
            if ticker in tickers:
                res[ticker]["last"] = ticker2close[ticker]
        return res
    

# class FakeFutureExchange(FakeExchange, FutureExchange):

#     @util.validate
#     def __init__(self, commission: float = 0.0, leverage: int = 1, **kwargs) -> None:
#         self._commission = commission
#         self._leverage = leverage

#     @property
#     def leverage(self) -> int:
#         return self._leverage

#     def _order2qty(self, order: Order, exec_prc: float) -> tuple[float, float]:
#         from_ticker, to_ticker = order.from_ticker, order.to_ticker
#         quote_ticker, base_ticker = util.get_quote_ticker(order.ticker), util.get_base_ticker(order.ticker)

#         match order.size_type:
#             case Order.SizeType.PCTG:
#                 from_pos = self.strategy.account[from_ticker]
#                 from_qty = from_pos.qty * order.size
#                 if order.action in {Order.Action.OPEN_LONG, Order.Action.OPEN_SHORT}:
#                     from_qty_scaled = (from_qty / self._leverage) if isinstance(from_pos, MarginPosition) else (from_qty * self._leverage)
#                     _, to_qty = util.convert((from_ticker, from_qty_scaled * (1 - self._commission)), order.ticker, exec_prc)
#                     to_qty *= -1 if order.action is Order.Action.OPEN_SHORT else 1
#                 else:  # close position
#                     to_qty = from_pos.margin[1] * order.size
#             case Order.SizeType.BASE if to_ticker == base_ticker:
#                 raise NotImplementedError
#             case Order.SizeType.QUOTE if to_ticker == quote_ticker:
#                 to_qty = order.size
#                 _, from_qty = util.convert((to_ticker, to_qty * self._leverage), order.ticker, exec_prc)
#                 from_qty *= -1 if order.action is Order.Action.CLOSE_SHORT else 1
#             case Order.SizeType.BASE if from_ticker == base_ticker:
#                 raise NotImplementedError
#             case Order.SizeType.QUOTE if from_ticker == quote_ticker:
#                 raise NotImplementedError
#             case _:
#                 raise NotImplementedError

#         return from_qty, to_qty

#     def _reconcile(self, order: Order, exec_prc: float) -> Order:
#         from_ticker, to_ticker = order.from_ticker, order.to_ticker
#         quote_ticker = util.get_quote_ticker(order.ticker)
#         from_qty, to_qty = self._order2qty(order, exec_prc)

#         fee_qty = from_qty if from_ticker == quote_ticker else to_qty
#         tcost = (quote_ticker, fee_qty * self._commission)  # charge tcost in quote_ticker
#         if to_ticker == quote_ticker:
#             to_qty -= tcost[1]

#         if order.action in {Order.Action.OPEN_LONG, Order.Action.OPEN_SHORT}:
#             trans = OpenTransaction(
#                 ticker = order.ticker,
#                 prc = exec_prc,
#                 from_ = (from_ticker, from_qty),  # normal position
#                 to_ = (to_ticker, to_qty),  # margin position
#                 tcost = tcost,
#                 timestamp = now,
#                 leverage = self._leverage
#             )
#         else:  # close position
#             trans = CloseTransaction(
#                 ticker = order.ticker,
#                 prc = exec_prc,
#                 from_ = (from_ticker, from_qty),  # margin position
#                 to_ = (to_ticker, to_qty),  # normal position
#                 tcost = tcost,
#                 timestamp = now,
#                 leverage = self._leverage
#             )
#         if not trans:
#             order.status = Order.Status.REJECTED
#             logger.debug(f"Order(ID={id(order)}) Rejected: {order}, due to trivial transaction, transaction={trans}")
#             return order

#         from_pos, to_pos, _ = trans.split()
#         account = copy.deepcopy(self.strategy.account)
#         account += to_pos
#         account -= from_pos

#         if not account.is_sufficient():
#             order.status = Order.Status.REJECTED
#             logger.debug(f"Order(ID={id(order)}) Rejected: {order}, due to insufficient capital, account={self.strategy.account}")
#             return order

#         self.strategy.account = account
#         self.strategy.transaction_history.append(trans)

#         order.status = Order.Status.FILLED
#         logger.debug(f"Order(ID={id(order)}) Filled: {order}, transaction={trans}")
#         return order

#     def _execute_market(self, order: Order) -> Order:
#         assert order.type is Order.Type.MARKET, f"Invalid order type: {order.type}"
#         assert order.action in {Order.Action.OPEN_LONG, Order.Action.CLOSE_LONG, Order.Action.OPEN_SHORT, Order.Action.CLOSE_SHORT}, f"Invalid order action: {order.action}"
#         if order.status in (Order.Status.CANCELED, Order.Status.EXPIRED, Order.Status.REJECTED, Order.Status.FILLED):
#             return order

#         candle = self.strategy.data.ticker2candle[order.ticker]
#         exec_prc = candle["close"].iloc[-1]

#         order = self._reconcile(order, exec_prc)
#         return order

#     def _execute_limit(self, order: Order) -> Order:
#         assert order.type is Order.Type.LIMIT, f"Invalid order type: {order.type}"
#         assert order.action in {Order.Action.OPEN_LONG, Order.Action.CLOSE_LONG, Order.Action.OPEN_SHORT, Order.Action.CLOSE_SHORT}, f"Invalid order action: {order.action}"
#         if order.status in (Order.Status.CANCELED, Order.Status.EXPIRED, Order.Status.REJECTED, Order.Status.FILLED):
#             return order

#         candle = self.strategy.data.ticker2candle[order.ticker]
#         match order.status:
#             case Order.Status.NEW:
#                 if order.action in {Order.Action.OPEN_LONG, Order.Action.CLOSE_SHORT} and order.param["price"] >= candle["close"].iloc[-1]:
#                     exec_prc = candle["close"].iloc[-1]
#                 elif order.action in {Order.Action.OPEN_SHORT, Order.Action.CLOSE_LONG} and order.param["price"] <= candle["close"].iloc[-1]:
#                     exec_prc = candle["close"].iloc[-1]
#                 else:
#                     order.status = Order.Status.PENDING
#                     return order
#             case Order.Status.PENDING:
#                 high = candle["high"].iloc[-1]
#                 low = candle["low"].iloc[-1]
#                 if low <= order.param["price"] <= high:
#                     exec_prc = order.param["price"]
#                 else:
#                     return order

#         order = self._reconcile(order, exec_prc)
#         return order

#     def execute(self, order: Order, **kwargs) -> Order:
#         """
#         Args:
#             now (pd.Timestamp):
#             order (Order):

#         Returns:
#             Order
#         """
#         if order.type is Order.Type.LIMIT:
#             return self._execute_limit(now, order)
#         elif order.type is Order.Type.MARKET:
#             return self._execute_market(now, order)
#         raise NotImplementedError
