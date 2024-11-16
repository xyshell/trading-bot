import logging.config

from ._version import __version__
from .data import Data
from .strategy import Strategy
from .model import Config, Order, Position, MarginPosition, Account, MarginAccount
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
logging.config.dictConfig(config.logging)

__all__ = [
    "__version__", 
    "Data", 
    "Strategy", 
    "Order", 
    "Position", "MarginPosition", 
    "Bot", 
    "config", "schedule", "Reporter", "Database", 
    "Account", "MarginAccount"
]
