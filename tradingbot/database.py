import collections
import functools
import sqlalchemy as sa
import typing

import tradingbot as tb
import tradingbot.util as util
from tradingbot.data.core import Data


class Database:

    _engine = {}

    @staticmethod
    def get_engine(url: typing.Optional[str] = None, **kwargs) -> sa.engine.Engine:
        url = url or tb.config.general.db_url
        if url in Database._engine:
            return Database._engine[url]
        Database._engine[url] = sa.create_engine(url, **kwargs)
        return Database._engine[url]

    @staticmethod
    @functools.lru_cache(maxsize=128)
    def get_data_table(kls: typing.Type[Data], name: str, /, **kwargs) -> sa.Table:
        url = kwargs.pop("url", tb.config.general.db_url)
        engine = Database.get_engine(url, **kwargs)
        metadata = sa.MetaData()

        columns = []
        for k, v in kls.field.items():
            primary_key = True if typing.get_origin(v) is typing.Annotated and "primary_key" in typing.get_args(v)[1:] else False
            dtype = typing.get_args(v)[0] if typing.get_origin(v) is typing.Annotated else v
            col = sa.Column(k, util.TYPE_MAPPING[dtype], primary_key=primary_key)
            columns.append(col)

        index = collections.defaultdict(list)
        for k, v in kls.field.items():
            if typing.get_origin(v) is typing.Annotated:
                for item in typing.get_args(v)[1:]:
                    if item.startswith("index"):
                        index[f"{item}_{name}"].append(k)

        table = sa.Table(name, metadata, *columns, *(sa.Index(k, *v) for k, v in index.items()))
        metadata.create_all(bind=engine, checkfirst=True)
        return table

    @staticmethod
    @functools.lru_cache(maxsize=8)
    def get_opt_table(**kwargs) -> sa.Table:
        url = kwargs.pop("url", tb.config.general.db_url)
        engine = Database.get_engine(url, **kwargs)
        metadata = sa.MetaData()

        table = sa.Table(
            "opt_result",
            metadata,
            sa.Column("key", sa.String, primary_key=True),
            sa.Column("strategy", sa.String),
            sa.Column("stats", sa.JSON, nullable=False),
        )
        metadata.create_all(bind=engine, checkfirst=True)
        return table
