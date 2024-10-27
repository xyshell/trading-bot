import contextlib
import hashlib
import logging
from logging.handlers import TimedRotatingFileHandler
import pathlib
import time
import types
import functools
import sqlalchemy as sa
import pandas as pd

import pydantic

validate = pydantic.validate_call(config=dict(arbitrary_types_allowed=True))


TYPE_MAPPING = {float: sa.Float, int: sa.Integer, str: sa.String, pd.Timestamp: sa.DateTime}


def utc_now_factory() -> pd.Timestamp:
    return pd.Timestamp.utcnow().tz_localize(None)


def dispatch(func):
    _registry = {}

    def register(
        key: tuple[str, str],  # key[1] is passed to the function as the first argument
    ):
        if key in _registry:
            raise KeyError(f"{key} is already registered in {func.__name__}._registry")

        def wrapper(func_):
            # if validate: func_ = validate(func_)
            _registry[key] = func_
            return func_

        return wrapper

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if len(args) < 2:
            raise TypeError(f"{func.__name__}() got invalid {args=} for retrieving 'key' in _registry")
        kls_name = args[0].__qualname__ if isinstance(args[0], type) else args[0].__class__.__qualname__
        key = (kls_name, args[1])
        return _registry[key](*args, **kwargs) if key in _registry else func(*args, **kwargs)

    wrapper.register = register
    wrapper._registry = types.MappingProxyType(_registry)
    return wrapper


def hash_pd(obj: pd.Index | pd.Series | pd.DataFrame, limit: int = 256) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(obj).to_numpy()).hexdigest()[:limit]


def to_list(obj):
    if obj is None:
        return []
    elif isinstance(obj, (list, tuple)):
        return obj
    else:
        return [obj]


def get_base_ticker(ticker: str) -> str:
    """USDT/BTC -> BTC"""
    return ticker.split("/")[1]


def get_quote_ticker(ticker: str) -> str:
    """USDT/BTC -> USDT"""
    return ticker.split("/")[0]


def convert(from_: tuple[str, float], ticker: str, prc: float) -> tuple[str, float]:
    """convert from one asset to another at a given price, assuming no tcost"""
    quote_ticker = get_quote_ticker(ticker)
    base_ticker = get_base_ticker(ticker)
    if from_[0] == quote_ticker:
        return (base_ticker, from_[1] / prc)
    elif from_[0] == base_ticker:
        return (quote_ticker, from_[1] * prc)
    else:
        raise ValueError(f"cannot convert {from_} with '{ticker}' at '{prc}'")


@contextlib.contextmanager
def set_level(logger, level):
    previous_level = logger.level
    logger.setLevel(level)
    try:
        yield
    finally:
        logger.setLevel(previous_level)


def inferred_freq2freq(inferred_freq: str) -> str:
    return f"1{inferred_freq}".lower() if not inferred_freq.startswith(tuple(str(i) for i in range(10))) else inferred_freq


class SlackHandler(logging.Handler):
    def __init__(self, bot_token: str, channel: str):
        super().__init__()

        from slack_sdk import WebClient

        self._client = WebClient(token=bot_token)
        self._channel = channel

    def emit(self, record):
        from slack_sdk.errors import SlackApiError

        msg = self.format(record)
        try:
            resp = self._client.chat_postMessage(channel=self._channel, text=msg)
        except SlackApiError as e:
            logging.getLogger(__name__).error(f"Slack API error: {e.response['error']}")
        else:
            logging.getLogger(__name__).info(f"Slack sent to channel='{resp['channel']}', {msg=}")


def get_strategy_logger(name: str) -> logging.Logger:
    from tradingbot import config

    logger = logging.getLogger(f"tradingbot.strategy.{name}")
    logger.setLevel(config.logging.loggers["tradingbot.strategy"]["level"])

    # logging to file
    log_dir = pathlib.Path(config.logging.handlers["file"]["filename"]).parent
    file_handler = logging.FileHandler(f"{log_dir / name}.log", mode="a", encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter(config.logging.formatters["standard"]["format"], config.logging.formatters["standard"]["datefmt"])
    )
    file_handler.setLevel(config.logging.handlers["file"]["level"])
    logger.addHandler(file_handler)

    # logging to slack
    if hasattr(config.notification, "slack"):
        slack_handler = SlackHandler(bot_token=config.notification.slack.bot_token, channel=config.notification.slack.channel)
        slack_handler.setFormatter(
            logging.Formatter(config.logging.formatters["concise"]["format"], config.logging.formatters["concise"]["datefmt"])
        )
        slack_handler.setLevel(logging.INFO)
        logger.addHandler(slack_handler)
    return logger


class CustomTimedRotatingFileHandler(TimedRotatingFileHandler):

    def doRollover(self):
        try:
            super().doRollover()
        except PermissionError:
            pass  # ignore "The process cannot access the file because it is being used by another process"


def timeit(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        tic = time.time()  # Start time
        result = func(*args, **kwargs)  # Execute the function
        toc = time.time()  # End time
        print(f"{func.__name__} took {(toc-tic):.2f} seconds.")
        return result
    return wrapper
