import logging.config
import pathlib

from ._version import __version__
from .data.core import Data
from .strategy import Strategy
from .config import get_config
from .position import Position
from .balance import Balance
from .order import Order
from .bot import Bot
from .trigger import schedule
from .reporter import Reporter
from .database import Database
from .trader import Trader
from .exchange import FakeExchange, CCXTExchange


def _print_version():
    box_width = 100
    version_text = f"TradingBot Version: '{__version__}'"

    padding_left = (box_width - len(version_text)) // 2
    padding_right = box_width - len(version_text) - padding_left

    print("╔" + "═" * box_width + "╗")
    # print(f"║{' ' * box_width}║")
    print(f"║{' ' * padding_left}{version_text}{' ' * padding_right}║")
    # print(f"║{' ' * box_width}║")
    print("╚" + "═" * box_width + "╝")

_print_version()

config = get_config()
log_dir = pathlib.Path(config.general.log_dir or pathlib.Path(__file__).parent / "log")
log_dir.mkdir(exist_ok=True)
for key, value in config.logging.handlers.items():
    if "filename" in value:
        value["filename"] = log_dir / value["filename"]
logging.config.dictConfig(config.logging)

__all__ = [
    "__version__", 
    "Data", 
    "Strategy", 
    "Order", 
    "Position", "MarginPosition", 
    "Bot", 
    "get_config",
    "schedule", "Reporter", "Database", 
    "Balance",
    "Trader",
    "FakeExchange", "CCXTExchange",
]
