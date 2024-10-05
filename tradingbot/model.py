from enum import Enum
from pathlib import Path
from typing import Self, Sequence, Type
import logging

import numpy as np
from typing_extensions import Annotated
from pydantic import BaseModel, ConfigDict, Field, computed_field, AfterValidator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, TomlConfigSettingsSource
import pandas as pd

import tradingbot.util as util


def check_mode(v: str) -> str:
    assert v in {"backtest", "paper", "live"}, f"mode must be one of 'backtest', 'paper' or 'live', got {v}"
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

    class _SourceConfig(BaseModel):
        model_config = ConfigDict(extra="allow")

        class _BinanceSourceConfig(BaseModel):
            api_key: str | None = Field(default=None)
            api_secret: str | None = Field(default=None)

        binance: _BinanceSourceConfig | None = Field(default=None)

    class _ExchangeConfig(BaseModel):
        model_config = ConfigDict(extra="allow")

        class _CCXTExchangeConfig(BaseModel):
            name: str
            api_key: str | None = Field(default=None)
            secret_key: str | None = Field(default=None)

        ccxt: _CCXTExchangeConfig | None = Field(default=None)

    class _LoggingConfig(BaseModel):
        version: int = 1
        disable_existing_loggers: bool = False

        formatters: dict[str, dict[str, str]]
        handlers: dict[str, dict[str, str]]
        loggers: dict[str, dict[str, str | Sequence[str] | bool]]
        root: dict[str, str | Sequence[str]]

    general: _GeneralConfig
    source: _SourceConfig
    exchange: _ExchangeConfig
    logging: _LoggingConfig

    model_config = SettingsConfigDict(
        toml_file=Path(__file__).parent / "config.toml", env_prefix="TB_", env_nested_delimiter="_", validate_assignment=True
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        if toml_file := cls.model_config.get("toml_file"):
            print(f"Loading config.toml from '{toml_file}'")
        return (env_settings, dotenv_settings, TomlConfigSettingsSource(settings_cls))


class Position(BaseModel):
    """Holding position and its state"""

    ticker: str  # e.g. BTC, USDT
    qty: float  # quantity, with sign indicates long/short
    entry_prc: float = 0.0  # entry price, i.e. historical average cost price
    market_prc: float = np.nan  # market price

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
    def get(positions: list[Self], ticker: str) -> Self:
        return next((p for p in positions if p.ticker == ticker), Position(ticker=ticker, qty=0))

    def clear(self) -> None:
        self.qty = 0
        self.entry_prc = 0.0


class Account:
    def __init__(self, position: list[Position]):
        self._position = {pos.ticker: pos for pos in position}

    def __repr__(self) -> str:
        wealth = {pos.ticker: pos.qty for pos in self.position}
        return f"Account({wealth})"

    @classmethod
    def create(cls, wealth: dict[str, float]) -> Self:
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

    def __add__(self, pos: Position) -> Self:
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

    def __sub__(self, pos: Position) -> Self:
        pos.qty = -pos.qty
        return self + pos

    def all_long(self) -> bool:
        return all(pos.qty >= 0 for pos in self._position.values())


class Transaction(BaseModel):
    """conversion from one asset to another"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ticker: str
    prc: float
    from_: tuple[str, float]  # (from_ticker, from_qty)
    to_: tuple[str, float]  # (to_ticker, to_qty)
    tcost: tuple[str, float]  # transaction cost, e.g. ("USDT", 10)
    timestamp: pd.Timestamp

    @model_validator(mode="after")
    def reconcile(self) -> Self:
        assert (
            self.from_[0] in self.ticker and self.to_[0] in self.ticker
        ), f"Invalid transaction: {self.from_[0]}, {self.to_[0]} not in {self.ticker}"
        if self.tcost[0] == self.from_[0]:
            assert np.isclose(self.from_[1] - self.tcost[1], util.convert(self.to_, self.ticker, self.prc)[1])
        elif self.tcost[0] == self.to_[0]:
            assert np.isclose(self.tcost[1] + self.to_[1], util.convert(self.from_, self.ticker, self.prc)[1])
        return self

    def split(self) -> tuple[Position, Position]:
        """Split a transaction into from position, to position and tcost position"""
        quote_ticker = util.get_quote_ticker(self.ticker)
        from_prc = self.prc if self.from_[0] != quote_ticker else 0.0
        to_prc = self.prc if self.to_[0] != quote_ticker else 0.0
        return (
            Position(ticker=self.from_[0], qty=self.from_[1], entry_prc=from_prc),
            Position(ticker=self.to_[0], qty=self.to_[1], entry_prc=to_prc),
            Position(ticker=self.tcost[0], qty=self.tcost[1]),
        )

    def __bool__(self) -> bool:
        return not (self.from_[1] == self.to_[1] == 0)


class Order(BaseModel):
    class Action(Enum):
        BUY = "BUY"
        SELL = "SELL"

    class Type(Enum):
        LIMIT = "LIMIT"
        MARKET = "MARKET"

    class SizeType(Enum):
        BASE = "BASE"  # units in base currency. e.g. BTC
        QUOTE = "QUOTE"  # units in quote (i.e. price) currency. e.g. USDT
        PCTG = "PCTG"  # percentage of available capital

    class Status(Enum):
        NEW = "NEW"
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

    def model_post_init(self, __context):
        logging.getLogger(self.__class__.__qualname__).debug(f"Order(ID={id(self)}) Created: {self}")

    def id(self) -> int:
        return id(self)

    @property
    def from_ticker(self) -> str:
        if self.action is Order.Action.BUY:
            return util.get_quote_ticker(self.ticker)
        elif self.action is Order.Action.SELL:
            return util.get_base_ticker(self.ticker)

    @property
    def to_ticker(self) -> str:
        if self.action is Order.Action.BUY:
            return util.get_base_ticker(self.ticker)
        elif self.action is Order.Action.SELL:
            return util.get_quote_ticker(self.ticker)
