from collections import defaultdict
import functools

import ccxt
import numpy as np
import pandas as pd
import requests
from retry import retry

import tradingbot as tb
import tradingbot.util as util
from tradingbot.util import PosFloat
from tradingbot.exchange.core import RealExchange
from tradingbot.position import Position
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
        """get CCXT symbol from currency quote ticker, e.g.
        USDT/BTC -> BTC/USDT
        USDT/BTC:USDT-250404 -> BTC/USDT:USDT-250404
        """
        if ":" in ticker:
            left, right = ticker.split(":")
            return ":".join(["/".join(left.split("/")[::-1]), right])
        else:
            return "/".join(ticker.split("/")[::-1])

    @functools.lru_cache(maxsize=128)
    def get_price(self, ticker: str, now: pd.Timestamp) -> float:
        """Get current price for a ticker 
        
        Args:
            ticker (str): e.g. "USDT/BTC"
            now (pd.Timestamp): for caching purposes

        Returns:
            float
        """
        return self.client.fetch_ticker(self.get_symbol(ticker))["last"]

    @retry((requests.exceptions.ReadTimeout, 
            requests.exceptions.ProxyError, 
            requests.exceptions.ConnectionError,
            ccxt.errors.RequestTimeout), tries=3)
    def _safe_fetch_order(self, order_id: str, symbol: str) -> dict:
        return self.client.fetch_order(order_id, symbol=symbol)

    @util.dispatch
    def execute(self, order_type: str, *args, **kwargs) -> Order:
        raise NotImplementedError(order_type)

    def _create_order(self, order: Order) -> dict:
        import ccxt

        symbol = self.get_symbol(order.ticker)
        action = order.action
        type = order.type.value
        amount = order.amount
        price = order.param.get("price")

        params = {}
        if action in {Order.Action.BUY, Order.Action.SELL}:  # spot order
            side = action.value
        else:  # derivative order
            params["tdMode"] = "isolated"
            if action is Order.Action.OPEN_LONG:
                side = "buy"
                params["posSide"] = "long"
                params["reduceOnly"] = False
            elif action is Order.Action.CLOSE_LONG:
                side = "sell"
                params["posSide"] = "long"
                params["reduceOnly"] = True
            elif action is Order.Action.OPEN_SHORT:
                side = "sell"
                params["posSide"] = "short"
                params["reduceOnly"] = False
            elif action is Order.Action.CLOSE_SHORT:
                side = "buy"
                params["posSide"] = "short"
                params["reduceOnly"] = True

        try:
            self.strategy.logger.debug(f"Calling client.create_order('{symbol}', '{type}', '{side}', '{amount}', '{params})")
            resp = self.client.create_order(symbol=symbol, type=type, side=side, amount=amount, price=price, params=params)
        except Exception as e:
            order.status = Order.Status.REJECTED
            order.updated_at = self.strategy.now
            if isinstance(e, ccxt.errors.InsufficientFunds):
                self.strategy.logger.warning(f"Order rejected: {order}, due to InsufficientFunds {e}")
                order.msg = f"Insufficient funds: {e}"
            elif isinstance(e, ccxt.errors.InvalidOrder):
                self.strategy.logger.error(f"Order rejected: {order}, due to InvalidOrder {e}")
                order.msg = f"Invalid order: {e}"
            else:
                self.strategy.logger.error(f"Order failed: {order}, due to {e}")
                order.msg = f"Unknown failure: {e}"
            if order in self.strategy.order:
                self.strategy.order.remove(order)
            if order not in self.strategy.order_history:
                self.strategy.order_history.append(order)
        else:
            order.id_ = resp["id"]
            self.update(order)
            self.strategy.logger.info(f"Order posted: {order}")
        return order

    @execute.register((__qualname__, "market"))
    def execute_market(self, order_type: str, order: Order) -> Order:
        return self._create_order(order)
        
    @execute.register((__qualname__, "limit"))
    def execute_limit(self, order_type: str, order: Order) -> Order:
        return self._create_order(order)

    def update(self, order: Order) -> Order:
        if order.status is Order.Status.REJECTED:
            return order
        markets = self.load_markets()
        derivative_markets = {k: v for k, v in markets.items() if v["type"] in {"future", "swap", "option"}}
        symbol = self.get_symbol(order.ticker)
        info = self._safe_fetch_order(order.id_, symbol=symbol)
        order.updated_at = pd.Timestamp(info["timestamp"], unit="ms")
        order.filled_amount = info["filled"]
        order.remain_amount = info["remaining"]
        order.exec_prc = info["average"] or np.nan

        match info["status"]:
            case "open" if info["filled"] == 0.0:
                order.status = Order.Status.PENDING
                if order not in self.strategy.order:
                    self.strategy.order.append(order)
            case "open" if info["filled"] > 0.0 and info["remaining"] > 0.0:
                order.status = Order.Status.PARTIAL_FILLED
                if order not in self.strategy.order:
                    self.strategy.order.append(order)
            case "closed":
                order.status = Order.Status.FILLED
                order.filled_at = pd.Timestamp(info["timestamp"], unit="ms")
                
                frm, to = self.get_frm_to(order)
                if order.action in {
                    Order.Action.BUY, Order.Action.OPEN_LONG, Order.Action.OPEN_SHORT
                }:
                    frm_qty = info["cost"]
                    to_qty = order.amount
                    if order.action in {Order.Action.OPEN_LONG, Order.Action.OPEN_SHORT}:
                        frm_qty /= float(info["info"]["lever"])
                else:  # SELL, CLOSE_LONG, CLOSE_SHORT
                    frm_qty = order.amount
                    to_qty = info["cost"]
                    if order.action in {Order.Action.CLOSE_LONG, Order.Action.CLOSE_SHORT}:
                        to_qty /= float(info["info"]["lever"])
                        to_qty += float(info["info"]["pnl"])

                trans = Transaction(
                    frm, frm_qty, 
                    to, to_qty, 
                    info["fee"]["currency"], info["fee"]["cost"], 
                    order.ticker,
                    info["average"], 
                    timestamp=self.strategy.now
                )
                self.strategy.transaction_history.append(trans)
                if frm in derivative_markets:
                    pos_pair = self.strategy.balance[frm]
                    pos = pos_pair[info["info"]["posSide"]]
                    minus_pos = Position(
                        ticker=order.ticker,
                        side=order.side,
                        amount=-order.amount,
                        leverage=pos.leverage,
                        entry_prc=info["average"],
                        mark_prc=info["average"],
                        margin=-pos.margin * order.amount / pos.amount,  # pro-rata margin
                        fee=-pos.fee * order.amount / pos.amount,  # pro-rata fee
                        created_at=self.strategy.now,
                        updated_at=self.strategy.now,
                        contract_size=derivative_markets[frm]["contractSize"],
                    )
                    self.strategy.balance.close_position(minus_pos)
                else:  # spot
                    self.strategy.balance[frm] -= frm_qty
                if to in derivative_markets:
                    pos_pair = self.strategy.balance[to]
                    plus_pos = Position(
                        ticker=order.ticker,
                        side=order.side,
                        amount=order.amount,
                        leverage=info["info"]["lever"],
                        entry_prc=info["average"],
                        mark_prc=info["average"],
                        margin=info["cost"] / float(info["info"]["lever"]),
                        fee=info["fee"]["cost"],
                        created_at=self.strategy.now,
                        updated_at=self.strategy.now,
                        contract_size=derivative_markets[to]["contractSize"],
                    )
                    self.strategy.balance.add_position(plus_pos)
                else:  # spot
                    self.strategy.balance[to] += to_qty
                if order in self.strategy.order:
                    self.strategy.order.remove(order)
                if order not in self.strategy.order_history:
                    self.strategy.order_history.append(order)
            case "canceled":
                order.status = Order.Status.CANCELED
                if order in self.strategy.order:
                    self.strategy.order.remove(order)
                if order not in self.strategy.order_history:
                    self.strategy.order_history.append(order)

        return order

    @retry((requests.exceptions.ReadTimeout, 
            requests.exceptions.ProxyError, 
            requests.exceptions.ConnectionError,
            ccxt.errors.RequestTimeout), tries=3)
    def _safe_cancel_order(self, order_id: str, symbol: str) -> dict:
        return self.client.cancel_order(order_id, symbol=symbol)

    @retry((requests.exceptions.ReadTimeout, 
            requests.exceptions.ProxyError, 
            requests.exceptions.ConnectionError,
            ccxt.errors.RequestTimeout), tries=3)
    def _safe_fetch_balance(self) -> dict:
        return self.client.fetch_balance()
    
    def cancel(self, order: Order) -> Order:
        symbol = self.get_symbol(order.ticker)

        self._safe_cancel_order(order.id_, symbol=symbol)
        self.update(order)
        
        return order
    
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

    # ------------------------------------- wrapper methods -------------------------------------
    def fetch_balance(self, balance_type: str = "total") -> dict:
        """Fetch current balance
        
        Args:
            balance_type (str): "total", "free", "used"
        
        Returns:
            dict
        """
        return self._safe_fetch_balance()[balance_type]

    @functools.lru_cache(maxsize=1)
    def _load_markets(self) -> dict:
        return self.client.load_markets()

    def load_markets(self, market_type: str | None = None) -> dict:
        """

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

    @functools.lru_cache(maxsize=128)
    def _fetch_tickers(self, symbols: tuple[str, ...], now: pd.Timestamp) -> dict:
        return self.client.fetch_tickers(symbols)

    def fetch_tickers(self, tickers: list[str]) -> dict:
        """
        
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
        symbols = [self.ticker2symbol[ticker] for ticker in tickers]
        if not symbols:
            return {}
        status = self._fetch_tickers(tuple(symbols), self.strategy.now)
        return {self.symbol2ticker[k]: v for k, v in status.items()}

    def fetch_positions(self, tickers: list[str]) -> dict[str, dict[str, Position]]:
        symbols = [self.ticker2symbol[ticker] for ticker in tickers]
        positions = self.client.fetch_positions(symbols)
        
        res = defaultdict(dict)
        for info in positions:
            ticker = self.symbol2ticker[info["symbol"]]
            res[ticker][info["side"]] = Position(
                ticker=ticker,
                side=info["side"],
                amount=info["contracts"],
                leverage=info["leverage"] or np.nan,
                entry_prc=info["entryPrice"] or np.nan,
                mark_prc=info["markPrice"] or np.nan,
                margin=info["collateral"] or 0.0,
                fee=abs(float(info["info"]["fee"] or 0.0)),
                id_=info["id"],
                created_at=pd.Timestamp(info["timestamp"], unit="ms"),
                updated_at=pd.Timestamp(info["lastUpdateTimestamp"], unit="ms"),
                contract_size=info["contractSize"],
                liquidation_prc_=info["liquidationPrice"] or np.nan,
                notional_=info["notional"] or np.nan
            )
        return res

    def set_leverage(self, ticker: str, side: str, leverage: PosFloat):
        self.client.set_leverage(leverage, self.get_symbol(ticker), params={"mgnMode": "isolated", "posSide": side})
