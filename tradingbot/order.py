from enum import Enum

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
import pandas as pd

import tradingbot.util as util


class Order(BaseModel):
    class Action(Enum):
        # spot
        BUY = "buy"
        SELL = "sell"
        # future
        OPEN_LONG = "open_long"
        OPEN_SHORT = "open_short"
        CLOSE_LONG = "close_long"
        CLOSE_SHORT = "close_short"

    class Type(Enum):
        MARKET = "market"
        LIMIT = "limit"

    class Status(Enum):
        NEW = "new"  # order created but not submitted to exchange yet
        PENDING = "pending"  # order submitted but not filled
        PARTIAL_FILLED = "partial_filled"  # order partially filled
        FILLED = "filled"  # order fully filled
        CANCELED = "canceled"  # order canceled
        REJECTED = "rejected"  # order rejected by exchange

    # input fields
    action: Action
    ticker: str
    amount: float
    type: Type
    param: dict = Field(default_factory=dict)
    status: Status = Status.NEW

    # managed fields
    id_: str | None = Field(default=None)
    created_at: pd.Timestamp  # | None = Field(default=None)
    updated_at: pd.Timestamp  # | None = Field(default=None)
    filled_at: pd.Timestamp | None = Field(default=None)
    filled_amount: float = np.nan
    remain_amount: float = np.nan
    exec_prc: float = np.nan
    msg: str = ""

    model_config = ConfigDict(validate_assignment=True, arbitrary_types_allowed=True)

    def __str__(self):
        return f"Order({self.action.name}, {self.ticker}, {self.amount:.4f}, {self.type.name}, {self.param}, {self.status.name})"

    def __repr__(self):
        return f"Order({self.model_dump()})"

    def model_post_init(self, __context):
        if self.type is Order.Type.LIMIT:
            assert self.param.get("price") is not None, "LIMIT order requires price parameter"

    @property
    def frm_asset(self) -> str:
        """which asset to consume"""
        if self.action is Order.Action.BUY or self.action in {Order.Action.OPEN_LONG, Order.Action.OPEN_SHORT}:
            return util.get_quote_asset(self.ticker)
        elif self.action is Order.Action.SELL or self.action in {Order.Action.CLOSE_LONG, Order.Action.CLOSE_SHORT}:
            return util.get_base_asset(self.ticker)
        raise NotImplementedError

    @property
    def to_asset(self) -> str:
        """which asset to produce"""
        if self.action is Order.Action.BUY or self.action in {Order.Action.OPEN_LONG, Order.Action.OPEN_SHORT}:
            return util.get_base_asset(self.ticker)
        elif self.action is Order.Action.SELL or self.action in {Order.Action.CLOSE_LONG, Order.Action.CLOSE_SHORT}:
            return util.get_quote_asset(self.ticker)
        raise NotImplementedError
