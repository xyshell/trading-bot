import copy
import functools

import pandas as pd

import tradingbot as tb
import tradingbot.util as util
from tradingbot.exchange.core import Exchange
from tradingbot.model import Order, Transaction


class CCXTExchange(Exchange):
    def __init__(self, name: str = None, **kwargs):
        config = tb.config
        self._name = name or config.exchange.ccxt.name
        self._param = {**tb.config.exchange.ccxt.model_dump(exclude="name"), **kwargs}

    @functools.cached_property
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

    def get_price(self, ticker: str) -> float:
        return self.client.fetch_ticker(self.get_symbol(ticker))["last"]

    def update_orders(self, now: pd.Timestamp, orders: list[Order]):
        import ccxt

        for order in orders:
            if order.status in {Order.Status.CANCELED, Order.Status.REJECTED}:
                self.strategy.order_history[now] = order
                if order in self.strategy.pending_order:
                    self.strategy.pending_order.remove(order)
            if order.id_ is None:
                continue
            try:
                status = self.client.fetch_order_status(str(order.id_), symbol=self.get_symbol(order.ticker))
            except ccxt.errors.OrderNotFound:
                continue
            match status:
                case "open":
                    self.strategy.logger.debug(f"Order(id={order.id_}) pending: {order}")
                    order.status = Order.Status.PENDING
                    if order not in self.strategy.pending_order:
                        self.strategy.pending_order.append(order)
                case "closed":
                    self.strategy.logger.info(f"Order(id={order.id_}) filled: {order}")
                    order_info = self.client.fetch_order(str(order.id_), symbol=self.get_symbol(order.ticker))
                    order.status = Order.Status.FILLED
                    from_ticker, to_ticker = order.from_ticker, order.to_ticker
                    trans = Transaction(
                        ticker=order.ticker,
                        prc=order.param["price"],
                        from_=(from_ticker, order_info["cost"]),
                        to_=(to_ticker, order_info["amount"] - order_info["fee"]["cost"]),
                        tcost=(order_info["fee"]["currency"], order_info["fee"]["cost"]),
                        timestamp=pd.Timestamp(order_info["datetime"]),
                    )
                    from_pos, to_pos, _ = trans.split()
                    account = copy.deepcopy(self.strategy.account)
                    account += to_pos
                    account -= from_pos
                    self.account = account
                    self.strategy.transaction_history.append(trans)
                    self.strategy.order_history[pd.Timestamp(order_info["datetime"])] = order
                    if order in self.strategy.pending_order:
                        self.strategy.pending_order.remove(order)
                case "canceled":
                    self.strategy.logger.info(f"Order(id={order.id_}) canceled: {order}")
                    order.status = Order.Status.CANCELED
                    self.strategy.order_history[now] = order
                    if order in self.strategy.pending_order:
                        self.strategy.pending_order.remove(order)

    def execute(self, now: pd.Timestamp, order: Order) -> Order:
        """
        Args:
            now (pd.Timestamp):
            order (Order):

        Returns:
            Order
        """
        import ccxt

        assert order.status in {Order.Status.NEW, Order.Status.PENDING, Order.Status.CANCELED}, f"Invalid order status: {order.status}"
        if order.type not in {Order.Type.LIMIT, Order.Type.MARKET}:
            raise NotImplementedError(f"Order type {order.type} is not supported yet.")

        if order.status is Order.Status.PENDING:
            return order
        elif order.status is Order.Status.CANCELED:
            try:
                self.client.cancel_order(str(order.id_), symbol=self.get_symbol(order.ticker))
            except ccxt.errors.OrderNotFound as e:
                self.strategy.logger.info(f"Order(id={order.id_}) Cancel failed, due to {e!r}. Do nothing.")
            return order

        # order.status is Order.Status.NEW
        quote_ticker, base_ticker = util.get_quote_ticker(order.ticker), util.get_base_ticker(order.ticker)

        # post order
        symbol = self.get_symbol(order.ticker)
        type_ = "limit" if order.type is Order.Type.LIMIT else "market"
        side = "buy" if order.action is Order.Action.BUY else "sell"
        match order.size_type:
            case Order.SizeType.PCTG if side == "buy":  # buy BTC, cost USDT
                price = order.param["price"] if type_ == "limit" else self.get_price(order.ticker)
                amount = self.strategy.account[quote_ticker].qty * order.size / price
            case Order.SizeType.PCTG if side == "sell":  # sell BTC, cost BTC
                amount = self.strategy.account[base_ticker].qty * order.size
            case Order.SizeType.QUOTE if type_ == "limit":
                amount = order.size / order.param["price"]
            case Order.SizeType.QUOTE if type_ == "market":
                amount = order.size / self.get_price(order.ticker)
            case Order.SizeType.BASE:
                amount = order.size
        try:
            price = order.param["price"] if type_ == "limit" else None
            self.strategy.logger.debug(f"Calling client.create_order({symbol}, {type_}, {side}, {amount}, {price})")
            order_resp = self.client.create_order(symbol=symbol, type=type_, side=side, amount=amount, price=price)
        except ccxt.errors.InsufficientFunds as e:
            self.strategy.logger.warning(f"Order rejected: {order}, due to InsufficientFunds {e!r}")
            order.status = Order.Status.REJECTED
            return order
        except ccxt.errors.InvalidOrder as e:
            self.strategy.logger.error(f"Order failed: {order}, due to InvalidOrder {e!r}")
            order.status = Order.Status.REJECTED
            return order
        except Exception as e:
            self.strategy.logger.error(f"Order failed: {order}, due to {e!r}")
            order.status = Order.Status.REJECTED
            return order

        order.id_ = order_resp["id"]
        order.status = Order.Status.PENDING
        self.strategy.logger.info(f"Order(id={order.id_}) posted: {order}")
        return order
