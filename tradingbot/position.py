from __future__ import annotations
from enum import Enum

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, computed_field

import tradingbot.util as util


class Position(BaseModel):
    class Side(Enum):
        LONG = "long"
        SHORT = "short"

    # input fields
    ticker: str
    side: Side
    amount: float
    leverage: float = Field(default=np.nan)
    entry_prc: float = Field(default=np.nan)
    mark_prc: float = Field(default=np.nan)
    margin: float = Field(default=0.0, ge=0.0)  # i.e. collateral
    fee: float = Field(default=0.0, ge=0.0)

    # managed fields
    id_: str | None = Field(default=None)
    created_at: pd.Timestamp
    updated_at: pd.Timestamp
    contract_size: float = np.nan
    liquidation_prc_: float = Field(default=np.nan, exclude=True, repr=False)
    notional_: float = Field(default=np.nan, exclude=True, repr=False)

    model_config = ConfigDict(validate_assignment=True, arbitrary_types_allowed=True)

    @computed_field
    @property
    def liquidation_prc(self) -> float:
        """Liquidation price"""
        if not np.isnan(self.liquidation_prc_):
            return self.liquidation_prc_
        if self.side is self.Side.LONG:
            return self.entry_prc / (1 + 1 / self.leverage)
        else:  # short:
            return self.entry_prc / (1 - 1 / self.leverage)

    @computed_field(repr=False)
    @property
    def margin_asset(self) -> str:
        return util.get_margin_asset(self.ticker)
    
    @computed_field(repr=False)
    @property
    def fee_asset(self) -> str:
        return self.margin_asset

    @computed_field
    @property
    def pnl(self) -> float:
        """PnL = (mark - entry) * amount - fee"""
        prc_chg = self.mark_prc - self.entry_prc if self.side is self.Side.LONG else self.entry_prc - self.mark_prc
        return prc_chg * self.amount - self.fee

    @computed_field
    @property
    def pnl_pctg(self) -> float:
        """PnL in percentage = pnl / margin"""
        try:
            return self.pnl / self.margin
        except ZeroDivisionError:
            return np.nan

    @computed_field
    @property
    def notional(self) -> float:
        """Notional value of position = abs(amount) * contract size * mark price"""
        if not np.isnan(self.notional_):
            return self.notional_
        return abs(self.amount) * self.mark_prc * self.contract_size
    
    def __add__(self, other: Position) -> Position:
        if self.ticker != other.ticker or self.side != other.side:
            raise ValueError(f"Cannot add positions with different tickers or sides, {self.ticker=} {self.side=} vs {other.ticker=} {other.side=}")

        total_amount = self.amount + other.amount
        self_entry_prc = 0.0 if np.isnan(self.entry_prc) else self.entry_prc
        other_entry_prc = 0.0 if np.isnan(other.entry_prc) else other.entry_prc
        try:
            weighted_entry = (self_entry_prc * abs(self.amount) + other_entry_prc * abs(other.amount)) / abs(total_amount)
        except ZeroDivisionError:
            weighted_entry = np.nan
        combined_fee = self.fee + other.fee
        combined_margin = self.margin + other.margin
        latest_time = max(self.updated_at, other.updated_at)
        mark_prc = other.mark_prc

        return self.model_copy(update={
            "amount": total_amount,
            "entry_prc": weighted_entry,
            "mark_prc": mark_prc,
            "margin": combined_margin,
            "fee": combined_fee,
            "updated_at": latest_time
        })

    def __mul__(self, multiplier: float) -> Position:
        if not isinstance(multiplier, (int, float)):
            return NotImplemented
        if multiplier < 0:
            raise ValueError("Multiplier must be non-negative")

        return self.model_copy(update={
            "amount": self.amount * multiplier,
            "margin": self.margin * multiplier,
            "fee": self.fee * multiplier,
            "notional_": self.notional_ * multiplier if not np.isnan(self.notional_) else np.nan,
        })
    
    __rmul__ = __mul__

    def clear(self) -> None:
        self.amount = 0.0
        self.margin = 0.0
        self.fee = 0.0
        self.entry_prc = np.nan
        self.mark_prc = np.nan
        self.liquidation_prc_ = np.nan
        self.notional_ = np.nan
