import copy
import functools
import random
import threading
import time

import ccxt
import pandas as pd
import requests
from retry import retry

import tradingbot as tb
import tradingbot.util as util
from tradingbot.exchange.core import Exchange, FutureExchange
from tradingbot.model import Account, Position, Transaction
from tradingbot.order import Order


class CCXTExchange(Exchange):
    def __init__(self, name: str = None, **kwargs):
        config = tb.config
        self._name = name or config.exchange.ccxt.name
        self._param = {**tb.config.exchange.ccxt.model_dump(exclude="name"), **kwargs}

    @property
    def client(self):
        import ccxt

        config = tb.config
        http_proxy = self._param.pop("http_proxy", config.general.http_proxy)
        https_proxy = self._param.pop("https_proxy", config.general.https_proxy)
        param = {**self._param, "proxies": {"http": http_proxy, "https": https_proxy}}
        return getattr(ccxt, self._name)(param)

    @staticmethod
    def get_symbol(ticker: str) -> str:
        return "/".join(ticker.split("/")[::-1])

    @functools.lru_cache(maxsize=128)
    def get_price(self, now: pd.Timestamp, ticker: str) -> float:
        return self.client.fetch_ticker(self.get_symbol(ticker))["last"]

    @retry((requests.exceptions.ReadTimeout, requests.exceptions.ProxyError, requests.exceptions.ConnectionError,
            ccxt.errors.RequestTimeout), tries=3)
    def update_order(self, now: pd.Timestamp, order: Order):
        import ccxt

        if order.status in {Order.Status.CANCELED, Order.Status.REJECTED}:
            self.strategy.order_history.append((now, order))
            if order in self.strategy.open_order:
                self.strategy.open_order.remove(order)
            return
        elif order.id_ is None:  # for other reason where id is not assigned by code 
            return

        try:
            order_info = self.client.fetch_order(order.id_, symbol=self.get_symbol(order.ticker))
        except ccxt.errors.OrderNotFound:
            util.logger.warning(f"{order.id_=} not found. Ignored. This should not happen!")
            return

        match order_info["status"]:
            case "open":
                order.status = Order.Status.PARTIAL_FILLED if order_info["filled"] > 0.0 else Order.Status.PENDING
                self.strategy.logger.debug(f"order open: {order}")
                if order not in self.strategy.open_order:
                    self.strategy.open_order.append(order)
            case "closed":
                order.status = Order.Status.FILLED
                self.strategy.logger.info(f"order filled: {order}")
                from_ticker, to_ticker = order.from_ticker, order.to_ticker
                from_qty = order_info["cost"] if order_info["side"] == "buy" else order_info["amount"]
                to_qty = (
                    (order_info["amount"] - order_info["fee"]["cost"])
                    if order_info["side"] == "buy"
                    else (order_info["cost"] - order_info["fee"]["cost"])
                )
                trans = Transaction(
                    ticker=order.ticker,
                    prc=order_info["average"],
                    from_=(from_ticker, from_qty),
                    to_=(to_ticker, to_qty),
                    tcost=(order_info["fee"]["currency"], order_info["fee"]["cost"]),
                    timestamp=pd.Timestamp(order_info["datetime"]),
                )
                from_pos, to_pos, _ = trans.split()
                account = copy.deepcopy(self.strategy.account)
                account += to_pos
                account -= from_pos
                self.strategy.account = account
                self.strategy.transaction_history.append(trans)
                self.strategy.order_history.append((pd.Timestamp(order_info["datetime"]), order))
                if order in self.strategy.open_order:
                    self.strategy.open_order.remove(order)
            case "canceled":
                order.status = Order.Status.CANCELED
                self.strategy.logger.info(f"order canceled: {order}")
                self.strategy.order_history.append((now, order))
                if order in self.strategy.open_order:
                    self.strategy.open_order.remove(order)

    def _execute_market(self, now: pd.Timestamp, order: Order) -> Order:
        import ccxt

        assert order.type is Order.Type.MARKET, f"Invalid order type: {order.type}"
        assert order.action in {Order.Action.BUY, Order.Action.SELL}, f"Invalid order action: {order.action}"
        assert order.status is Order.Status.NEW, f"Invalid order status: {order.status}"
        quote_ticker, base_ticker = util.get_quote_ticker(order.ticker), util.get_base_ticker(order.ticker)

        symbol = self.get_symbol(order.ticker)
        type_ = "market"
        side = "buy" if order.action is Order.Action.BUY else "sell"
        match order.size_type:
            case Order.SizeType.PCTG if side == "buy":  # buy BTC, cost USDT
                price = self.get_price(now, order.ticker)
                amount = self.strategy.account[quote_ticker].qty * order.size / price
            case Order.SizeType.PCTG if side == "sell":  # sell BTC, cost BTC
                amount = self.strategy.account[base_ticker].qty * order.size
            case Order.SizeType.QUOTE:
                amount = order.size / self.get_price(now, order.ticker)
            case Order.SizeType.BASE:
                amount = order.size
        try:
            self.strategy.logger.debug(f"Calling client.create_order({symbol}, {type_}, {side}, {amount})")
            order_resp = self.client.create_order(symbol=symbol, type=type_, side=side, amount=amount, price=None)
        except ccxt.errors.InsufficientFunds as e:
            self.strategy.logger.warning(f"Order rejected: {order}, due to InsufficientFunds {e}")
            order.status = Order.Status.REJECTED
            return order
        except ccxt.errors.InvalidOrder as e:
            self.strategy.logger.error(f"Order rejected: {order}, due to InvalidOrder {e}")
            order.status = Order.Status.REJECTED
            return order
        except Exception as e:
            self.strategy.logger.error(f"Order failed: {order}, due to {e!r}")
            order.status = Order.Status.REJECTED
            return order

        order.id_ = order_resp["id"]
        self.strategy.logger.info(f"Order posted: {order}")
        self.update_order(now=now, order=order)
        return order

    def _execute_limit(self, now: pd.Timestamp, order: Order, check: bool = True) -> Order:
        import ccxt

        assert order.type is Order.Type.LIMIT, f"Invalid order type: {order.type}"
        assert order.action in {Order.Action.BUY, Order.Action.SELL}, f"Invalid order action: {order.action}"
        assert order.status in {Order.Status.NEW, Order.Status.PENDING, Order.Status.CANCELED, Order.Status.PARTIAL_FILLED}, f"Invalid order status: {order.status}"
        quote_ticker, base_ticker = util.get_quote_ticker(order.ticker), util.get_base_ticker(order.ticker)

        if order.status in {Order.Status.PENDING, Order.Status.PARTIAL_FILLED}:
            return order
        elif order.status is Order.Status.CANCELED:
            try:
                self.client.cancel_order(str(order.id_), symbol=self.get_symbol(order.ticker))
            except ccxt.errors.OrderNotFound:
                try:
                    order_info = self.client.fetch_order(str(order.id_), symbol=self.get_symbol(order.ticker))
                except Exception as e:
                    self.strategy.logger.debug(f"order cancel and fetch failed for {order.id_=}: due to {e!r}. Ignored.")
                else:
                    if order_info["status"] == "closed":
                        order.status = Order.Status.FILLED
            return order

        symbol = self.get_symbol(order.ticker)
        type_ = "limit"
        side = "buy" if order.action is Order.Action.BUY else "sell"
        match order.size_type:
            case Order.SizeType.PCTG if side == "buy":  # buy BTC, cost USDT
                price = order.param["price"] if type_ == "limit" else self.get_price(now, order.ticker)
                amount = self.strategy.account[quote_ticker].qty * order.size / price
            case Order.SizeType.PCTG if side == "sell":  # sell BTC, cost BTC
                amount = self.strategy.account[base_ticker].qty * order.size
            case Order.SizeType.QUOTE:
                amount = order.size / order.param["price"]
            case Order.SizeType.BASE:
                amount = order.size
        try:
            price = order.param["price"]
            self.strategy.logger.debug(f"Calling client.create_order({symbol}, {type_}, {side}, {amount}, {price})")
            order_resp = self.client.create_order(symbol=symbol, type=type_, side=side, amount=amount, price=price)
        except ccxt.errors.InsufficientFunds as e:
            self.strategy.logger.warning(f"Order rejected: {order}, due to InsufficientFunds {e}")
            order.status = Order.Status.REJECTED
            return order
        except ccxt.errors.InvalidOrder as e:
            self.strategy.logger.error(f"Order rejected: {order}, due to InvalidOrder {e}")
            order.status = Order.Status.REJECTED
            return order
        except Exception as e:
            self.strategy.logger.error(f"Order failed: {order}, due to {e!r}")
            order.status = Order.Status.REJECTED
            return order

        order.id_ = order_resp["id"]
        order.status = Order.Status.PENDING
        self.strategy.logger.info(f"Order posted: {order}")

        if check:
            def _check_order(now: pd.Timestamp, order: Order, frequency: float = None):
                """
                Args:
                    frequency (float, optional): refresh rate in seconds
                """
                frequency = frequency or (self.client.rateLimit / 10 + random.randint(1, 10))  # rateLimit is in milliseconds, sleep for x100 of it

                while order.status is Order.Status.PENDING:
                    self.strategy.logger.debug(f"Checking order: {order}")
                    self.update_order(now=now, order=order)
                    time.sleep(frequency)
                
                self.strategy.logger.debug(f"Checked order: {order}")
                
            threading.Thread(target=_check_order, args=(now, order), daemon=True).start()  # schedule periodic order check
        return order
    
    def _execute_trailing_limit(self, now: pd.Timestamp, order: Order) -> Order:
        assert order.type is Order.Type.TRAILING_LIMIT

        init_now = now
        init_order = copy.deepcopy(order)  # make a limit order from trailing order
        init_order.type = Order.Type.LIMIT
        init_order.param = {"price": self.get_price(now, order.ticker) * order.param["offset"]}
        init_order = self._execute_limit(now, init_order, check=False)
        self.update_order(now=now, order=init_order)

        prev_order, next_order = copy.deepcopy(init_order), copy.deepcopy(init_order)
        if init_order.status in {Order.Status.PENDING, Order.Status.PARTIAL_FILLED}:
            interval_td = pd.Timedelta(order.param["interval"])
            interval_sec = interval_td.total_seconds()
            time.sleep(interval_sec)
            now += interval_td

            while prev_order.status in {Order.Status.PENDING, Order.Status.PARTIAL_FILLED}:
                prev_order.cancel(self, now=now)
                order_info = self.client.fetch_order(prev_order.id_, symbol=self.get_symbol(order.ticker))
                if order_info["status"] == "closed": 
                    break

                next_order = Order(
                    ticker=order.ticker, 
                    type=Order.Type.LIMIT,
                    action=order.action, 
                    size_type=Order.SizeType.BASE, 
                    size=order_info["remaining"], 
                    param={"price": self.get_price(now, order.ticker) * order.param["offset"]}
                )
                next_order = self._execute_limit(now, next_order, check=False)
                self.strategy.logger.debug(
                    f"trailing limit replaced: prev_order=({prev_order.param['price']}, {prev_order.size}) -> next_order=({next_order.param['price']}, {next_order.size})"
                )

                time.sleep(interval_sec)
                now += interval_td

                self.update_order(now=now, order=next_order)
                prev_order = next_order

        order.status = prev_order.status
        order.id_ = prev_order.id_ 
        self.strategy.logger.info(f"trailing limit completed in {(now - init_now).total_seconds() / 60 :.2f} mins: {order=}")
        if order in self.strategy.open_order:
            self.strategy.open_order.remove(order)
        return order

    def execute(self, now: pd.Timestamp, order: Order, **kwargs) -> Order:
        """
        Args:
            now (pd.Timestamp):
            order (Order):
                
        Returns:
            Order
        """
        if order.type is Order.Type.LIMIT:
            return self._execute_limit(now, order, **kwargs)
        elif order.type is Order.Type.MARKET:
            return self._execute_market(now, order)
        elif order.type is Order.Type.TRAILING_LIMIT:
            return self._execute_trailing_limit(now, order)
        raise NotImplementedError
    
    def _check_order(self, now: pd.Timestamp, order: Order, frequency: float = None):
        """
        Args:
            frequency (float, optional): refresh rate in seconds
        """
        frequency = frequency or (self.client.rateLimit / 5 + random.randint(1, 10))  # rateLimit is in milliseconds, sleep for x200 of it

        while order.status is Order.Status.PENDING:
            self.strategy.logger.debug(f"Checking order: {order}")
            self.update_order(now=now, order=order)
            time.sleep(frequency)
        
        self.strategy.logger.debug(f"Checked order: {order}")

    def reflect_account(self, now: pd.Timestamp, account: Account, ticker: str) -> Account:
        """
        Args:
            now (pd.Timestamp):
            account (Account):
            ticker (str): e.g. "USDT/BTC"
        Returns:
            Account
        """
        account = copy.deepcopy(account)
        quote_ticker, base_ticker = util.get_quote_ticker(ticker), util.get_base_ticker(ticker)
        balance = self.client.fetch_balance({"ccy": base_ticker})
        base_info = balance.get(base_ticker, {})

        if base_total := base_info.get("total", 0):
            prc = self.get_price(now, ticker)
            base_detail = next((det for det in balance["info"]["data"][0]["details"] if det["ccy"] == base_ticker), {})
            base_pos = Position(ticker=base_ticker, qty=base_total, entry_prc=float(base_detail.get("openAvgPx", prc) or 0.0), market_prc_=prc)
            quote_pos = Position(ticker=quote_ticker, qty=max(account[quote_ticker].qty - base_total * prc, 0.0))
            account[base_ticker] = base_pos
            account[quote_ticker] = quote_pos

        return account

class CCXTFutureExchange(CCXTExchange, FutureExchange):
    pass
