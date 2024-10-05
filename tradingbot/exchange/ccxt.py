import functools

import tradingbot as tb
from tradingbot.exchange.core import Exchange
from tradingbot.model import Order


class CCXTExchange(Exchange):
    def __init__(self, name="binance", api_key: str = None, secret_key: str = None, **kwargs):
        config = tb.config
        self._name = name
        self._api_key = api_key or config.exchange.ccxt.api_key
        self._secret_key = secret_key or config.exchange.ccxt.secret_key

    @functools.cached_property
    def _client(self):
        import ccxt

        config = tb.config
        param = {
            "apiKey": self._api_key,
            "secret": self._secret_key,
            "proxies": {"http": config.general.http_proxy, "https": config.general.https_proxy},
        }
        return getattr(ccxt, self._name)(param)

    def handle(self, order: Order):
        pass
