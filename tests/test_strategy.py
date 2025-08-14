import tradingbot as tb
from tradingbot.balance import Balance
from tradingbot.exchange.core import FakeExchange
from tradingbot.order import Order
from tradingbot.trader import Trader

from . import assert_report


def test_dummy_limit_order_strategy(snapshot):

    class DummyLimitOrder(tb.Strategy):
        def __init__(self):
            super().__init__()
            self.trader = Trader(FakeExchange(commission=0.001))
            self.balance = Balance(USDT=10_000)
            self.data = {"candlestick_1h": tb.data.Candlestick("binance", ticker="USDT/BTC", freq="1h", load_len=35)}

        @tb.schedule([tb.trigger.StrategyFirstRun(), tb.trigger.StandardInterval("1h")])
        def next(self):
            curr_prc = self.data["candlestick_1h"]["close"].iloc[-1]

            for order in self.order:
                if order.action.value == "buy" and order.param["price"] < curr_prc * 0.97:
                    self.trader.exchange.cancel(order)
                    self.balance.convert(0.5, "PCTG", "USDT", "BTC", trader=self.trader, method="limit", param={"price": curr_prc * 0.98})
                
            if not self.order:
                self.balance.convert(0.5, "PCTG", "USDT", "BTC", trader=self.trader, method="limit", param={"price": curr_prc * 0.98})

    bot = tb.Bot(mode="backtest", start="2024-09-01", end="2024-10-01")
    bot.add_strategy(DummyLimitOrder())
    bot.run()

    report = bot.strategy.report
    assert_report(report, snapshot)
    assert (report['order']['status'] == Order.Status.FILLED).sum() == len(report['transaction'])
