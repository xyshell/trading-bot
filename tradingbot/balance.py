from __future__ import annotations
import copy
from collections import UserDict

import numpy as np

from tradingbot.exchange import RealExchange, Exchange, FakeExchange
from tradingbot.transaction import Transaction


class Balance(UserDict):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __repr__(self):
        return f"Balance({self.data})"

    def __getitem__(self, key: str):
        return self.data.get(key, 0.0)

    def __setitem__(self, key: str, value: int | float):  # TODO: add position objct
        if isinstance(value, (int, float)) and value < 0:
            raise ValueError(f"balance cannot be negative, got {key}={value}")
        self.data[key] = value

    def reflect(self, exchange: Exchange, balance_type: str = "total") -> Balance:
        """Reflect balance from exchange
        
        Args:
            exchange (Exchange):
            balance_type (str): "total", "free" or "used"
        """
        if isinstance(exchange, FakeExchange):
            return self
        balance = copy.deepcopy(self)
        balance.data = exchange.fetch_balance(balance_type)
        return balance

    def evaluate(self, exchange: Exchange, currency: str) -> dict[str, float]:
        """Evaluate balance in one currency
        
        Args:
            exchange (Exchange): 
            currency (str): e.g. USDT

        Returns:
            dict[str, float]
        """
        tickers = [f"{currency}/{asset}" for asset in self.data.keys()]
        trivial_ticker = f"{currency}/{currency}"
        if trivial_ticker in tickers:
            tickers.remove(trivial_ticker)
        status = exchange.fetch_tickers(tickers)
        price = {k: v["last"] for k, v in status.items()}
        price[trivial_ticker] = 1.0
        evaluated = {asset: self.data[asset] * price[f"{currency}/{asset}"] for asset in self.data}
        return evaluated

    # def add_position(self, pos: Position):  # TODO: add future positions
    
    # def is_sufficient(self) -> bool:
    #     # TODO: for margin positions, check margin
    #     return all(pos.qty >= 0 for pos in self._positions.values() if isinstance(pos, SpotPosition))

    # -------------------------------  Trading API  -------------------------------
    def convert(self, size: float, size_type: str, frm: str, to: str, *, trader, method: str = "market", param: dict | None = None) -> None:
        """Convert <frm> asset to <to> asset using <method> with <param>, e.g.
        
        1. size in percentage:
        self.convert(1.0, "PCTG", "USDT", "BTC", trader=trader)  # convert [100] [percentage] of [USDT] to [BTC]
        
        2. size in quantity:
        self.convert(50, "QTY", "USDT", "BTC", trader=trader)  # convert [50] [USDT] to [BTC]
        
        3. split into 5 market orders, delay 60s between each order
        self.balance.convert(1.0, "USDT", "BTC", trader=trader, method="market", param={"n": 5, "delay": 60})

        4. place a limit order at 80_000, wait for 300s, if not filled, split into 5 market orders with 60s delay in between 
        self.convert(1.0, "USDT", "BTC", trader=trader, method="limit2market", param={"price": 80_000, "wait": 300, "n": 5, "delay": 60})

        Args:
            size (float): size of the conversion
            size_type (str): "QTY" for quantity or "PCTG" for percentage
            frm (str): from asset
            to (str): to asset
            trader (tradingbot.trader.Trader):
            method (str): "market" or "limit"
            param (dict | None, optional): parameters for the method. Defaults to None.

        Returns:
            None
        """
        # WIP
        param = param or {}

        frm_qty = self[frm] * size if size_type == "PCTG" else size

        # FakeExchange, assuming executed at close price, regarless of method
        ticker2close = trader.strategy.data.ticker2close
        if f"{frm}/{to}" in ticker2close:
            ticker = f"{frm}/{to}"
            divider = ticker2close[ticker]
        else:
            ticker = f"{to}/{frm}"
            divider = 1.0 / ticker2close[ticker]
        to_qty = frm_qty / divider
        tcost = to_qty * trader.exchange._commission
        to_qty -= tcost  # charge tcost in <to> asset, i.e. get less

        new_balance = copy.deepcopy(self)
        try:
            new_balance[frm] -= frm_qty
            new_balance[to] += to_qty
        except ValueError:
            raise ValueError(f"insufficient balance to convert {frm_qty} '{frm}' to {to_qty} '{to}', current balance: {self}")
            # TODO: consider adding param to use as much balance as possible
        else:
            self.data = new_balance.data
            trans = Transaction(frm, frm_qty, to, to_qty, frm, tcost, ticker, ticker2close[ticker],
                                timestamp=trader.strategy.now)
            trader.strategy.transaction_history.append(trans)

    def target(self, size: float, size_type: str, side: str, ticker: str, *, trader, leverage: int = 1, method: str = "market", param: dict | None = None) -> None:
        """Target <side> position of <ticker> using <method> with <param>, e.g.
        
        1. target [0] [percentage] of [short] position of contract [USDT/BTC:USDT]
        self.target(0.0, "PCTG", "SHORT", f"USDT/BTC:USDT", trader=trader)

        2. target [100] [percentage] of [long] position of contract [USDT/BTC:USDT], with leverage x[5]
        self.target(1.0, "PCTG", "LONG", f"USDT/BTC:USDT", trader=trader, leverage=5)
        
        3. target [0] [percentage] of [long] position of contract [USDT/BTC:USDT]
        self.target(0.0, "PCTG", "LONG", f"USDT/BTC:USDT", trader=trader)

        4. target [100] [percentage] of [short] position of contract [USDT/BTC:USDT], with leverage x[5]
        self.target(1.0, "PCTG", "SHORT", f"USDT/BTC:USDT", trader=trader, leverage=5)

        Args:
            size (float): size of the target
            size_type (str): "QTY" for quantity or "PCTG" for percentage
            side (str): "LONG" or "SHORT"
            ticker (str): ticker of the tradable asset
            
        Returns:
            None
        """
        param = param or {}
        raise NotImplementedError