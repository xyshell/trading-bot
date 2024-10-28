import abc
import collections
import logging
import threading
from typing import Self
import typing

import pandas as pd

import tradingbot.util as util
from tradingbot.model import ModeType

logger = logging.getLogger(__name__)


class Data:
    _registry = {}

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        if cls.__base__ is not Data:
            assert isinstance(cls.source, str), "must implement class attribute 'source': str"
            key = (cls.__base__, cls.source)
            assert key not in Data._registry, f"source='{cls.source}' is already registered in '{cls.__base__.__name__}'"
            Data._registry[(cls.__base__, cls.source)] = cls
        elif issubclass(cls, Data):
            assert isinstance(cls.field, dict), "must implement class attribute 'field': dict"
            for k, v in cls.field.items():
                assert isinstance(k, str), "field key must be str"
                assert isinstance(v, type) or typing.get_origin(v) is typing.Annotated, "field value must be type or Annotated type"
            cls.pit = next(  # point-in-time := first pd.Timestamp field defined as part of "primary_key"
                (k for k, v in cls.field.items() if "primary_key" in typing.get_args(v) and typing.get_args(v)[0] is pd.Timestamp),
                None,
            )
            assert (
                cls.pit is not None
            ), f"can't find PIT (point-in-time) column in {cls.field=}. At least one column must be Annotated[pd.Timestamp, 'primary_key']"

    def __new__(cls, *args, **kwargs) -> Self:
        source = args[0] if args else cls.source
        kls = cls.__base__ if cls.__base__ is not Data else cls
        return super().__new__(kls._registry[(kls, source)])

    def __init__(self, mode: ModeType = "backtest", freq: str = "1s", load_len: int = 1000, preload: bool = False, **kwargs):
        """
        Args:
            mode (str): data fetching mode. "backtest" or "live"
            freq (str): update frequency, last update older than (now - freq) will be considered as stale and thus trigger update
            load_len (int): length of data to load
            preload (bool): when backtest, whether to preload data to speed up
        """
        self._mode = mode
        self.freq = freq
        self.load_len = load_len
        self._preload = preload
        self._cached = None

        self.value = collections.defaultdict(pd.Series)
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def frame(self) -> pd.DataFrame:
        return pd.concat({key: self[key] for key in self.field}, axis=1)

    def __repr__(self):
        return f"{self.__class__.__name__}(load_len={self.load_len}, field={list(self.field.keys())})\n{self.frame}"

    @property
    @abc.abstractmethod
    def table_name(self) -> str:
        pass

    @property
    def mode(self) -> ModeType:
        return self._mode

    @mode.setter
    @util.validate
    def mode(self, mode: ModeType):
        self._mode = mode

    @property
    def preload(self) -> bool:
        return self._preload
    
    @preload.setter
    @util.validate
    def preload(self, preload: bool):
        self._preload = preload

    @abc.abstractmethod
    def get(self, now: pd.Timestamp, **kwargs) -> pd.DataFrame:
        pass

    def load(self, now: pd.Timestamp, **kwargs) -> pd.DataFrame:
        """load from database for child class"""
        df = super(self.__class__, self).get(now, **kwargs)
        return df

    @abc.abstractmethod
    def set(self, now: pd.Timestamp, df: pd.DataFrame, **kwargs) -> None:
        pass

    def __getitem__(self, item: str):
        return self.value[item]

    def update(self, now: pd.Timestamp, **kwargs) -> None:
        if self.mode == "backtest" and self._preload:
            df = self._cached.loc[self._cached[self.pit] <= now].tail(self.load_len)
        elif self.mode == "backtest":
            df = self.load(now, **kwargs)
        else:  # live
            df = pd.DataFrame()

        if self.mode == "live" or len(df) < self.load_len or df[self.pit].iloc[-1] < (now - pd.Timedelta(self.freq)):
            logger.debug(f"Data Fetching {self.__class__.__name__} for {now=}")
            df = self.get(now, **kwargs)
            thread = threading.Thread(target=self.set, args=(now, df), kwargs=kwargs, daemon=True)
            thread.start()

        for line in self.__class__.field:
            self.value[line] = df[line]


class DataManager(dict):
    def __init__(self, *args, mode: ModeType, **kwargs):
        super().__init__(*args, **kwargs)
        self._mode = mode
        for data in self.values():
            data.mode = mode

        from tradingbot.data.candlestick import Candlestick

        self._candlestick_data = [data for data in self.values() if isinstance(data, Candlestick)]
        assert self._candlestick_data, "Data must contain at least one tb.data.Candlestick()"

    @property
    def ticker2candle(self) -> dict[str, Data]:
        ticker2min_freq = collections.defaultdict(lambda: pd.Timedelta.max)
        ticker2candle = {}  # reference ticker to the candlestick with highest frequency
        for data in self._candlestick_data:
            if pd.Timedelta(data.freq) < ticker2min_freq[data.ticker]:
                ticker2min_freq[data.ticker] = pd.Timedelta(data.freq)
                ticker2candle[data.ticker] = data
        return ticker2candle
