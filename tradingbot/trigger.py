import abc
import collections
import functools
import itertools
from typing import Self

import pandas as pd


from tradingbot.model import TimedeltaType
import tradingbot.util as util


class Trigger(abc.ABC):
    def __init__(self) -> None:
        self.checked = collections.deque()

    def __eq__(self, other: Self) -> bool:
        return self.__class__ is other.__class__

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"

    @abc.abstractmethod
    def check(self, now: pd.Timestamp) -> bool:
        pass


class StrategyFirstRun(Trigger):
    def check(self, now: pd.Timestamp) -> bool:
        if not self.checked:
            self.checked.append(now)
            return True
        return False


class StandardInterval(Trigger):
    @util.validate
    def __init__(self, interval: TimedeltaType):
        super().__init__()
        self.interval = interval

    def __eq__(self, other: Trigger) -> bool:
        return isinstance(other, StandardInterval) and self.interval == other.interval

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}('{self.interval}')"

    def check(self, now: pd.Timestamp) -> bool:
        if not self.checked:
            self.checked.append(now)
            return now.ceil(self.interval) == now
        next_check = self.checked[-1].ceil(self.interval)
        if next_check <= now:
            self.checked.append(now)
            return True
        return False


@util.validate
def schedule(trigger: list[Trigger]):
    for x, y in itertools.combinations(trigger, 2):
        assert x != y, f"Duplicated triggers: {x} and {y}"

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper.trigger = trigger
        return wrapper

    return decorator
