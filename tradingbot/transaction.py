from dataclasses import dataclass
import pandas as pd


@dataclass
class Transaction:
    """represent a transaction between two assets. sign of qty indicates long or short position"""
    frm_asset: str
    frm_qty: float
    to_asset: str
    to_qty: float
    fee_asset: str
    fee_qty: float
    prc_ticker: str
    prc: float
    timestamp: pd.Timestamp
