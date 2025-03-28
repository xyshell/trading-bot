from dataclasses import dataclass
import pandas as pd


@dataclass
class Transaction:
    frm_asset: str
    frm_qty: float
    to_asset: str
    to_qty: float
    fee_asset: str
    fee_qty: float
    prc_ticker: str
    prc: float
    timestamp: pd.Timestamp

    # model_config = ConfigDict(arbitrary_types_allowed=True)

    # from_pos: Position  # position consumed
    # to_pos: Position  # position produced
    # tcost_pos: Position  # transaction cost
    # timestamp: pd.Timestamp = pd.NaT  # time of transaction

    # @model_validator(mode="after")
    # def _(self) -> typing.Self:
    #     if self.tcost_pos.ticker == self.from_pos.ticker:
    #         assert np.isclose(
    #             self.from_pos.qty - self.tcost_pos.qty, util.convert(self.to_pos.ticker, self.ticker, self.prc)[1]
    #         ), f"Failed to reconcile {self}"
    #     elif self.tcost_pos.ticker == self.to_pos.ticker:
    #         assert np.isclose(
    #             self.tcost_pos.qty + self.to_pos.qty, util.convert(self.from_pos.ticker, self.ticker, self.prc)[1]
    #         ), f"Failed to reconcile {self}"
    #     return self

    # def __bool__(self) -> bool:
    #     return not (self.from_pos.qty == self.to_pos.qty == 0)


# class _MarginTransaction(Transaction):
#     leverage: int

#     def _validate(self) -> None:
#         super()._validate()
#         quote_ticker = util.get_quote_ticker(self.ticker)
#         assert self.tcost[0] == quote_ticker, f"Tcost should be charged in '{quote_ticker}'"


# class OpenTransaction(_MarginTransaction):
#     """conversion from normal position to margin position"""
#     leverage: int

#     @model_validator(mode="after")
#     def reconcile(self) -> typing.Self:
#         self._validate()
#         lhs = (self.from_[1] - self.tcost[1])
#         rhs = abs(util.convert(self.to_, self.ticker, self.prc)[1] / self.leverage)
#         assert np.isclose(lhs, rhs), f"Failed to reconcile {self}"
#         return self

#     def split(self) -> tuple[SpotPosition, MarginSpotPosition, SpotPosition]:
#         quote_ticker = util.get_quote_ticker(self.ticker)
#         return (
#             SpotPosition(asset=self.from_[0], qty=self.from_[1], entry_prc=0.0),  # withdraw from normal position
#             MarginSpotPosition(
#                 ticker=self.to_[0], 
#                 qty=self.to_[1], 
#                 entry_prc=self.prc, 
#                 leverage=self.leverage, 
#                 margin=(quote_ticker, self.from_[1] - self.tcost[1])
#             ),  # deposit to margin position
#             SpotPosition(asset=self.tcost[0], qty=self.tcost[1]),  # vanish as tcost
#         )
    

# class CloseTransaction(_MarginTransaction):
#     """conversion from normal position to margin position"""
#     leverage: int

#     @model_validator(mode="after")
#     def reconcile(self) -> typing.Self:
#         self._validate()
#         return self

#     def split(self) -> tuple[MarginSpotPosition, SpotPosition, SpotPosition]:
#         quote_ticker = util.get_quote_ticker(self.ticker)
#         return (
#             MarginSpotPosition(
#                 ticker=self.from_[0], 
#                 qty=self.from_[1], 
#                 entry_prc=self.prc, 
#                 leverage=self.leverage,
#                 margin=(quote_ticker, self.to_[1] + self.tcost[1]),
#             ),  # withdraw from margin position
#             SpotPosition(asset=self.to_[0], qty=self.to_[1], entry_prc=0.0),  # deposit to normal position
#             SpotPosition(asset=self.tcost[0], qty=self.tcost[1]),  # vanish as tcost
#         )
