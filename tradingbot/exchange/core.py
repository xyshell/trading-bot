import abc
from collections import defaultdict
import copy
import logging


import tradingbot.util as util
from tradingbot.transaction import Transaction
from tradingbot.order import Order


logger = logging.getLogger(__name__)


class Exchange(abc.ABC):

    def __init__(self):
        from tradingbot.strategy.core import Strategy

        self.strategy: Strategy

    def __repr__(self):
        return f"{self.__class__.__name__}()"
    
    @abc.abstractmethod
    def execute(self, order: Order) -> Order:
        """Execute an order"""
        pass

    @abc.abstractmethod
    def update(self, order: Order) -> Order:
        """Update status of an order"""
        pass

    @abc.abstractmethod
    def cancel(self, order: Order) -> Order:
        """Cancel an order"""
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

    @abc.abstractmethod
    def load_markets(self, market_type: str | None = None) -> dict:
        """Load tradable tickers in the market

        Args:
            market_type (str): "spot", "future", "swap", "option", defaults to load all

        Returns:
            dict: 
            {
                "USDT/BTC": {
                    "quote": "USDT",
                    "base": "BTC",
                    "type": "spot",
                    ...
                }
                ...
            }
        """
        pass

    def get_frm_to(self, order: Order) -> tuple[str, str]:
        markets = self.load_markets()
        market_type = markets[order.ticker]['type']

        if order.action == Order.Action.BUY:
            if market_type == "spot":
                frm = util.get_quote_asset(order.ticker)
                to = util.get_base_asset(order.ticker)
            else:
                frm = util.get_margin_asset(order.ticker)
                to = order.ticker
        else:  # sell
            if market_type == "spot":
                frm = util.get_base_asset(order.ticker)
                to = util.get_quote_asset(order.ticker)
            else:
                frm = order.ticker
                to = util.get_margin_asset(order.ticker)

        return frm, to


class RealExchange(Exchange):
    pass


class FakeExchange(Exchange):
    """Fake exchange for backtest and paper trading"""

    @util.validate
    def __init__(self, commission: float = 0.0, **kwargs) -> None:
        from tradingbot.strategy.core import Strategy

        self._commission = commission
        self.strategy: Strategy

    def __repr__(self):
        return f"{self.__class__.__name__}(commission={self._commission})"

    def _reconcile(self, order: Order, exec_prc: float) -> Order:
        frm, to = self.get_frm_to(order)
        frm_qty = exec_prc * order.amount if order.action is Order.Action.BUY else order.amount
        to_qty = exec_prc * order.amount if order.action is Order.Action.SELL else order.amount
        tcost = to_qty * self._commission
        to_qty -= tcost  # charge tcost in <to> asset, i.e. get less

        new_balance = copy.deepcopy(self.strategy.balance)
        try:
            new_balance[frm] -= frm_qty
            new_balance[to] += to_qty
        except ValueError:
            order.status = Order.Status.REJECTED
            order.msg = f"insufficient balance to convert {frm_qty} '{frm}' to {to_qty} '{to}', current balance: {self}"
        else:
            order.status = Order.Status.FILLED
            order.filled_at = self.strategy.now
            order.filled_amount = order.amount
            order.remain_amount = 0.0
            order.exec_prc = exec_prc
            trans = Transaction(frm, frm_qty, to, to_qty, frm, tcost, order.ticker, exec_prc, timestamp=self.strategy.now)
            self.strategy.transaction_history.append(trans)
            self.strategy.balance.data = new_balance.data
        finally:
            order.updated_at = self.strategy.now
            self.strategy.order_history.append(order)
            if order in self.strategy.order:
                self.strategy.order.remove(order)

        return order

    @util.dispatch
    def execute(self, order_type: str, *args, **kwargs) -> Order:
        raise NotImplementedError(order_type)

    @execute.register((__qualname__, "market"))
    def execute_market(self, order_type: str, order: Order) -> Order:
        ticker2close = self.strategy.data.ticker2close
        exec_prc = ticker2close[order.ticker]

        order = self._reconcile(order, exec_prc)
        return order

    @execute.register((__qualname__, "limit"))
    def execute_limit(self, order_type: str, order: Order) -> Order:
        candle = self.strategy.data.ticker2candle[order.ticker]
        match order.status:
            case Order.Status.NEW:
                if order.action is Order.Action.BUY and order.param["price"] >= candle["close"].iloc[-1]:
                    exec_prc = candle["close"].iloc[-1]
                elif order.action is Order.Action.SELL and order.param["price"] <= candle["close"].iloc[-1]:
                    exec_prc = candle["close"].iloc[-1]
                else:
                    order.status = Order.Status.PENDING
                    order.updated_at = self.strategy.now
                    if order not in self.strategy.order:
                        self.strategy.order.append(order)
                    return order
            case Order.Status.PENDING | order.Status.PARTIAL_FILLED:
                high = candle["high"].iloc[-1]
                low = candle["low"].iloc[-1]
                if low <= order.param["price"] <= high:
                    exec_prc = order.param["price"]
                else:
                    order.updated_at = self.strategy.now
                    if order not in self.strategy.order:
                        self.strategy.order.append(order)
                    return order
            case _:
                return order

        order = self._reconcile(order, exec_prc)
        return order

    def update(self, order: Order) -> Order:
        order.updated_at = self.strategy.now
        if order.status in {Order.Status.PENDING, Order.Status.PARTIAL_FILLED} and order not in self.strategy.order:
            self.strategy.order.append(order)
        if order.status in {Order.Status.CANCELED, Order.Status.REJECTED, Order.Status.FILLED}:
            if order in self.strategy.order:
                self.strategy.order.remove(order)
            if order not in self.strategy.order_history:
                self.strategy.order.append(order)
        return order

    def cancel(self, order: Order) -> Order:
        order.status = Order.Status.CANCELED
        order.updated_at = self.strategy.now
        if order in self.strategy.order:
            self.strategy.order.remove(order)
        if order not in self.strategy.order_history:
            self.strategy.order_history.append(order)
        return order

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
    
    def load_markets(self, market_type: str | None = None) -> dict:
        """Load tradable tickers in the market

        Args:
            market_type (str): "spot", "future", "swap", "option", defaults to load all

        Returns:
            dict: 
            {
                "USDT/BTC": {
                    "quote": "USDT",
                    "base": "BTC",
                    "type": "spot",
                    ...
                }
                ...
            }
        """
        tickers = self.strategy.data.ticker2candle.keys()
        markets = defaultdict(dict)
        for ticker in tickers:
            markets[ticker]["quote"] = util.get_quote_asset(ticker)
            markets[ticker]["base"] = util.get_quote_asset(ticker)
            try:
                util.get_strike_price(ticker)
            except AssertionError:
                try:
                    util.get_expiry_date(ticker)
                except AssertionError:
                    try:
                        util.get_margin_asset(ticker)
                    except AssertionError:
                        markets[ticker]["type"] = "spot"
                    except Exception:
                        raise NotImplementedError(ticker)
                    else:
                        markets[ticker]["type"] = "swap"
                else:
                    markets[ticker]["type"] = "future"
            else:
                markets[ticker]["type"] = "option"

        if market_type:
            return {k: v for k, v in markets.items() if v["type"] == market_type}
        
        return markets
            

# class FakeFutureExchange(FakeExchange, FutureExchange):

#     @util.validate
#     def __init__(self, commission: float = 0.0, leverage: int = 1, **kwargs) -> None:
#         self._commission = commission
#         self._leverage = leverage

#     @property
#     def leverage(self) -> int:
#         return self._leverage

#     def _order2qty(self, order: Order, exec_prc: float) -> tuple[float, float]:
#         frm_asset, to_asset = order.frm_asset, order.to_asset
#         quote_ticker, base_ticker = util.get_quote_asset(order.ticker), util.get_base_asset(order.ticker)

#         match order.size_type:
#             case Order.SizeType.PCTG:
#                 from_pos = self.strategy.account[frm_asset]
#                 from_qty = from_pos.qty * order.size
#                 if order.action in {Order.Action.OPEN_LONG, Order.Action.OPEN_SHORT}:
#                     from_qty_scaled = (from_qty / self._leverage) if isinstance(from_pos, MarginPosition) else (from_qty * self._leverage)
#                     _, to_qty = util.convert((frm_asset, from_qty_scaled * (1 - self._commission)), order.ticker, exec_prc)
#                     to_qty *= -1 if order.action is Order.Action.OPEN_SHORT else 1
#                 else:  # close position
#                     to_qty = from_pos.margin[1] * order.size
#             case Order.SizeType.BASE if to_asset == base_ticker:
#                 raise NotImplementedError
#             case Order.SizeType.QUOTE if to_asset == quote_ticker:
#                 to_qty = order.size
#                 _, from_qty = util.convert((to_asset, to_qty * self._leverage), order.ticker, exec_prc)
#                 from_qty *= -1 if order.action is Order.Action.CLOSE_SHORT else 1
#             case Order.SizeType.BASE if frm_asset == base_ticker:
#                 raise NotImplementedError
#             case Order.SizeType.QUOTE if frm_asset == quote_ticker:
#                 raise NotImplementedError
#             case _:
#                 raise NotImplementedError

#         return from_qty, to_qty

#     def _reconcile(self, order: Order, exec_prc: float) -> Order:
#         frm_asset, to_asset = order.frm_asset, order.to_asset
#         quote_ticker = util.get_quote_asset(order.ticker)
#         from_qty, to_qty = self._order2qty(order, exec_prc)

#         fee_qty = from_qty if frm_asset == quote_ticker else to_qty
#         tcost = (quote_ticker, fee_qty * self._commission)  # charge tcost in quote_ticker
#         if to_asset == quote_ticker:
#             to_qty -= tcost[1]

#         if order.action in {Order.Action.OPEN_LONG, Order.Action.OPEN_SHORT}:
#             trans = OpenTransaction(
#                 ticker = order.ticker,
#                 prc = exec_prc,
#                 from_ = (frm_asset, from_qty),  # normal position
#                 to_ = (to_asset, to_qty),  # margin position
#                 tcost = tcost,
#                 timestamp = now,
#                 leverage = self._leverage
#             )
#         else:  # close position
#             trans = CloseTransaction(
#                 ticker = order.ticker,
#                 prc = exec_prc,
#                 from_ = (frm_asset, from_qty),  # margin position
#                 to_ = (to_asset, to_qty),  # normal position
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
