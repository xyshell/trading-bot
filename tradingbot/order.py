from enum import Enum
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
        MARKET = "MARKET"
        LIMIT = "LIMIT"  # {"price": 12345.6, "good_till": pd.Timedelta.max}

    class SizeType(Enum):
        BASE = "BASE"  # units in base currency. e.g. BTC
        QUOTE = "QUOTE"  # units in quote (i.e. price) currency. e.g. USDT
        PCTG = "PCTG"  # percentage of available capital

    class Status(Enum):
        NEW = "NEW"  # order created but not submitted to exchange
        PENDING = "PENDING"  # order submitted but not filled
        PARTIAL_FILLED = "PARTIAL_FILLED"  # order partially filled
        FILLED = "FILLED"  # order fully filled
        CANCELED = "CANCELED"  # order canceled
        EXPIRED = "EXPIRED"  # limit order expired due to good_till
        REJECTED = "REJECTED"  # order rejected by validation or exchange

    # input fields
    action: Action
    ticker: str
    size_type: SizeType
    size: float
    type: Type
    param: dict = Field(default_factory=dict)
    status: Status = Status.NEW
    id_: str | None = Field(default=None)

    # managed fields
    created_at: pd.Timestamp | None = Field(default=None)
    updated_at: pd.Timestamp | None = Field(default=None)
    filled_at: pd.Timestamp | None = Field(default=None)

    model_config = ConfigDict(validate_assignment=True, arbitrary_types_allowed=True)

    def __str__(self):
        return f"Order({self.action.name}, {self.ticker}, {self.size_type.name}, {self.size:.4f}, {self.type.name}, {self.param}, {self.status.name})"

    def __repr__(self):
        return f"Order({self.model_dump()})"
    
    def model_post_init(self, __context):
        if self.type is Order.Type.LIMIT:
            assert self.param["price"] is not None
            self.param["good_till"] = pd.Timedelta(self.param.get("good_till", pd.Timedelta.max))  # default to GTC

    @property
    def from_ticker(self) -> str:
        """which ticker to consume"""
        if self.action is Order.Action.BUY or self.action in {Order.Action.OPEN_LONG, Order.Action.OPEN_SHORT}:
            return util.get_quote_ticker(self.ticker)
        elif self.action is Order.Action.SELL or self.action in {Order.Action.CLOSE_LONG, Order.Action.CLOSE_SHORT}:
            return util.get_base_ticker(self.ticker)
        raise NotImplementedError

    @property
    def to_ticker(self) -> str:
        """which ticker to produce"""
        if self.action is Order.Action.BUY or self.action in {Order.Action.OPEN_LONG, Order.Action.OPEN_SHORT}:
            return util.get_base_ticker(self.ticker)
        elif self.action is Order.Action.SELL or self.action in {Order.Action.CLOSE_LONG, Order.Action.CLOSE_SHORT}:
            return util.get_quote_ticker(self.ticker)
        raise NotImplementedError

    @property
    def market(self) -> str:
        """which market is this order for
        
        Returns:
            str: "spot" or "future"
        """
        return "spot" if self.action in {Order.Action.BUY, Order.Action.SELL} else "future"

    # def cancel(self, exchange, now: pd.Timestamp = pd.NaT) -> typing.Self:  TODO: not here
    #     self.status = Order.Status.CANCELED
    #     self = exchange.execute(now=now, order=self, check=False)
    #     exchange.update_order(now=now, order=self)
    #     return self
