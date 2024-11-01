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
        self.order_history: list[tuple[pd.Timestamp, Order]] = []  # record all filled orders
        self.transaction_history: list[Transaction] = []  # record all transactions
        self.account: Account  # keep track of all positions
        self.account_history: dict[pd.Timestamp, list[Account]] = {}  # record all positions
        self.report: dict[str, pd.DataFrame] = {}  # save report

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.param})"

    def __str__(self) -> str:
        return f"{self.__class__.__name__}_{"_".join([f"{v:.4f}" if isinstance(v, float) else str(v) for v in self.param.values()])}".replace(
            "/", ""
        )

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
        import matplotlib.pyplot as plt

        data = self.data
        # analyze results
        port_report = self.report["portfolio"]
        order_report = self.report["order"].query("status == 'FILLED'")
        sample_freq = util.inferred_freq2freq(port_report.index.inferred_freq)
        candlestick_highest = min(data.values(), key=lambda da: pd.Timedelta(da.freq))
        if pd.Timedelta(candlestick_highest.freq) > pd.Timedelta(sample_freq):
            candlestick = Candlestick(candlestick_highest.source, ticker=candlestick_highest.ticker, freq=sample_freq)
        else:
            candlestick = candlestick_highest
        candlestick_df = candlestick.load(now=port_report.index[-1], load_len=len(port_report))
        df = pd.merge_asof(port_report, candlestick_df, right_on="close_time", left_index=True)
        buy_sell = order_report["action"].to_frame()
        buy_sell["one"] = 1
        buy_sell_clean = buy_sell.pivot(columns="action", values="one").resample(sample_freq, closed="left").sum()
        buy_sell_clean = buy_sell_clean.loc[buy_sell_clean.index.isin(buy_sell.index)]
        df = pd.concat([df, buy_sell_clean], axis=1)
        buy_col = {Order.Action.BUY.name, Order.Action.OPEN_LONG.name, Order.Action.CLOSE_SHORT.name}
        sell_col = {Order.Action.SELL.name, Order.Action.OPEN_SHORT.name, Order.Action.CLOSE_LONG.name}
        df["BUY"] = np.where(df[list(buy_col & set(df.columns))].any(axis=1), df["close"], np.nan)
        df["SELL"] = np.where(df[list(sell_col & set(df.columns))].any(axis=1), df["close"], np.nan)
        if Order.Action.OPEN_LONG.name in df.columns and Order.Action.OPEN_SHORT.name in df.columns:
            df["BUY_PLUS"] = np.where(df[[Order.Action.OPEN_LONG.name, Order.Action.CLOSE_SHORT.name]].sum(axis=1) == 2, df["close"], np.nan)
        else:
            df["BUY_PLUS"] = np.nan
        if Order.Action.CLOSE_LONG.name in df.columns and Order.Action.CLOSE_SHORT.name in df.columns:
            df["SELL_PLUS"] = np.where(df[[Order.Action.OPEN_SHORT.name, Order.Action.CLOSE_LONG.name]].sum(axis=1) == 2, df["close"], np.nan)
        else:
            df["SELL_PLUS"] = np.nan
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
                mpf.make_addplot(df["BUY"], panel=1, type="scatter", markersize=50, marker="^", color="#4db344", secondary_y=False, label="BUY"),
                mpf.make_addplot(df["SELL"], panel=1, type="scatter", markersize=50, marker="v", color="#fa5f7e", secondary_y=False, label="SELL"),
                mpf.make_addplot(df["BUY_PLUS"], panel=1, type="scatter", markersize=50, marker=10, color="#4db344", secondary_y=False, label=""),
                mpf.make_addplot(df["SELL_PLUS"], panel=1, type="scatter", markersize=50, marker=11, color="#fa5f7e", secondary_y=False, label=""),
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
        plt.show()
        # fmt: on
