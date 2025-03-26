import importlib
import logging
import warnings

import concurrent
import requests
from retry import retry
from typing_extensions import Annotated
import pandas as pd
import sqlalchemy as sa

import tradingbot.util as util
from tradingbot.config import Config
from tradingbot.util import ModeType
from tradingbot.data.core import Data
from tradingbot.database import Database

logger = logging.getLogger(__name__)


class Candlestick(Data):
    MIN_FREQ_USAGE = "5m"
    field = {
        "ticker": Annotated[str, "primary_key", "index_ticker_opentime"],
        "open_time": Annotated[pd.Timestamp, "index_ticker_opentime"],
        "close_time": Annotated[pd.Timestamp, "primary_key"],
        "open": float,
        "high": float,
        "low": float,
        "close": float,
        "base_volume": float,
        "quote_volume": float,
    }

    def __init__(self, *_, ticker: str, freq: str, closed_only: bool = True, **kwargs):
        """
        Args:
            ticker (str): ticker name, e.g. "USDT/BTC"
            freq (str): update frequency and candlestick interval, e.g. "1h", "1d"
            closed_only (bool): if True, only return closed candles, default is True
        """
        super().__init__(**kwargs)
        self.ticker = ticker
        self.freq = freq
        self.closed_only = closed_only

    def __repr__(self):
        df = pd.concat({key: self[key] for key in self.field}, axis=1)
        return f"{self.__class__.__name__}(ticker={self.ticker}, freq={self.freq}, closed_only={self.closed_only}, load_len={self.load_len}, field={list(self.field.keys())})\n{df}"

    @property
    def table_name(self) -> str:
        return f"candlestick_{self.source}_{self.freq}"

    @Data.mode.setter
    @util.validate
    def mode(self, mode: ModeType):
        self._mode = mode

    def load(self, now: pd.Timestamp, **kwargs) -> pd.DataFrame:
        """load from database for child class"""
        df = super(self.__class__, self).get(now, **kwargs)
        if self.mode == "backtest" and not self.closed_only and pd.Timedelta(self.freq) > pd.Timedelta(Candlestick.MIN_FREQ_USAGE):
            # extend candlestick using Candlestick.MIN_FREQ_USAGE
            max_close_time = df["close_time"].max()
            max_close_time = pd.NaT if pd.isna(max_close_time) else max_close_time
            load_len = (now - max_close_time) // pd.Timedelta(Candlestick.MIN_FREQ_USAGE)
            if load_len > 0:
                candlestick = Candlestick(
                    self.source,
                    mode="backtest",
                    ticker=self.ticker,
                    freq=Candlestick.MIN_FREQ_USAGE,
                    closed_only=True,
                    load_len=load_len,
                )
                candlestick.update(now)
                agg_rule = {
                    "ticker": "last",
                    "close_time": "last",
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "base_volume": "sum",
                }
                if "open_time" in df.columns:
                    agg_rule["open_time"] = "first"
                if "quote_volume" in df.columns:
                    agg_rule["quote_volume"] = "sum"
                aug_df = (
                    candlestick.frame.set_index("close_time", drop=False)
                    .resample(self.freq, closed="right", label="right")
                    .agg(agg_rule)
                ).reset_index(drop=True)
                df = pd.concat([df.iloc[len(aug_df) :], aug_df], ignore_index=True)
        return df

    def get(self, now: pd.Timestamp, **kwargs) -> pd.DataFrame:
        load_len = kwargs.pop("load_len", self.load_len)
        since = kwargs.pop("since", None)

        config = Config()
        engine = Database.get_engine(config.general.db_url)
        table = Database.get_data_table(self.__class__, self.table_name)

        sql = (
            sa.select(*table.columns)
            .where(table.c.ticker == self.ticker)
            .where(table.c.close_time <= now.to_pydatetime())
            .order_by(table.c.close_time.desc())
        )
        if since is not None:
            sql = sql.where(table.c.close_time >= pd.Timestamp(since).to_pydatetime())
        else:
            sql = sql.limit(load_len)
        with engine.connect() as conn:
            df = pd.read_sql(sql, con=conn).sort_values("close_time")
        if since is None:
            df = df.tail(load_len)
        return df.reset_index(drop=True)

    def set(self, now: pd.Timestamp, df: pd.DataFrame, **kwargs) -> None:
        config = Config()
        engine = Database.get_engine(config.general.db_url)
        table = Database.get_data_table(self.__class__, self.table_name)

        df = df.loc[df["close_time"] <= now].copy()  # only save closed candles
        if df.empty:
            return

        with warnings.catch_warnings():
            warnings.filterwarnings(
                action="ignore", category=FutureWarning, message="The behavior of DatetimeProperties.to_pydatetime is deprecated"
            )
            df["close_time"] = df["close_time"].dt.to_pydatetime()
            if "open_time" in df.columns:
                df["open_time"] = df["open_time"].dt.to_pydatetime()

        sqlalchemy_dialect = importlib.import_module(f"sqlalchemy.dialects.{engine.dialect.name}")
        insert = sqlalchemy_dialect.insert
        insert_stmt = insert(table).values(df.to_dict(orient="records"))
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=[table.c.ticker, table.c.close_time],
            set_={col.key: col for col in table.columns if col not in [table.c.ticker, table.c.close_time]},
        )

        with engine.connect() as conn:
            result = conn.execute(upsert_stmt)
            conn.commit()
            logger.debug(f"upsert affected {result.rowcount} rows in {self.table_name}")

    @classmethod
    def display(cls, source: str) -> pd.DataFrame:
        """Display basic stats of candlestick data
        
        Args:
            source (str): source name
        
        Returns:
            pd.DataFrame
        """
        config = Config()
        engine = Database.get_engine(config.general.db_url)
        metadata = sa.MetaData()
        metadata.reflect(engine)
        tables = [table_name for table_name in metadata.tables.keys() if table_name.startswith(f"candlestick_{source}")]
        freqs = [table_name.split("_")[-1] for table_name in tables]

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {}
            for freq in freqs:
                table = Database.get_data_table(cls, f"candlestick_{source}_{freq}")
                query = (
                    sa.select(
                        table.c.ticker, 
                        sa.func.min(table.c.close_time).label("close_time_min"), 
                        sa.func.max(table.c.close_time).label("close_time_max"), 
                        sa.func.count(table.c.close_time).label("close_time_count"),
                        sa.func.avg(table.c.close).label("close_avg"),
                        sa.func.avg(table.c.base_volume).label("base_volume_avg")
                    )
                    .group_by(table.c.ticker)
                    .order_by(table.c.ticker)
                )
                futures[freq] = executor.submit(pd.read_sql, query, con=engine.connect())
        df = pd.concat({freq: future.result().set_index("ticker") for freq, future in futures.items()})
        df.index.rename("freq", level=0, inplace=True)
        df = df.swaplevel(0, 1).sort_values("close_time_max", ascending=False).reset_index()
        return df


class YahooCandlestick(Candlestick):
    """Yahoo Finance candlestick data. https://aroussi.com/post/python-yahoo-finance
    valid freq: '1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo'. intraday data cannot extend last 60 days
    """

    source = "yahoo"

    field = {
        "ticker": Annotated[str, "primary_key"],
        "close_time": Annotated[pd.Timestamp, "primary_key"],
        "open": float,
        "high": float,
        "low": float,
        "close": float,
        "volume": float,
    }

    def __init__(self, *_, ticker: str, freq: str, **kwargs):
        import yfinance as yf

        super().__init__(ticker=ticker, freq=freq, **kwargs)
        ccy, security = ticker.split("/")
        sec = yf.Ticker(security)
        assert sec.info["currency"] == ccy, f"Currency mismatched: '{ccy}' != '{sec.info['currency']}'"

    @retry((requests.exceptions.ReadTimeout, requests.exceptions.ProxyError, requests.exceptions.ConnectionError), tries=3)
    def get(self, now: pd.Timestamp, **kwargs) -> pd.DataFrame:
        import yfinance as yf

        symbol = self.ticker.split("/")[1]
        sec = yf.Ticker(symbol)
        period = "5d" if self.freq == "1m" else "1mo" if self.freq in {"2m", "5m", "15m", "30m", "60m", "90m", "1h"} else "max"
        df = sec.history(period, interval=self.freq, actions=False).round(2)
        df.index = df.index.rename("close_time").tz_localize(None)
        df.reset_index(inplace=True)
        df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        df["ticker"] = self.ticker
        df.sort_values(["ticker", "close_time"], ignore_index=True, inplace=True)
        if self.closed_only or self.mode == "backtest":
            df = df.loc[df["close_time"] <= now]
        return df.tail(self.load_len).reset_index(drop=True)


class BinanceCandlestick(Candlestick):
    """Binance candlestick data"""

    source = "binance"

    def __init__(
        self,
        *_,
        ticker: str,
        freq: str,
        api_key: str = None,
        api_secret: str = None,
        http_proxy: str = None,
        https_proxy: str = None,
        **kwargs,
    ):
        super().__init__(ticker=ticker, freq=freq, **kwargs)
        config = Config()
        self._api_key = api_key or config.source.binance.api_key
        self._api_secret = api_secret or config.source.binance.api_secret
        self._http_proxy = http_proxy or config.general.http_proxy
        self._https_proxy = https_proxy or config.general.https_proxy

    @property
    def _client(self):
        from binance import Client

        proxy = {}
        if self._http_proxy:
            proxy["http"] = self._http_proxy
        if self._https_proxy:
            proxy["https"] = self._https_proxy
        requests_params = {"proxies": proxy} if proxy else None

        return Client(self._api_key, self._api_secret, requests_params)

    @retry((requests.exceptions.ReadTimeout, requests.exceptions.ProxyError, requests.exceptions.ConnectionError), tries=3)
    def get(self, now: pd.Timestamp, **kwargs) -> pd.DataFrame:
        start = now - pd.Timedelta(self.freq) * (self.load_len + 1)
        end = now
        start_str = start.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end.strftime("%Y-%m-%d %H:%M:%S")

        symbol = "".join(self.ticker.split("/")[::-1])
        with warnings.catch_warnings():
            warnings.filterwarnings(
                action="ignore", category=DeprecationWarning, message="datetime.datetime.utcfromtimestamp() is deprecated"
            )
            candlestick = self._client.get_historical_klines(symbol, self.freq, start_str, end_str)
        df = pd.DataFrame(
            candlestick,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_asset_volume",
                "number_of_trades",
                "taker_buy_base_asset_volume",
                "taker_buy_quote_asset_volume",
                "ignore",
            ],
        )
        df = df[["timestamp", "close_time", "open", "high", "low", "close", "volume", "quote_asset_volume"]]
        df["timestamp"] = pd.to_datetime(df["timestamp"] // 1000, unit="s")
        df["close_time"] = pd.to_datetime(df["close_time"] // 1000, unit="s")
        df[["open", "high", "low", "close", "volume", "quote_asset_volume"]] = df[
            ["open", "high", "low", "close", "volume", "quote_asset_volume"]
        ].astype("float")
        df = df.rename(columns={"timestamp": "open_time", "volume": "base_volume", "quote_asset_volume": "quote_volume"})
        df["ticker"] = self.ticker
        df = df.sort_values(["ticker", "open_time"], ignore_index=True)
        if self.closed_only or self.mode == "backtest":
            df = df.loc[df["close_time"] <= now]
        return df.tail(self.load_len).reset_index(drop=True)


class OkxCandlestick(Candlestick):
    """Okx candlestick data"""

    source = "okx"

    def __init__(self, *_, ticker: str, freq: str, http_proxy: str = None, https_proxy: str = None, **kwargs):
        super().__init__(ticker=ticker, freq=freq, **kwargs)
        config = Config()
        self._http_proxy = http_proxy or config.general.http_proxy
        self._https_proxy = https_proxy or config.general.https_proxy

    @property
    def _client(self):
        import ccxt

        class OkxClient(ccxt.okx):
            def parse_ohlcv(self, ohlcv, market = None) -> list:
                #
                #     [
                #         "1678928760000",  # timestamp
                #         "24341.4",  # open
                #         "24344",  # high
                #         "24313.2",  # low
                #         "24323",  # close
                #         "628",  # contract volume
                #         "2.5819",  # base volume
                #         "62800",  # quote volume
                #         "0"  # candlestick state
                #     ]
                #
                res = self.handle_market_type_and_params('fetchOHLCV', market, None)
                type = res[0]
                volumeIndex = 5 if (type == 'spot') else 6
                return [
                    self.safe_integer(ohlcv, 0),
                    self.safe_number(ohlcv, 1),
                    self.safe_number(ohlcv, 2),
                    self.safe_number(ohlcv, 3),
                    self.safe_number(ohlcv, 4),
                    self.safe_number(ohlcv, volumeIndex),  # base volume
                    self.safe_number(ohlcv, 7),  # quote volume
                    self.safe_integer(ohlcv, 8),  # is closed
                ]

        param = {"proxies": {"http": self._http_proxy, "https": self._https_proxy}}
        return OkxClient(param)
    
    def get(self, now: pd.Timestamp, **kwargs) -> pd.DataFrame:
        start = now - pd.Timedelta(self.freq) * (self.load_len + 1)
        start_ts = int(start.timestamp() * 1000)
        end_ts = int(now.timestamp() * 1000)

        symbol = "/".join(self.ticker.split("/")[::-1])
        since = start_ts
        candlestick = []
        while True:
            ohlcv = self._client.fetch_ohlcv(symbol, self.freq, since=since)
            candlestick.extend(ohlcv)
            if not ohlcv or candlestick[-1][0] >= end_ts:
                break
            since = candlestick[-1][0] + 1000

        df = pd.DataFrame(
            candlestick,
            columns=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "base_volume",
                "quote_volume",
                "is_closed",
            ],
        )
        df["open_time"] = pd.to_datetime(df["open_time"] // 1000, unit="s")
        df["close_time"] = pd.to_datetime(df["open_time"] + pd.Timedelta(self.freq), unit="s") - pd.Timedelta(1, unit="s")
        df["ticker"] = self.ticker
        df = df.sort_values(["ticker", "open_time"], ignore_index=True)
        if self.closed_only or self.mode == "backtest":
            df = df.loc[df["is_closed"] == 1]
            df = df.loc[df["close_time"] <= now]
        df.drop(columns="is_closed", inplace=True)
        return df.tail(self.load_len).reset_index(drop=True)
