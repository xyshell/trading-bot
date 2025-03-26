import logging.config
import pathlib

from ._version import __version__
from .data.core import Data
from .strategy import Strategy
from .config import Config
from .position import Position
from .account import Account
from .order import Order
from .bot import Bot
from .trigger import schedule
from .reporter import Reporter
from .database import Database


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

config = Config()
if not config.general.log_dir:
    log_dir = pathlib.Path(__file__).parent / "logs"
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
    "config", "schedule", "Reporter", "Database", 
    "Account", "Account"
]
