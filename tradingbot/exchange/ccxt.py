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
from tradingbot.exchange.core import RealExchange
from tradingbot.account import Account
from tradingbot.position import Position, SpotPosition
from tradingbot.transaction import Transaction
from tradingbot.order import Order


class CCXTExchange(RealExchange):
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
        """currency quote: USDT/BTC -> CCXT symbol: BTC/USDT"""
        return "/".join(ticker.split("/")[::-1])

    @functools.lru_cache(maxsize=128)
    def get_price(self, now: pd.Timestamp, ticker: str) -> float:
        """Get current price for a ticker 
        
        Args:
            now (pd.Timestamp): not used but required for caching purposes
            ticker (str): e.g. "USDT/BTC"

        Returns:
            float
        """
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
            # TODO: better resizer
            for multiplier in [0.9, 0.8, 0.7, 0.6, 0.5]:
                new_amount = amount * multiplier
                try:
                    self.strategy.logger.debug(f"Calling client.create_order({symbol}, {type_}, {side}, {new_amount}, {price})")
                    order_resp = self.client.create_order(symbol=symbol, type=type_, side=side, amount=new_amount, price=price)
                except ccxt.errors.InsufficientFunds as e:
                    self.strategy.logger.debug(f"Order rejected: {order}, due to InsufficientFunds {e}")
                    continue
                else:
                    break
            else:
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


    def get_position(self, asset: str, now: pd.Timestamp | None = None, **kwargs) -> Position:
        """Get current position for an asset
        
        Args:
            asset (str): e.g. "USDT"

        Returns:
            Position
        """
        now = now or util.get_random_timestamp()
        balance = self.fetch_balance(now, **kwargs)[asset]
        return Position(asset=asset, qty=balance)

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
            base_pos = Position(asset=base_ticker, qty=base_total, entry_prc=float(base_detail.get("openAvgPx", prc) or 0.0), market_prc_=prc)
            quote_pos = Position(asset=quote_ticker, qty=max(account[quote_ticker].qty - base_total * prc, 0.0))
            account[base_ticker] = base_pos
            account[quote_ticker] = quote_pos

        return account

    def ping(self) -> bool:
        return "ok" in self.client.fetch_status()

    # ------------------------------------- wrapper methods -------------------------------------
    def fetch_balance(self, balance_type: str = "total") -> dict:
        """Fetch current balance
        
        Args:
            balance_type (str): "total", "free", "used"
        
        Returns:
            dict
        """
        return self.client.fetch_balance()[balance_type]

    @functools.lru_cache(maxsize=1)
    def _load_markets(self) -> dict:
        return self.client.load_markets()

    def load_markets(self, market_type: str | None = None) -> dict:
        """

        Args:
            market_type (str): "spot", "future", "swap", "option", defaults to load all

        Returns:
            dict
        """
        markets = self._load_markets()
        spot_markets = {k.replace(f"{v['base']}/{v['quote']}", f"{v['quote']}/{v['base']}"): v for k, v in markets.items() if v["type"] == "spot"}  # BTC/USDT (base/quote)
        future_markets = {k.replace(f"{v['base']}/{v['quote']}", f"{v['quote']}/{v['base']}"): v for k, v in markets.items() if v["type"] == "future"}  # BTC/USDT:USDT-250404 (base/quote:settle-date)
        swap_markets = {k.replace(f"{v['base']}/{v['quote']}", f"{v['quote']}/{v['base']}"): v for k, v in markets.items() if v["type"] == "swap"}  # BTC/USDT:USDT (base/quote:settle)
        option_markets = {k.replace(f"{v['base']}/{v['quote']}", f"{v['quote']}/{v['base']}"): v for k, v in markets.items() if v["type"] == "option"}  # BTC/USD:BTC-250404-83000-C (base/quote:settle-date-strike-C/P)
        
        # flip base/quote to quote/base
        match market_type:
            case "spot":
                return spot_markets
            case "future":
                return future_markets
            case "swap":
                return swap_markets
            case "option":
                return option_markets
            case None:
                return spot_markets | future_markets | swap_markets | option_markets
            case _:
                raise NotImplementedError

    @functools.cached_property
    def ticker2symbol(self) -> dict[str, str]:
        markets = self.load_markets()
        return {k: v["symbol"] for k, v in markets.items()}

    @functools.cached_property
    def symbol2ticker(self) -> dict[str, str]:
        return {v: k for k, v in self.ticker2symbol.items()}

    def fetch_tickers(self, tickers: list[str]) -> dict:
        symbols = [self.ticker2symbol[ticker] for ticker in tickers]
        status = self.client.fetch_tickers(symbols)
        return {self.symbol2ticker[k]: v for k, v in status.items()}
