import copy
import typing

from pydantic import BaseModel, ConfigDict, computed_field, model_validator


class Position(BaseModel):
    """Generic position"""
    asset: str  # e.g. BTC, USDT
    qty: float  # quantity, with sign indicating long or short position

    def __neg__(self):
        return Position(asset=self.asset, qty=-self.qty)


class SpotPosition(Position):
    """Spot market position"""
    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    entry_cost: Position  # entry cost, e.g. Position(asset="USDT", qty=12345.0)
    _market_value: Position | None = None  # market
    
    @model_validator(mode="after")
    def _(self) -> typing.Self:
        if self._market_value is None:
            self._market_value = copy.deepcopy(self.entry_cost)
        else:
            assert self._market_value.asset == self.entry_cost.asset
        return self

    @property
    def market_value(self) -> Position:
        """Getter for market value"""
        return self._market_value
    
    @market_value.setter
    def market_value(self, pos: Position) -> None:
        """Setter for market value"""
        assert pos.asset == self.entry_cost.asset
        self._market_value = pos

    @computed_field
    def pnl(self) -> Position:
        """Profit and loss"""
        return Position(asset=self.entry_cost.asset, qty=self.market_value.qty - self.entry_cost.qty)

    def __neg__(self):
        entry_cost = copy.deepcopy(self.entry_cost)
        market_value = copy.deepcopy(self.market_value)
        entry_cost.qty = -entry_cost.qty
        market_value.qty = -market_value.qty
        return SpotPosition(asset=self.asset, qty=-self.qty, entry_cost=self.entry_cost, market_value=self.market_value)


class MarginPosition(Position):
    """Margin market position"""
    pass
#     leverage: int = -1
#     margin: tuple[str, float] = ("", 0.0)
#     last_market_val_: float | None = Field(default=None, exclude=True, repr=False)

#     @SpotPosition.market_val.setter
#     def market_val(self, value: float) -> None:
#         self.last_market_val_ = value if self.last_market_val_ is None else self.market_val  # init or update last market price
#         self.market_val_ = value
#         mark_to_market_pnl = (self.market_val - self.last_market_val_) * self.qty 
#         self.margin = (self.margin[0], float(self.margin[1] + mark_to_market_pnl))  # mark to market 

#     @computed_field
#     def liq_prc(self) -> float:  # liquidation price
#         sign = -1 if self.qty > 0 else 1
#         return self.entry_prc * (1 + sign / (self.leverage if self.leverage > 0 else np.nan))

#     def clear(self) -> None:
#         super().clear()
#         self.margin = (self.margin[0], 0.0)
