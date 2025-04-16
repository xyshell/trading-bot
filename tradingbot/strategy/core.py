import abc
import copy
import functools
import logging
import warnings

import numpy as np
import pandas as pd

from tradingbot.data.candlestick import Candlestick
import tradingbot.util as util
from tradingbot.balance import Balance
from tradingbot.transaction import Transaction
from tradingbot.order import Order
from tradingbot.data.core import Data


class Strategy(abc.ABC):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # ensure cls.param
        if not hasattr(cls, "param"):
            cls.param = {}
        else:
            assert isinstance(cls.param, dict), f"param must be dict, but {cls.param=}"

    def __init__(self, **kwargs):
        self.param = self.__class__.param.copy()
        self.currency: str = kwargs.pop("currency", "USDT")  # report currency
        self.param.update(kwargs)  # override default param

        @functools.wraps(self.__class__.next)
        def bound_next(*args, **kwargs):
            return self.__class__.next(self, *args, **kwargs)

        bound_next.trigger = copy.deepcopy(self.__class__.next.trigger)  # deepcopy trigger for each instance
        self.next = bound_next

        self.order: list[Order] = []  # keep track of all open orders
        self.order_history: list[Order] = []  # record all filled orders
        self.balance: Balance  # current balance
        self.balance_history: dict[pd.Timestamp, Balance] = {}  # record all positions
        self.transaction_history: list[Transaction] = []  # record all transactions
        self.store: dict[str, any] = {}  # store any user custom values
        self.store_history: dict[pd.Timestamp, dict[str, any]] = {}  # record all stores
        self.report: dict[str, pd.DataFrame] = {}  # save report
        self.now = None
        self.data: dict[str, Data]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.param})"

    def __str__(self) -> str:
        return f"{self.__class__.__name__}_{'_'.join([f'{v:.4f}' if isinstance(v, float) else str(v) for v in self.param.values()])}".replace(
            "/", ""
        )

    def start(self):
        self.logger = logging.getLogger(str(self))
        # reset triggers
        for tri in self.next.trigger:
            tri.checked.clear()

    @abc.abstractmethod
    def next(self):
        pass

    def stop(self):
        pass

    def plot(self, /, engine="matplotlib", **kwargs):
        """Plot strategy result

        Returns:
            Figure object depend on engine
        """
        assert engine == "matplotlib", f"{engine=} not supported"
        import mplfinance as mpf

        data = self.data
        port_report = self.report["portfolio"].set_index("timestamp")
        asset_report = self.report["asset"].set_index("timestamp")
        nav_col = f"NAV_{self.currency}"
        asset_report = port_report.join(asset_report).fillna(0.0)
        transaction_report = self.report["transaction"]
        sample_freq = util.inferred_freq2freq(port_report.index.inferred_freq)
        candlestick_highest = min(data.values(), key=lambda da: pd.Timedelta(da.freq))
        if pd.Timedelta(candlestick_highest.freq) > pd.Timedelta(sample_freq):
            candlestick = Candlestick(candlestick_highest.source, ticker=candlestick_highest.ticker, freq=sample_freq)
        else:
            candlestick = candlestick_highest
        candlestick_df = candlestick.load(now=port_report.index[-1], load_len=len(port_report))
        df = pd.merge_asof(asset_report, candlestick_df, right_on="close_time", left_index=True)
        buy_sell = transaction_report[["timestamp", "frm_asset", "frm_qty", "to_asset", "to_qty", "prc"]].copy()
        buy_sell["frm_qty_pos"] = buy_sell["frm_qty"] > 0
        buy_sell["frm_qty_neg"] = buy_sell["frm_qty"] < 0
        buy_sell["to_qty_pos"] = buy_sell["to_qty"] > 0
        buy_sell["to_qty_neg"] = buy_sell["to_qty"] < 0
        buy_sell["frm_asset_eq_currency"] = buy_sell["frm_asset"] == self.currency
        buy_sell["to_asset_eq_currency"] = buy_sell["to_asset"] == self.currency

        buy_sell["BUY"] = np.where(
            buy_sell["frm_asset_eq_currency"] & buy_sell["to_qty_pos"] | buy_sell["to_asset_eq_currency"] & buy_sell["frm_qty_neg"],
            buy_sell["prc"], 
            np.nan
        )
        buy_sell["SELL"] = np.where(
            buy_sell["to_asset_eq_currency"] & buy_sell["frm_qty_pos"] | buy_sell["frm_asset_eq_currency"] & buy_sell["to_qty_neg"],
            buy_sell["prc"], 
            np.nan
        )

        df = pd.concat([df, buy_sell.set_index("timestamp")[["BUY", "SELL"]].drop_duplicates()], axis=1)
        if "volume" not in df.columns and "base_volume" in df.columns:
            df.rename(columns={"base_volume": "volume"}, inplace=True)
        df.drop_duplicates(subset=["ticker", "close_time"], keep="last", inplace=True)
        # fmt: off
        fig, axlist = mpf.plot(
            df,
            mav=kwargs.pop("mav", []),
            mavcolors=kwargs.pop("mavcolors", []),
            type="candle",
            style="charles",
            volume=True,
            volume_alpha=0.3,
            title=f"{self.__class__.__name__}_{'_'.join([str(p) for p in self.param.values()])}",
            main_panel=1,
            volume_panel=2,
            figsize=(10, 5),
            tight_layout=True,
            scale_padding={"left": 0.2, "right": 1.0, "top": 0.5, "bottom": 0.5},
            xrotation=0,
            datetime_format="%y/%m/%d %H:%M",
            addplot=[
                # panel 0
                mpf.make_addplot(df[nav_col], panel=0, alpha=1.0, color="b", label=nav_col, secondary_y=False),
                *[mpf.make_addplot(df[col], panel=0, alpha=0.4, secondary_y=True, label=col) for col in asset_report.columns if col != nav_col],
                # panel 1
                mpf.make_addplot(df["BUY"], panel=1, type="scatter", markersize=50, marker="^", color="#4db344", secondary_y=False, label="BUY"),
                mpf.make_addplot(df["SELL"], panel=1, type="scatter", markersize=50, marker="v", color="#fa5f7e", secondary_y=False, label="SELL"),
                # mpf.make_addplot(df["BUY_PLUS"], panel=1, type="scatter", markersize=50, marker=10, color="#4db344", secondary_y=False, label=""),
                # mpf.make_addplot(df["SELL_PLUS"], panel=1, type="scatter", markersize=50, marker=11, color="#fa5f7e", secondary_y=False, label=""),
                # panel 2
                # volume
            ],
            warn_too_much_data=len(df),
            num_panels=3 + kwargs.pop("add_panels", 0),
            returnfig=True,
        )
        fig.suptitle(fig._suptitle.get_text(), y=1.0, fontsize=12)
        with util.set_level(logging.getLogger("matplotlib.legend"), logging.ERROR), warnings.catch_warnings():
            warnings.filterwarnings(
                action="ignore", category=UserWarning, message="No artists with labels found to put in legend"
            )
            for i, ax in enumerate(axlist):
                _ = ax.tick_params(axis="x", labelsize=5)
                _ = ax.tick_params(axis="y", labelsize=5)
                _ = ax.legend(loc="upper left" if i % 2 != 0 else "lower right", fontsize=6, ncol=2)
        return fig
        # fmt: on
