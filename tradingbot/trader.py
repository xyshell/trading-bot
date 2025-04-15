from functools import cached_property
import time

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
    def implement_market(self, method: str, frm_qty: float, frm: str, to: str, param: dict) -> None:
        """trading algorithm: 'market', e.g.

        param:
            n (int): number of orders to split into
            delay (int): delay between orders in seconds
        """
        self.strategy.logger.debug(f"Implementing '{method}': {frm_qty} '{frm}' -> '{to}', {param=}")
        n = param.get("n", 1)
        delay = param.get("delay", 0)
        
        action, ticker = self._get_action_ticker(frm, to)
        prc = self.strategy.data.ticker2close[ticker]
        total_amount = frm_qty / prc if action == "buy" else frm_qty
        each_amount = total_amount / n

        for _ in range(n):
            order = Order(
                action=action, 
                ticker=ticker, 
                amount=each_amount, 
                type="market", 
                created_at=self.strategy.now, 
                updated_at=self.strategy.now
            )
            order = self.exchange.execute("market", order)
            time.sleep(delay)

    @implement.register((__qualname__, "limit"))
    def implement_limit(self, method: str, frm_qty: float, frm: str, to: str, param: dict) -> None:
        """trading algorithm: 'limit'
        """
        self.strategy.logger.debug(f"Implementing '{method}': {frm_qty} '{frm}' -> '{to}', {param=}")

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

    @implement.register((__qualname__, "limit2market"))
    def implement_limit2market(self, method: str, frm_qty: float, frm: str, to: str, param: dict) -> None:
        """trading algorithm: 'limit2market', e.g.

        param:
            price (float): limit price
            wait (float): wait time in seconds
            n (int): number of market orders to split into
            delay (int): delay between market orders in seconds
            scaler (float): scaling factor for order amount from limit to market order to ensure execution
        
        Example:
            1. place a limit order at 80_000, wait for 300s, if not filled, scale the order amount to 99% and split into 5 market orders with 60s delay in between
            param={"price": 80_000, "wait": 300, "n": 5, "delay": 60, "scaler": 0.99}
        """
        if self.mode in {"backtest", "paper"}: 
            return self.implement("market", frm_qty, frm, to, {})

        self.strategy.logger.debug(f"Implementing '{method}': {frm_qty} '{frm}' -> '{to}', {param=}")
        price = param["price"]
        wait = param.get("wait", 0)
        n = param.get("n", 1)
        delay = param.get("delay", 0)
        scaler = param.get("scaler", 1.0)

        action, ticker = self._get_action_ticker(frm, to)
        prc = self.strategy.data.ticker2close[ticker]
        limit_order = Order(
            action=action, 
            ticker=ticker,
            amount=frm_qty / prc if action == "buy" else frm_qty, 
            type="limit", 
            param={"price": price},
            created_at=self.strategy.now, 
            updated_at=self.strategy.now
        )
        limit_order = self.exchange.execute("limit", limit_order)
        self.strategy.logger.debug(f"Limit order placed: {limit_order}")

        if limit_order.status is Order.Status.FILLED:
            self.strategy.logger.debug(f"Limit order filled: {limit_order}")
            return
        elif limit_order.status in {Order.Status.PENDING, Order.Status.PARTIAL_FILLED}:  # wait
            time.sleep(wait)
            limit_order = self.exchange.update(limit_order)
            if limit_order.status in {
                Order.Status.FILLED,
                Order.Status.CANCELED,  # canceled by user
            }:
                return
            self.exchange.cancel(limit_order)  # cancel limit order
            self.strategy.logger.debug(f"Limit order canceled: {limit_order}")

            total_amount = limit_order.remain_amount * scaler
            each_amount = total_amount / n

            for _ in range(n):
                order = Order(
                    action=action, 
                    ticker=ticker, 
                    amount=each_amount, 
                    type="market", 
                    created_at=self.strategy.now, 
                    updated_at=self.strategy.now
                )
                order = self.exchange.execute("market", order)
                time.sleep(delay)
