import abc
from collections import defaultdict
import copy
import logging

import numpy as np

from tradingbot.position import Position
import tradingbot.util as util
from tradingbot.util import PosFloat
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

    @abc.abstractmethod
    def fetch_positions(self) -> dict[str, dict[str, Position]]:
        """Fetch open positions in the exchange

        Returns:
            dict[str, Position]: {
                "USDT/BTC:USDT": {
                    "long": Position(...),
                    "short": Position(...),
                }
                ...
            }
        """
        pass

    @abc.abstractmethod
    def set_leverage(self, ticker: str, side: str, leverage: PosFloat) -> None:
        """Set leverage for margin trading

        Args:
            ticker (str): e.g. "USDT/BTC:USDT"
            side (str): "long" or "short"
            leverage (NonNegFloat): leverage
        """
        pass

    def get_frm_to(self, order: Order) -> tuple[str, str]:
        markets = self.load_markets()
        market_type = markets[order.ticker]['type']

        if order.action in {Order.Action.BUY, Order.Action.OPEN_LONG, Order.Action.OPEN_SHORT}:
            if market_type == "spot":
                frm = util.get_quote_asset(order.ticker)
                to = util.get_base_asset(order.ticker)
            else:
                frm = util.get_margin_asset(order.ticker)
                to = order.ticker
        else:  # SELL, CLOSE_LONG, CLOSE_SHORT
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

    def _reconcile_asset(self, order: Order, exec_prc: float) -> Order:
        if order.action not in {Order.Action.BUY, Order.Action.SELL}:
            raise ValueError(f"order action must be 'BUY' or 'SELL', got {order.action}")
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

    def _reconcile_position(self, order: Order, exec_prc: float) -> Order:
        if order.action not in {Order.Action.OPEN_LONG, Order.Action.CLOSE_LONG, Order.Action.OPEN_SHORT, Order.Action.CLOSE_SHORT}:
            raise ValueError(f"order action must be 'OPEN_LONG', 'CLOSE_LONG', 'OPEN_SHORT' or 'CLOSE_SHORT', got {order.action}")
        derivative_markets = {k: v for k, v in self.load_markets().items() if v["type"] in {"future", "swap", "option"}}
        
        frm, to = self.get_frm_to(order)
        new_balance = copy.deepcopy(self.strategy.balance)
        if frm in derivative_markets:  # close position
            existing_pos = self.fetch_positions([frm])[frm][order.side]
            margin = order.amount * exec_prc * derivative_markets[frm]["contractSize"] / existing_pos.leverage
            tcost = margin * self._commission
            to_qty = existing_pos.margin + existing_pos.pnl + existing_pos.fee - tcost  # add fee back to avoid double counting

            minus_pos = Position(
                ticker=order.ticker,
                side=order.side,
                amount=-order.amount,
                leverage=existing_pos.leverage,
                entry_prc=exec_prc,
                mark_prc=exec_prc,
                fee=tcost,
                created_at=self.strategy.now,
                updated_at=self.strategy.now,
                contract_size=derivative_markets[frm]["contractSize"],
            )
            try:
                new_balance.close_position(minus_pos)
                new_balance[to] += to_qty
            except ValueError:
                order.status = Order.Status.REJECTED
                order.msg = "insufficient balance to close position"
            else:
                order.status = Order.Status.FILLED
                order.filled_at = self.strategy.now
                order.filled_amount = order.amount
                order.remain_amount = 0.0
                order.exec_prc = exec_prc
                frm_qty = order.amount if order.side == "long" else -order.amount
                trans = Transaction(frm, frm_qty, to, to_qty, to, tcost, order.ticker, exec_prc, timestamp=self.strategy.now)
                self.strategy.transaction_history.append(trans)
                self.strategy.balance.data = new_balance.data
            finally:
                order.updated_at = self.strategy.now
                self.strategy.order_history.append(order)
                if order in self.strategy.order:
                    self.strategy.order.remove(order)
        elif to in derivative_markets:  # open position
            existing_pos = self.fetch_positions([to])[to][order.side]
            order.amount *= (1 - self._commission)
            margin = order.amount * exec_prc * derivative_markets[to]["contractSize"] / existing_pos.leverage
            tcost = margin * self._commission
            frm_qty = margin + tcost
            
            plus_pos = Position(
                ticker=order.ticker,
                side=order.side,
                amount=order.amount,
                leverage=existing_pos.leverage,
                entry_prc=exec_prc,
                mark_prc=exec_prc,
                margin=margin,
                fee=tcost,
                created_at=self.strategy.now,
                updated_at=self.strategy.now,
                contract_size=derivative_markets[to]["contractSize"],
            )
            try:
                new_balance.add_position(plus_pos)
                new_balance[frm] -= frm_qty
            except ValueError:
                order.status = Order.Status.REJECTED
                order.msg = "insufficient balance to open position"
            else:
                order.status = Order.Status.FILLED
                order.filled_at = self.strategy.now
                order.filled_amount = order.amount
                order.remain_amount = 0.0
                order.exec_prc = exec_prc
                to_qty = order.amount if order.side == "long" else -order.amount
                trans = Transaction(frm, frm_qty, to, to_qty, frm, tcost, order.ticker, exec_prc, timestamp=self.strategy.now)
                self.strategy.transaction_history.append(trans)
                self.strategy.balance.data = new_balance.data
            finally:
                order.updated_at = self.strategy.now
                self.strategy.order_history.append(order)
                if order in self.strategy.order:
                    self.strategy.order.remove(order)            

    @util.dispatch
    def execute(self, order_type: str, *args, **kwargs) -> Order:
        raise NotImplementedError(order_type)

    @execute.register((__qualname__, "market"))
    def execute_market(self, order_type: str, order: Order) -> Order:
        ticker2close = self.strategy.data.ticker2close
        exec_prc = ticker2close[order.ticker]

        if order.action in {Order.Action.BUY, Order.Action.SELL}:
            order = self._reconcile_asset(order, exec_prc)
        else:  # OPEN_LONG, OPEN_SHORT, CLOSE_LONG, CLOSE_SHORT
            order = self._reconcile_position(order, exec_prc)
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

        order = self._reconcile_asset(order, exec_prc)
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
                "USDT/BTC": {  # spot market
                    "quote": "USDT",
                    "base": "BTC",
                    "type": "spot",
                    ...
                },
                "USDT/BTC:USDT": {  # swap market
                    "quote": "USDT",
                    "base": "BTC",
                    "type": "swap",
                    "contractSize": 1.0,
                    ...
                },
                "USDT/BTC:USDT-250627": {  # future market
                    "quote": "USDT",
                    "base": "BTC",
                    "type": "future",
                    "contractSize": 1.0,
                    ...
                },
                "USD/BTC:BTC-250419-84500-C: {  # option market
                    "quote": "USD",
                    "base": "BTC",
                    "type": "option",
                    "contractSize": 1.0,
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
                        markets[ticker]["contractSize"] = 1.0
                else:
                    markets[ticker]["type"] = "future"
                    markets[ticker]["contractSize"] = 1.0
            else:
                markets[ticker]["type"] = "option"
                markets[ticker]["contractSize"] = 1.0

        if market_type:
            return {k: v for k, v in markets.items() if v["type"] == market_type}
        
        return markets
    
    def fetch_positions(self, tickers: list[str]) -> dict[str, dict[str, Position]]:
        """Fetch open positions in the exchange
        
        Returns:
            dict[str, Position]: {
                "USDT/BTC:USDT": {
                    "long": Position(...),
                    "short": Position(...),
                }
                ...
            }
        """
        res = defaultdict(dict)
        for ticker in tickers:
            pos_pair = self.strategy.balance[ticker] or {}
            if pos_long := pos_pair.get("long"):
                res[ticker]["long"] = pos_long
            else:
                res[ticker]["long"] = Position(
                    ticker=ticker,
                    side="long",
                    amount=0.0,
                    leverage=np.nan,
                    entry_prc=np.nan,
                    mark_prc=np.nan,
                    margin=0.0,
                    fee=0.0,
                    id_=None,
                    created_at=self.strategy.now,
                    updated_at=self.strategy.now,
                    contract_size=1.0,
                    liquidation_prc_=np.nan,
                    notional_=np.nan
                )
            if pos_short := pos_pair.get("short"):
                res[ticker]["short"] = pos_short
            else:
                res[ticker]["short"] = Position(
                    ticker=ticker,
                    side="short",
                    amount=0.0,
                    leverage=np.nan,
                    entry_prc=np.nan,
                    mark_prc=np.nan,
                    margin=0.0,
                    fee=0.0,
                    created_at=self.strategy.now,
                    updated_at=self.strategy.now,
                    contract_size=1.0,
                    liquidation_prc_=np.nan,
                    notional_=np.nan
                )
        return res

    def set_leverage(self, ticker: str, side: str, leverage: PosFloat) -> None:
        if pos := self.strategy.balance[ticker].get(side): 
            pos.leverage = leverage
        else:
            self.strategy.balance.add_position(
                Position(
                    ticker=ticker,
                    side=side,
                    amount=0.0,
                    leverage=leverage,
                    entry_prc=np.nan,
                    mark_prc=np.nan,
                    margin=0.0,
                    fee=0.0,
                    created_at=self.strategy.now,
                    updated_at=self.strategy.now,
                    contract_size=1.0,
                    liquidation_prc_=np.nan,
                    notional_=np.nan
                )
            )
