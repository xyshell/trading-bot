from enum import Enum
import typing
import logging

from pydantic import BaseModel, ConfigDict, Field
import pandas as pd

import tradingbot.util as util


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
        # basic
        MARKET = "MARKET"
        LIMIT = "LIMIT"  # {"price": 12345.6}
        # algo
        TrailingLimit = "TrailingLimit" # {"interval": "1m", offset": 0.9995}

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
        if self.type is Order.Type.LIMIT:
            assert self.param["price"] is not None
        if self.type is Order.Type.TrailingLimit:
            assert self.param["interval"] is not None
            assert self.param["offset"] is not None

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
        exchange.update_order(now=now, order=self)
        return self
