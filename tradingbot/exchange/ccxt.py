import functools

import tradingbot as tb
from tradingbot.exchange.core import Exchange
from tradingbot.model import Order


class CCXTExchange(Exchange):
    def __init__(self, name: str = None, **kwargs):
        config = tb.config
        self._name = name or config.exchange.ccxt.name
        self._param = {**tb.config.exchange.ccxt.model_dump(exclude="name"), **kwargs}

    @functools.cached_property
    def client(self):
        import ccxt

        config = tb.config
        http_proxy = self._param.pop("http_proxy", config.general.http_proxy)
        https_proxy = self._param.pop("https_proxy", config.general.https_proxy)
        param = {**self._param, "proxies": {"http": http_proxy, "https": https_proxy}}
        return getattr(ccxt, self._name)(param)

    def execute(self, order: Order):
        pass
