import numpy as np
import pytest
import pandas as pd

from tradingbot.position import Position


def make_position(
    amount: float, side: str = "long", entry: float = 20000, mark: float = 21000, margin: float = 1000, fee: float = 5
) -> Position:
    return Position(
        ticker="BTC/USDT:USDT",
        side=side,
        amount=amount,
        leverage=5,
        entry_prc=entry,
        mark_prc=mark,
        margin=margin,
        fee=fee,
        created_at=pd.Timestamp("2024-01-01 00:00:00"),
        updated_at=pd.Timestamp("2024-01-01 00:00:00"),
        contract_size=1.0,
    )


def test_position_side_and_pnl():
    pos = make_position(amount=1.0, entry=20000, mark=21000, margin=1000, fee=10)

    assert pos.side.value == "long"
    assert pos.pnl == pytest.approx((21000 - 20000) * 1.0 - 10)
    assert pos.pnl_pctg == pytest.approx(pos.pnl / 1000)
    assert pos.notional == pytest.approx(21000.0)


def test_position_addition_same_side():
    pos1 = make_position(amount=1.0, entry=20000, margin=1000, fee=5)
    pos2 = make_position(amount=2.0, entry=22000, margin=2000, fee=10)
    pos2.updated_at = pd.Timestamp("2024-01-01 01:00:00")  # simulate later timestamp

    combined = pos1 + pos2
    expected_entry = (1 * 20000 + 2 * 22000) / 3

    assert combined.amount == 3.0
    assert combined.entry_prc == pytest.approx(expected_entry)
    assert combined.margin == 3000
    assert combined.fee == 15
    assert combined.updated_at == pos2.updated_at


def test_position_addition_mismatch_ticker():
    pos1 = make_position(amount=1.0)
    pos2 = make_position(amount=1.0)
    pos2.ticker = "ETH/USDT:USDT"  # ⛔ different ticker

    with pytest.raises(ValueError, match="different tickers"):
        _ = pos1 + pos2


def test_position_addition_mismatch_side():
    pos1 = make_position(amount=1.0)
    pos2 = make_position(amount=-0.5, side="short")  # ⛔ opposite side

    with pytest.raises(ValueError, match="different tickers or sides"):
        _ = pos1 + pos2


def test_position_scaling():
    original = make_position(amount=2.0, margin=1000, fee=10)

    # Test __mul__
    scaled_right = original * 0.5
    assert scaled_right.amount == pytest.approx(1.0)
    assert scaled_right.margin == pytest.approx(500.0)
    assert scaled_right.fee == pytest.approx(5.0)

    # Test __rmul__
    scaled_left = 0.25 * original
    assert scaled_left.amount == pytest.approx(0.5)
    assert scaled_left.margin == pytest.approx(250.0)
    assert scaled_left.fee == pytest.approx(2.5)


def test_position_clear():
    pos = make_position(amount=1.0, entry=20000, mark=21000, margin=1000, fee=5)

    # Ensure initial state is non-zero
    assert pos.amount == 1.0
    assert pos.margin == 1000
    assert pos.fee == 5
    assert not np.isnan(pos.entry_prc)
    assert not np.isnan(pos.mark_prc)

    # Clear the position (simulate liquidation)
    pos.clear()

    # Verify all economic values are reset
    assert pos.amount == 0.0
    assert pos.margin == 0.0
    assert pos.fee == 0.0
    assert np.isnan(pos.entry_prc)
    assert np.isnan(pos.mark_prc)
    assert np.isnan(pos.liquidation_prc_)
    assert np.isnan(pos.notional_)
    # Ensure other attributes are not reset
    assert pos.ticker
    assert pos.side
    assert not np.isnan(pos.leverage)

    # Ensure timestamp was updated
    assert isinstance(pos.updated_at, pd.Timestamp)


def test_close_position():
    existing = Position(
        ticker="USDT/BTC:USDT",
        side="short",
        amount=0.005000786433592835,
        leverage=5.0,
        entry_prc=95593.89,
        mark_prc=92018.41,
        margin=95.60892564927316,
        fee=0.09560892564927316,
        id_=None,
        created_at=pd.Timestamp("2025-02-17 14:00:00"),
        updated_at=pd.Timestamp("2025-02-25 02:00:00"),
        contract_size=1.0,
        liquidation_prc=119492.36249999999,
        pnl=17.784602951933216,
        pnl_pctg=0.18601404451686168,
        notional=460.1644163687833,
    )
    delta = Position(
        ticker="USDT/BTC:USDT",
        side="short",
        amount=-0.001000157286718567,
        leverage=5.0,
        entry_prc=92018.41,
        mark_prc=92018.41,
        margin=-19.121785129854633,
        fee=-0.019121785129854633,
        id_=None,
        created_at=pd.Timestamp("2025-02-25 02:00:00"),
        updated_at=pd.Timestamp("2025-02-25 02:00:00"),
        contract_size=1.0,
        liquidation_prc=115023.0125,
        pnl=0.019121785129854633,
        pnl_pctg=-0.001,
        notional=92.03288327375667,
    )

    res = existing + delta

    # Direct fields
    assert res.ticker == existing.ticker
    assert res.side == existing.side
    assert res.mark_prc == delta.mark_prc
    assert res.updated_at == delta.updated_at
    assert res.amount == pytest.approx(0.004000629146874268)
    assert res.margin == pytest.approx(76.48714051941852)
    assert res.fee == pytest.approx(0.07648714051941852)

    # Weighted average entry price
    assert res.entry_prc == existing.entry_prc

    # Derived fields
    expected_pnl = (res.entry_prc - res.mark_prc) * res.amount - res.fee
    assert res.pnl == pytest.approx(expected_pnl)

    expected_pctg = expected_pnl / res.margin
    assert res.pnl_pctg == pytest.approx(expected_pctg)

    expected_notional = abs(res.amount) * res.mark_prc
    assert res.notional == pytest.approx(expected_notional)