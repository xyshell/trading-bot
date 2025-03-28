import copy
import typing

from tradingbot.position import SpotPosition, Position
import tradingbot.util as util


class Account:
    """Account is a collection of open positions"""

    @util.validate
    def __init__(self, base_currency: str, positions: list[Position] = []):
        """Initialize an account

        Args:
            base_currency (str): base currency, e.g. "USDT"
            positions (list[Position], optional): initial positions. Defaults to [].
        """
        self._base_currency = base_currency
        self._positions: dict[str, Position] = {pos.asset: pos for pos in positions}

    @property
    def base_currency(self) -> str:
        return self._base_currency

    @property
    def positions(self) -> dict[str, Position]:
        return self._positions

    @util.validate
    def add_position(self, pos: Position) -> None:
        """Add a position to the account, consolidating if necessary
        
        Args:
            pos (Position): position
        """
        if pos.asset in self._positions:
            consolidated_pos = self._consolidate_position(self._positions[pos.asset], pos)
            self._positions[pos.asset] = consolidated_pos
        else:
            self._positions[pos.asset] = pos

    @staticmethod
    def _consolidate_position(pos1: Position, pos2: Position) -> Position:
        """Consolidate two positions
        
        Args:
            pos1 (Position): existing position
            pos2 (Position): additional position

        Returns:
            Position: consolidated position
        """
        assert type(pos1) is type(pos2), f"{type(pos1)=} must match {type(pos2)=}"
        assert pos1.asset == pos2.asset, f"{pos1.asset=} must match {pos2.asset=}"
        new_qty = pos1.qty + pos2.qty
         
        if isinstance(pos1, SpotPosition):
            if pos1.qty * new_qty < 0 or pos1.entry_cost.asset != pos2.entry_cost.asset:
                # if position direction is flipped or entry cost tickers are different, use pos2's entry cost
                return SpotPosition(asset=pos1.asset, qty=new_qty, entry_cost=pos2.entry_cost)
            else:  # add or reduce position
                new_entry_fee_qty = (pos2.entry_cost.qty * pos2.qty + pos1.entry_cost.qty * pos1.qty) / new_qty if new_qty else 0.0
                return SpotPosition(asset=pos1.asset, qty=new_qty, entry_cost=Position(asset=pos1.entry_cost.asset, qty=new_entry_fee_qty))
        elif isinstance(pos1, Position):
            return Position(asset=pos1.asset, qty=new_qty)
        
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"Account({self._positions})"

    def __contains__(self, ticker: str) -> bool:
        return ticker in self._positions

    def __getitem__(self, ticker: str) -> Position:
        return self._positions[ticker]

    def __setitem__(self, ticker: str, pos: Position) -> None:
        assert pos.asset == ticker, f"{pos.asset=} must match {ticker=}"
        self._positions[pos.asset] = pos

    def __iter__(self) -> typing.Iterator[Position]:
        return iter(self._positions)

    def __add__(self, pos: Position) -> typing.Self:
        self = copy.deepcopy(self)
        pos = copy.deepcopy(pos)
        self.add_position(pos)
        return self

    def __sub__(self, pos: Position) -> typing.Self:
        self = copy.deepcopy(self)
        pos = -pos
        self.add_position(pos)
        return self

    def is_sufficient(self) -> bool:
        # TODO: for margin positions, check margin
        return all(pos.qty >= 0 for pos in self._positions.values() if isinstance(pos, SpotPosition))
