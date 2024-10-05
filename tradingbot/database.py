import collections
import functools
import sqlalchemy as sa
import typing

import tradingbot as tb
import tradingbot.util as util
from tradingbot.data.core import Data


class DataBase:
    @staticmethod
    @functools.lru_cache(maxsize=1)
    def get_engine(url, **kwargs) -> sa.engine.Engine:
        return sa.create_engine(url, **kwargs)

    @staticmethod
    @functools.lru_cache(maxsize=128)
    def get_table_schema(cls: typing.Type[Data], name: str) -> sa.Table:
        engine = DataBase.get_engine(tb.config.general.db_url)
        metadata = sa.MetaData()

        columns = []
        for k, v in cls.field.items():
            primary_key = True if typing.get_origin(v) is typing.Annotated and "primary_key" in typing.get_args(v)[1:] else False
            dtype = typing.get_args(v)[0] if typing.get_origin(v) is typing.Annotated else v
            col = sa.Column(k, util.TYPE_MAPPING[dtype], primary_key=primary_key)
            columns.append(col)

        index = collections.defaultdict(list)
        for k, v in cls.field.items():
            if typing.get_origin(v) is typing.Annotated:
                for item in typing.get_args(v)[1:]:
                    if item.startswith("index"):
                        index[f"{item}_{name}"].append(k)

        table = sa.Table(name, metadata, *columns, *(sa.Index(k, *v) for k, v in index.items()))
        metadata.create_all(bind=engine, checkfirst=True)
        return table
