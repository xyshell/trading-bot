from __future__ import annotations
import copy
from enum import Enum
from typing import TYPE_CHECKING, Iterable
from collections import UserDict, defaultdict


import tradingbot.util as util
from tradingbot.util import NonNegFloat, PosFloat
from tradingbot.position import Position


if TYPE_CHECKING:
    from tradingbot.exchange import Exchange


class _SizeType(Enum):
    QTY = "QTY"
    PCTG = "PCTG"


class _SideType(Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class Balance(UserDict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __repr__(self):
        return f"Balance({self.data})"

    def __getitem__(self, key: str) -> float | dict[str, Position]:
        return self.data.get(key, 0.0 if ":" not in key else {})

    def __setitem__(self, key: str, value: int | float):
        if isinstance(value, (int, float)) and value < 0:
            raise ValueError(f"balance cannot be negative, got {key}={value}")
        self.data[key] = value

    @property
    def positions(self) -> dict[str, Position]:
        return {k: v for k, v in self.data.items() if ":" in k}

    def add_position(self, pos: Position) -> None:
        """Add or update an existing position using a Position object."""
        ticker = pos.ticker
        side = pos.side.value

        if ticker not in self.data or not isinstance(self.data[ticker], dict):
            self.data[ticker] = {}

        existing = self.data[ticker].get(side)
        if existing is None:
            self.data[ticker][side] = pos
        else:
            combined = existing + pos
            if combined.amount == 0.0:
                self.data[ticker][side].clear()
            else:
                self.data[ticker][side] = combined

    def close_position(self, pos: Position) -> None:
        """Close or reduce an existing position using an opposing Position object."""
        ticker = pos.ticker
        side = pos.side.value

        pos_pair = self.data.get(ticker)
        if not pos_pair or side not in pos_pair:
            raise KeyError(f"No open {side} position to close for {ticker}")

        existing = pos_pair[side]
        if abs(pos.amount) > abs(existing.amount):
            raise ValueError(f"Cannot close more than existing {side} amount: {abs(pos.amount)} > {abs(existing.amount)}")

        self.add_position(pos)

    def reflect(self, exchange: Exchange, balance_type: str = "total", subset: Iterable[str] | None = None) -> Balance:
        """Reflect balance from exchange

        Args:
            exchange (Exchange):
            balance_type (str): "total", "free" or "used"
            subset (Iterable[str] | None, optional): list of assets to filter. Defaults to None.

        Returns:
            Balance
        """
        from tradingbot.exchange import FakeExchange

        if isinstance(exchange, FakeExchange):
            return self

        balance = copy.deepcopy(self)
        bal = exchange.fetch_balance(balance_type)
        pos = exchange.fetch_positions([])
        if subset:
            data = {k: v for k, v in (bal | pos).items() if k in subset}
        balance.data = data
        return balance

    def evaluate(self, exchange: Exchange, currency: str) -> dict[str, float]:
        """Evaluate balance in one currency

        Args:
            exchange (Exchange):
            currency (str): e.g. USDT

        Returns:
            dict[str, float]
        """
        markets = exchange.load_markets()
        spot_markets = {k: v for k, v in markets.items() if v["type"] == "spot"}
        derivative_markets = {k: v for k, v in markets.items() if v["type"] in {"future", "swap", "option"}}
        spot_tickers = []
        for asset in self.data.keys():
            if f"{currency}/{asset}" in spot_markets:
                spot_tickers.append(f"{currency}/{asset}")
            elif f"{asset}/{currency}" in spot_markets:
                spot_tickers.append(f"{asset}/{currency}")
        derivative_tickers = [asset for asset in self.data.keys() if asset in derivative_markets]
        tickers = spot_tickers + derivative_tickers
        trivial_ticker = f"{currency}/{currency}"
        if trivial_ticker in tickers:
            tickers.remove(trivial_ticker)
        status = exchange.fetch_tickers(tickers)
        price = {k: v["last"] for k, v in status.items()}
        price[trivial_ticker] = 1.0

        evaluated = defaultdict(float)
        for asset in self.data:
            if asset in derivative_markets:
                # for positions, use the margin value + pnl
                eval_asset = util.get_margin_asset(asset)
                eval_value = 0.0
                if long_pos := self.data[asset].get("long"):
                    long_margin = long_pos.margin if long_pos.amount else 0.0
                    long_pnl = long_pos.pnl if long_pos.amount else 0.0
                    eval_value += long_margin + long_pnl + long_pos.fee
                if short_pos := self.data[asset].get("short"):
                    short_margin = short_pos.margin if short_pos.amount else 0.0
                    short_pnl = short_pos.pnl if short_pos.amount else 0.0
                    eval_value += short_margin + short_pnl + short_pos.fee
            else:
                eval_asset = asset
                eval_value = self.data[asset]

            prc = price.get(f"{currency}/{eval_asset}")
            if prc is None:
                prc = 1 / price[f"{eval_asset}/{currency}"]
            evaluated[asset] = eval_value * prc
        return evaluated

    # -------------------------------  Trading API  -------------------------------
    @util.validate
    def convert(
        self, size: NonNegFloat, size_type: _SizeType, frm: str, to: str, *, trader, method: str = "market", param: dict | None = None
    ) -> None:
        """Convert <frm> asset to <to> asset using <method> with <param>, e.g.

        1. size in percentage:
        self.convert(1.0, "PCTG", "USDT", "BTC", trader=trader)  # convert [100] [percentage] of [USDT] to [BTC]

        2. size in quantity:
        self.convert(50, "QTY", "USDT", "BTC", trader=trader)  # convert [50] [USDT] to [BTC]

        3. split into 5 market orders, delay 60s between each order
        self.convert(1.0, "PCTG", "USDT", "BTC", trader=trader, param={"n": 5, "delay": 60})

        4. place a limit order at 80_000
        self.convert(1.0, "PCTG", "USDT", "BTC", trader=trader, method="limit", param={"price": 80_000})

        5. place a limit order at 80_000, wait for 300s, if not filled, scale the order amount to 99% and split into 5 market orders with 60s delay in between
        self.convert(1.0, "PCTG", "USDT", "BTC", trader=trader, method="limit2market", param={"price": 80_000, "wait": 300, "n": 5, "delay": 60, "scaler": 0.99})

        TODO: 6. place a limit order at 80_000, wait for 300s, if not filled, cancel it
        self.convert(1.0, "PCTG", "USDT", "BTC", trader=trader, method="limit2cancel", param={"price": 80_000, "wait": 300})

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
        param = param or {}
        frm_qty = self[frm] * size if size_type is _SizeType.PCTG else size

        trader.convert(method, frm_qty, frm, to, param)

    @util.validate
    def target(
        self,
        size: NonNegFloat,
        size_type: _SizeType,
        side: _SideType,
        ticker: str,
        *,
        trader,
        leverage: PosFloat | None = None,
        method: str = "market",
        param: dict | None = None,
    ) -> None:
        """Target <side> position of <ticker> using <method> with <param>, e.g.

        1. target [0] [percentage] of [short] position of contract [USDT/BTC:USDT]
        self.target(0.0, "PCTG", "SHORT", f"USDT/BTC:USDT", trader=trader)

        2. target [100] [percentage] of [long] position of contract [USDT/BTC:USDT], with leverage x[5]
        self.target(1.0, "PCTG", "LONG", f"USDT/BTC:USDT", trader=trader, leverage=5)

        Args:
            size (float): size of the target
            size_type (str): "QTY" for quantity or "PCTG" for percentage
            side (str): "LONG" or "SHORT"
            ticker (str): ticker of the tradable asset

        Returns:
            None
        """
        param = param or {}
        side_str = side.value.lower()
        margin_asset = util.get_margin_asset(ticker)
        base_asset = util.get_base_asset(ticker)
        if size_type == _SizeType.QTY or size == 0.0:
            qty = size
        else:  # size_type == _SizeType.PCTG
            pos = self[ticker].get(side_str)
            if pos is not None and pos.amount > 0:
                pos_value = pos.margin + pos.pnl + pos.fee
            else:
                pos_value = 0.0
            margin_value = self[margin_asset] + pos_value
            raw_qty = Balance({margin_asset: margin_value}).evaluate(trader.exchange, base_asset)[margin_asset]
            markets = trader.exchange.load_markets()
            qty = raw_qty * size * leverage / markets[ticker]["contractSize"]

        trader.target(method, qty, side_str, ticker, leverage=leverage, param=param)
