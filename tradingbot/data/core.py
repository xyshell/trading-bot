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

    def __new__(cls, source: str, *args, **kwargs) -> Self:
        return super().__new__(cls._registry[(cls, source)])

    def __init__(self, mode: ModeType = "backtest", load_len: int = 1000, **kwargs):
        self._mode = mode
        self.load_len = load_len
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
        df = self.load(now, **kwargs) if self.mode == "backtest" else pd.DataFrame()
        if self.mode in {"paper", "live"} or len(df) < self.load_len:
            logger.debug(f"len={len(df)}<{self.load_len}. fetching {self.__class__.__name__} for {now=}")
            df = self.get(now, **kwargs)
            thread = threading.Thread(target=self.set, args=(now, df), kwargs=kwargs, daemon=True)
            thread.start()

        for line in self.__class__.field:
            self.value[line] = df[line]
