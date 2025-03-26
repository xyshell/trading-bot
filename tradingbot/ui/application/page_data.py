"""
asset x frequency, health overview display
"""

import math
import threading
import time
from typing import Dict, List
import pandas as pd
import streamlit as st
import numpy as np

import tradingbot.util as util
import tradingbot.data as tbdata
from tradingbot.config import Config

tbconfig = Config()

tab_candlestick, _ = st.tabs(["📈Candlestick", "..."])


@st.cache_data
def get_candlestick_status(source: str, now: pd.Timestamp) -> pd.DataFrame:
    df = tbdata.Candlestick.display(source)
    df["freq_ts"] = df["freq"].apply(lambda x: pd.Timedelta(x))
    df["expected_count"] = (df["close_time_max"] - df["close_time_min"]) / df["freq_ts"]
    df["LatencyHealth"] = np.where(
        df["close_time_max"] >= now - df["freq_ts"] * 2, "🟢", np.where(df["close_time_max"] >= now - df["freq_ts"] * 25, "🟡", "🔴")
    )
    df["CountHealth"] = np.where(df["close_time_count"] == df["expected_count"], "🟢", "🟡")
    
    df = df[
        ["ticker", "freq", "close_time_min", "close_time_max", "close_time_count", "expected_count", "LatencyHealth", "CountHealth"]
    ].rename(
        columns={
            "close_time_min": "StartTime",
            "close_time_max": "EndTime",
            "close_time_count": "ActualCount",
            "expected_count": "ExpectedCount",
        }
    )
    return df


def update_candlestick(source: str, ticker_freq_start: List[Dict[str, str | pd.Timestamp]], end: pd.Timestamp) -> None:
    """Update candlestick data

    Args:
        source (str):
        ticker_freq_start (List[Dict[str, str | pd.Timestamp]]): e.g.
            [
                {"ticker": "USDT/BTC", "freq": "1h", "EndTime": pd.Timestamp('2025-03-23 15:59:59')},
                {"ticker": "USDT/ETH", "freq": "1h", "EndTime": pd.Timestamp('2025-03-23 14:59:59')}
            ]
        end (pd.Timestamp):

    Returns:
        None
    """

    def helper(ticker, freq, start, end):
        load_len = math.ceil((end - start) / pd.Timedelta(freq))
        candle = tbdata.Candlestick(source, ticker=ticker, freq=freq, closed_only=True, load_len=load_len)
        df = candle.get(end)
        df = df.iloc[:-1]
        candle.set(end, df)

    threads = []
    for item in ticker_freq_start:
        ticker = item["ticker"]
        freq = item["freq"]
        start = item["EndTime"]

        st.write(f"Updating {ticker} {freq} from {start.strftime('%Y-%m-%d %H:%M:%S')} to {end.strftime('%Y-%m-%d %H:%M:%S')}...")
        thread = threading.Thread(target=helper, args=(ticker, freq, start, end))
        thread.start()
        threads.append(thread)
    
    for thread in threads:
        thread.join()


with tab_candlestick:
    sources = list(tbconfig.source.__dict__.keys())
    with st.sidebar:
        sources = st.multiselect("Source", list(sources), default=sources)
    for source in sources:
        st.subheader(f"{source}")
        now = util.utc_now_factory()
        source_df = get_candlestick_status(source, now)

        event = st.dataframe(
            source_df,
            use_container_width=True,
            height=500,
            hide_index=True,
            on_select="rerun",
            selection_mode="multi-row",
        )

        ticker_freq_start = source_df.iloc[event.selection.rows][["ticker", "freq", "EndTime"]].to_dict(orient="records")
        button_update = st.button("Update Selection")
        if button_update:
            if not ticker_freq_start:
                st.warning("No selection made, nothing to update")
            else:
                update_candlestick(source, ticker_freq_start, now)
                st.success("Update successful!")
                progress_bar = st.progress(0, text="Reloading...")
                for percent_complete in range(100):
                    progress_bar.progress(percent_complete + 1, text="Reloading...")
                    time.sleep(0.01)
                time.sleep(0.5)
                st.rerun()
