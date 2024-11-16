import copy
from enum import Enum
from pathlib import Path
import typing
import logging

import numpy as np
from typing_extensions import Annotated
from pydantic import BaseModel, ConfigDict, Field, computed_field, AfterValidator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, TomlConfigSettingsSource
import pandas as pd

import tradingbot.util as util


def check_mode(v: str) -> str:
    assert v in {"backtest", "live"}, f"mode must be one of 'backtest' or 'live', got {v}"
    return v


def check_datetime(v: str) -> pd.Timestamp:
    return pd.Timestamp(v)


def check_timedelta(v: str) -> pd.Timedelta:
    return pd.Timedelta(v)


ModeType = Annotated[str, AfterValidator(check_mode)]
DatetimeType = Annotated[str | pd.Timestamp, AfterValidator(check_datetime)]
TimedeltaType = Annotated[str | pd.Timedelta, AfterValidator(check_timedelta)]


class Config(BaseSettings):
    class _GeneralConfig(BaseModel):
        db_url: str = Field(default=f"sqlite:///{Path(__file__).parent / 'tradingbot.db'}")
        http_proxy: str | None = Field(default=None)
        https_proxy: str | None = Field(default=None)
        dask_scheduler_url: str | None = Field(default=None)

    class _SourceConfig(BaseModel):
        model_config = ConfigDict(extra="allow")

        class _BinanceSourceConfig(BaseModel):
            api_key: str | None = Field(default=None)
            api_secret: str | None = Field(default=None)

        binance: _BinanceSourceConfig | None = Field(default=None)

    class _ExchangeConfig(BaseModel):
        model_config = ConfigDict(extra="allow")

        class _CCXTExchangeConfig(BaseModel):
            model_config = ConfigDict(extra="allow")

            name: str

        ccxt: _CCXTExchangeConfig | None = Field(default=None)

    class _NotificationConfig(BaseModel):
        model_config = ConfigDict(extra="allow")

        class _SlackConfig(BaseModel):
            bot_token: str
            channel: str

        slack: _SlackConfig | None = Field(default=None)

    class _LoggingConfig(BaseModel):
        version: int = 1
        disable_existing_loggers: bool = False

        formatters: dict[str, dict[str, typing.Any]]
        handlers: dict[str, dict[str, typing.Any]]
        loggers: dict[str, dict[str, typing.Any]]
        root: dict[str, typing.Any]

    general: _GeneralConfig
    source: _SourceConfig
    exchange: _ExchangeConfig
    notification: _NotificationConfig
    logging: _LoggingConfig

    model_config = SettingsConfigDict(
        toml_file=Path(__file__).parent / "config.toml", env_prefix="TB_", env_nested_delimiter="_", validate_assignment=True
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: typing.Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        
        search_path = [
            Path.cwd() / "config.toml",  # current directory
            Path.cwd().parent / "config.toml",  # parent directory
        ]
        toml_file = cls.model_config.get("toml_file")  # default
        for path in search_path:
            if path.exists():
                toml_file = path
                break

        print(f"Loading config.toml from '{toml_file}'")
        return (env_settings, dotenv_settings, TomlConfigSettingsSource(settings_cls, toml_file))


class Position(BaseModel):
    """Holding position"""

    ticker: str  # e.g. BTC, USDT
    qty: float  # quantity, with sign indicates long/short
    entry_prc: float = 0.0  # entry price, i.e. historical average cost price
    market_prc_: float = 1.0  # defaults to reporting currency unit

    @property
    def market_prc(self) -> float:
        return self.market_prc_

    @market_prc.setter
    def market_prc(self, value: float) -> None:
        self.market_prc_ = value

    @computed_field
    def pnl(self) -> float:  # profit and loss
        return self.qty * (self.market_prc - self.entry_prc)

    @computed_field
    def entry_val(self) -> float:  # entry value, i.e. historical cost
        return self.qty * self.entry_prc

    @computed_field
    def market_val(self) -> float:  # market value
        return self.qty * self.market_prc

    @staticmethod
    def get(positions: list[typing.Self], ticker: str) -> typing.Self:
        return next((p for p in positions if p.ticker == ticker), Position(ticker=ticker, qty=0))

    def clear(self) -> None:
        self.qty = 0
        self.entry_prc = 0.0


class MarginPosition(Position):

    leverage: int = -1
    margin: tuple[str, float] = ("", 0.0)
    last_market_prc_: float | None = Field(default=None, exclude=True, repr=False)

    @Position.market_prc.setter
    def market_prc(self, value: float) -> None:
        self.last_market_prc_ = value if self.last_market_prc_ is None else self.market_prc  # init or update last market price
        self.market_prc_ = value
        mark_to_market_pnl = (self.market_prc - self.last_market_prc_) * self.qty 
        self.margin = (self.margin[0], float(self.margin[1] + mark_to_market_pnl))  # mark to market 

    @computed_field
    def liq_prc(self) -> float:  # liquidation price
        sign = -1 if self.qty > 0 else 1
        return self.entry_prc * (1 + sign / (self.leverage if self.leverage > 0 else np.nan))

    def clear(self) -> None:
        super().clear()
        self.margin = (self.margin[0], 0.0)


class Account:

    @util.validate
    def __init__(self, position: list[Position]):
        self._position = {pos.ticker: pos for pos in position}

    def __repr__(self) -> str:
        wealth = {pos.ticker: f"{pos.qty:.4f}" for pos in self.position}
        return f"Account({wealth})"

    @classmethod
    def create(cls, wealth: dict[str, float]) -> typing.Self:
        return cls([Position(ticker=ticker, qty=qty) for ticker, qty in wealth.items()])

    @property
    def position(self) -> list[Position]:
        return [pos for pos in self._position.values() if pos.qty]

    def __contains__(self, ticker: str) -> bool:
        return ticker in self._position

    def __getitem__(self, ticker: str) -> Position:
        if ticker not in self._position:
            pos = Position(ticker=ticker, qty=0)
            self._position[ticker] = pos
        return self._position[ticker]

    def __setitem__(self, ticker: str, pos: Position) -> None:
        self._position[ticker] = pos

    def __iter__(self) -> typing.Iterator[Position]:
        return iter(self.position)

    def __add__(self, pos: Position) -> typing.Self:
        self = copy.deepcopy(self)
        pos = copy.deepcopy(pos)
        this = self[pos.ticker]
        new_qty = this.qty + pos.qty
        if this.qty * new_qty < 0:
            pos.qty += this.qty
            this.clear()
            return self + pos
        else:
            entry_prc = (pos.entry_prc * pos.qty + this.entry_prc * this.qty) / new_qty if new_qty else 0.0
            qty = this.qty + pos.qty
            this.qty = qty
            this.entry_prc = entry_prc
        return self

    def __sub__(self, pos: Position) -> typing.Self:
        pos = copy.deepcopy(pos)
        pos.qty = -pos.qty
        return self + pos

    def all_sufficient(self) -> bool:
        return all(pos.qty >= 0 for pos in self._position.values())

class MarginAccount(Account):

    @classmethod
    def create(cls, wealth: dict[str, float]) -> typing.Self:
        return cls([Position(ticker=ticker, qty=qty) for ticker, qty in wealth.items()])

    def __repr__(self):
        wealth = {pos.ticker: pos.qty for pos in self.position}
        return f"MarginAccount({wealth})"

    @property
    def position(self) -> list[Position]:
        return [pos for pos in self._position.values() if pos.qty or isinstance(pos, MarginPosition)]
    
    def __getitem__(self, ticker: str) -> MarginPosition:
        if ticker not in self._position:
            pos = MarginPosition(ticker=ticker, qty=0)
            self._position[ticker] = pos
        return self._position[ticker]

    def __add__(self, pos: Position | MarginPosition) -> typing.Self:
        self = super().__add__(pos)
        pos_ = self[pos.ticker]
        if isinstance(pos_, MarginPosition):
            pos_.margin = (pos.margin[0], pos_.margin[1] + pos.margin[1])
            if pos_.leverage == -1:  # uninitialized leverage 
                pos_.leverage = pos.leverage
            elif pos_.leverage != pos.leverage:
                raise NotImplementedError
        return self

    def __sub__(self, pos: Position | MarginPosition) -> typing.Self:
        pos = copy.deepcopy(pos)
        pos.qty = -pos.qty
        if isinstance(pos, MarginPosition):
            pos.margin = (pos.margin[0], -pos.margin[1])
        return self + pos

    def all_sufficient(self) -> bool:
        result = True
        for pos in self._position.values():
            if isinstance(pos, MarginPosition):
                result &= pos.margin[1] >= 0
            else:
                result &= pos.qty >= 0
        return result

class Transaction(BaseModel):
    """conversion from one asset to another"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    ticker: str
    prc: float
    from_: tuple[str, float]  # (from_ticker, from_qty)
    to_: tuple[str, float]  # (to_ticker, to_qty)
    tcost: tuple[str, float]  # transaction cost, e.g. ("USDT", 10)
    timestamp: pd.Timestamp

    def _validate(self) -> None:
        assert (
            self.from_[0] in self.ticker and self.to_[0] in self.ticker
        ), f"Invalid transaction: {self.from_[0]}, {self.to_[0]} not in {self.ticker}"

    @model_validator(mode="after")
    def reconcile(self) -> typing.Self:
        self._validate()
        if self.tcost[0] == self.from_[0]:
            assert np.isclose(
                self.from_[1] - self.tcost[1], util.convert(self.to_, self.ticker, self.prc)[1]
            ), f"Failed to reconcile {self}"
        elif self.tcost[0] == self.to_[0]:
            assert np.isclose(
                self.tcost[1] + self.to_[1], util.convert(self.from_, self.ticker, self.prc)[1]
            ), f"Failed to reconcile {self}"
        return self

    def split(self) -> tuple[Position, Position, Position]:
        """Split a transaction into from position, to position and tcost position"""
        quote_ticker = util.get_quote_ticker(self.ticker)
        from_prc = self.prc if self.from_[0] != quote_ticker else 0.0
        to_prc = self.prc if self.to_[0] != quote_ticker else 0.0
        return (
            Position(ticker=self.from_[0], qty=self.from_[1], entry_prc=from_prc),  # withdraw
            Position(ticker=self.to_[0], qty=self.to_[1], entry_prc=to_prc),  # deposit
            Position(ticker=self.tcost[0], qty=self.tcost[1]),  # vanish
        )

    def __bool__(self) -> bool:
        return not (self.from_[1] == self.to_[1] == 0)


class _MarginTransaction(Transaction):
    leverage: int

    def _validate(self) -> None:
        super()._validate()
        quote_ticker = util.get_quote_ticker(self.ticker)
        assert self.tcost[0] == quote_ticker, f"Tcost should be charged in '{quote_ticker}'"


class OpenTransaction(_MarginTransaction):
    """conversion from normal position to margin position"""
    leverage: int

    @model_validator(mode="after")
    def reconcile(self) -> typing.Self:
        self._validate()
        lhs = (self.from_[1] - self.tcost[1])
        rhs = abs(util.convert(self.to_, self.ticker, self.prc)[1] / self.leverage)
        assert np.isclose(lhs, rhs), f"Failed to reconcile {self}"
        return self

    def split(self) -> tuple[Position, MarginPosition, Position]:
        quote_ticker = util.get_quote_ticker(self.ticker)
        return (
            Position(ticker=self.from_[0], qty=self.from_[1], entry_prc=0.0),  # withdraw from normal position
            MarginPosition(
                ticker=self.to_[0], 
                qty=self.to_[1], 
                entry_prc=self.prc, 
                leverage=self.leverage, 
                margin=(quote_ticker, self.from_[1] - self.tcost[1])
            ),  # deposit to margin position
            Position(ticker=self.tcost[0], qty=self.tcost[1]),  # vanish as tcost
        )
    

class CloseTransaction(_MarginTransaction):
    """conversion from normal position to margin position"""
    leverage: int

    @model_validator(mode="after")
    def reconcile(self) -> typing.Self:
        self._validate()
        return self

    def split(self) -> tuple[MarginPosition, Position, Position]:
        quote_ticker = util.get_quote_ticker(self.ticker)
        return (
            MarginPosition(
                ticker=self.from_[0], 
                qty=self.from_[1], 
                entry_prc=self.prc, 
                leverage=self.leverage,
                margin=(quote_ticker, self.to_[1] + self.tcost[1]),
            ),  # withdraw from margin position
            Position(ticker=self.to_[0], qty=self.to_[1], entry_prc=0.0),  # deposit to normal position
            Position(ticker=self.tcost[0], qty=self.tcost[1]),  # vanish as tcost
        )


class Order(BaseModel):
    class Action(Enum):
        # spot
        BUY = "BUY"
        SELL = "SELL"
        # future
        OPEN_LONG = "OPEN_LONG"
        OPEN_SHORT = "OPEN_SHORT"
        CLOSE_LONG = "CLOSE_LONG"
        CLOSE_SHORT = "CLOSE_SHORT"

    class Type(Enum):
        LIMIT = "LIMIT"
        MARKET = "MARKET"

    class SizeType(Enum):
        BASE = "BASE"  # units in base currency. e.g. BTC
        QUOTE = "QUOTE"  # units in quote (i.e. price) currency. e.g. USDT
        PCTG = "PCTG"  # percentage of available capital

    class Status(Enum):
        NEW = "NEW"
        PENDING = "PENDING"
        PARTIAL_FILLED = "PARTIAL_FILLED"
        FILLED = "FILLED"
        CANCELED = "CANCELED"
        EXPIRED = "EXPIRED"
        REJECTED = "REJECTED"

    action: Action
    ticker: str
    size_type: SizeType
    size: float
    type: Type
    param: dict = Field(default_factory=dict)
    status: Status = Status.NEW
    id_: str | None = Field(default=None)

    model_config = ConfigDict(validate_assignment=True)

    def __str__(self):
        return f"Order(id={self.id_}, {self.action.name}, {self.ticker}, {self.size_type.name}, {self.size:.4f}, {self.type.name}, {self.param}, {self.status.name})"

    def model_post_init(self, __context):
        logging.getLogger(self.__class__.__qualname__).debug(f"Order(ID={self.id_}) Created: {self}")

    @property
    def from_ticker(self) -> str:
        if self.action is Order.Action.BUY or self.action in {Order.Action.OPEN_LONG, Order.Action.OPEN_SHORT}:
            return util.get_quote_ticker(self.ticker)
        elif self.action is Order.Action.SELL or self.action in {Order.Action.CLOSE_LONG, Order.Action.CLOSE_SHORT}:
            return util.get_base_ticker(self.ticker)
        raise NotImplementedError

    @property
    def to_ticker(self) -> str:
        if self.action is Order.Action.BUY or self.action in {Order.Action.OPEN_LONG, Order.Action.OPEN_SHORT}:
            return util.get_base_ticker(self.ticker)
        elif self.action is Order.Action.SELL or self.action in {Order.Action.CLOSE_LONG, Order.Action.CLOSE_SHORT}:
            return util.get_quote_ticker(self.ticker)
        raise NotImplementedError

    def cancel(self, exchange, now: pd.Timestamp = pd.NaT) -> typing.Self:
        self.status = Order.Status.CANCELED
        self = exchange.execute(now=now, order=self)
        exchange.update_orders(now=now, orders=[self])
        return self
