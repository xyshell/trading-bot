import abc
import logging
import warnings

import numpy as np
import pandas as pd

from tradingbot.data.candlestick import Candlestick
import tradingbot.util as util
from tradingbot.model import Account, Order, Transaction


class Strategy(abc.ABC):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "param"):
            cls.param = {}

    def __init__(self, **kwargs):
        self.param = self.__class__.param.copy()
        self.param.update(kwargs)

        self.pending_order: list[Order] = []  # keep track of all pending orders
        self.order_history: dict[pd.Timestamp, Order] = {}  # record all filled orders
        self.transaction_history: list[Transaction] = []  # record all transactions
        self.account: Account  # keep track of all positions
        self.account_history: dict[pd.Timestamp, list[Account]] = {}  # record all positions
        self.report: dict[str, pd.DataFrame] = {}  # save report

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.param})"

    def __str__(self) -> str:
        return f"{self.__class__.__name__}_{"_".join([str(v) for v in self.param.values()])}".replace("/", "")

    def start(self):
        pass

    @abc.abstractmethod
    def next(self):
        pass

    def stop(self):
        pass

    def plot(self, /, engine="matplotlib", **kwargs) -> None:
        assert engine == "matplotlib", f"{engine=} not supported"

        import mplfinance as mpf

        data = self.data
        # analyze results
        port_report = self.report["portfolio"]
        order_report = self.report["order"].query("status == 'FILLED'")
        sample_freq = util.inferred_freq2freq(port_report.index.inferred_freq)
        candlestick = next(da for da in data.values() if isinstance(da, Candlestick) and da.freq == sample_freq)
        candlestick_df = candlestick.load(now=port_report.index[-1], load_len=len(port_report))
        df = pd.merge_asof(port_report, candlestick_df, right_on="close_time", left_index=True)
        buy_sell = order_report["action"].to_frame()
        buy_sell["one"] = 1
        df = pd.concat([df, buy_sell.pivot(columns="action", values="one")], axis=1)
        df["BUY"] = (df["BUY"] * df["close"]) if "BUY" in df.columns else np.nan
        df["SELL"] = (df["SELL"] * df["close"]) if "SELL" in df.columns else np.nan
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
            figsize=(15.5, 7),
            tight_layout=True,
            scale_padding={"left": 0.2, "right": 1.0, "top": 0.5, "bottom": 0.5},
            xrotation=0,
            datetime_format="%y/%m/%d %H:%M",
            addplot=[
                mpf.make_addplot(df["nav"], panel=0, alpha=1.0, color="b", label="NAV"),
                *[mpf.make_addplot(df[col], panel=0, alpha=0.4, secondary_y=False, label=col) for col in port_report.columns if col != "nav"],
                mpf.make_addplot(df["BUY"], panel=1, type="scatter", markersize=50, marker="^", color="#6cfa5f", secondary_y=False, label="BUY"),
                mpf.make_addplot(df["SELL"], panel=1, type="scatter", markersize=50, marker="v", color="#fa5f7e", secondary_y=False, label="SELL"),
            ],
            warn_too_much_data=len(df),
            returnfig=True
        )
        with util.set_level(logging.getLogger("matplotlib.legend"), logging.ERROR), warnings.catch_warnings():
            warnings.filterwarnings(
                action="ignore", category=UserWarning, message="No artists with labels found to put in legend"
            )
            for ax in axlist:
                _ = ax.tick_params(axis="x", labelsize=5)
                _ = ax.tick_params(axis="y", labelsize=5)
                _ = ax.legend(loc="upper left", fontsize=6)
        # fmt: on
