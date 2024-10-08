import logging
from typing import Sequence

import tradingbot as tb
import tradingbot.util as util


class _SMACross(tb.Strategy):
    param = {"ticker": "USDT/BTC", "fast": 10, "slow": 20}

    def start(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"{self.__class__.__name__} started with param: {self.param}")

    @tb.schedule([tb.trigger.StrategyFirstRun(), tb.trigger.StandardInterval("1h")])
    def next(self, context: dict) -> tb.Order | Sequence[tb.Order] | None:
        """
        Args:
            context (dict):
                "trigger": list[Trigger], reason of this run
                "pending_orders": list[Order], if any pending orders
        """
        self.sma_fast = self.data["candlestick_1h"]["close"].rolling(window=self.param["fast"]).mean()
        self.sma_slow = self.data["candlestick_1h"]["close"].rolling(window=self.param["slow"]).mean()
        crossup = self.sma_fast.iloc[-2] < self.sma_slow.iloc[-2] and self.sma_fast.iloc[-1] >= self.sma_slow.iloc[-1]
        crossdown = self.sma_fast.iloc[-2] > self.sma_slow.iloc[-2] and self.sma_fast.iloc[-1] <= self.sma_slow.iloc[-1]
        ticker = self.param["ticker"]
        curr_prc = self.data["candlestick_1h"]["close"].iloc[-1]

        if crossup:
            self.logger.info(f"SMA crossed up, buy at {curr_prc:.2f}")
            order = tb.Order(action="BUY", ticker=ticker, size_type="PCTG", size=1.0, type="MARKET")
        elif crossdown:
            self.logger.info(f"SMA crossed down, sell at {curr_prc:.2f}")
            order = tb.Order(action="SELL", ticker=ticker, size_type="PCTG", size=1.0, type="MARKET")
        else:
            order = None

        return order

    def stop(self):
        final_nav = self.report["portfolio"]["nav"].iloc[-1]
        self.logger.info(f"Strategy stopped, final NAV={final_nav}")


class TestBacktest:
    def test_btcusdt(self, snapshot):
        # fmt: off
        bot = tb.Bot(
            mode="backtest",  # or "paper" or "live"
            start="2024-01-01", end="2024-01-10",  # for backtest mode
        )
        # fmt: on
        bot.data = {
            # subscribe to USDT/BTC 1h OHLCV from binance
            "candlestick_1h": tb.data.Candlestick("binance", ticker="USDT/BTC", freq="1h", load_len=35)
        }
        bot.strategy = _SMACross(ticker="USDT/BTC", fast=10, slow=30)
        bot.exchange = tb.exchange.FakeSpotExchange(commission=0.001)
        bot.account = {"USDT": 1000}
        bot.run()

        assert util.hash_pd(bot.strategy.report["stats"].drop("strategy")) == snapshot
        assert util.hash_pd(bot.strategy.report["portfolio"]["nav"]) == snapshot

    def test_msft(self, snapshot):
        class _SMACross(tb.Strategy):
            param = {"ticker": "USD/MSFT", "fast": 10, "slow": 20}

            def start(self):
                self.logger = logging.getLogger(__name__)
                self.logger.info(f"{self.__class__.__name__} started with param: {self.param}")

            @tb.schedule([tb.trigger.StrategyFirstRun(), tb.trigger.StandardInterval("1d")])
            def next(self, context: dict) -> tb.Order | Sequence[tb.Order] | None:
                """
                Args:
                    context (dict):
                        "trigger": list[Trigger], reason of this run
                        "pending_orders": list[Order], if any pending orders
                """
                self.sma_fast = self.data["candlestick_1h"]["close"].rolling(window=self.param["fast"]).mean()
                self.sma_slow = self.data["candlestick_1h"]["close"].rolling(window=self.param["slow"]).mean()
                crossup = self.sma_fast.iloc[-2] < self.sma_slow.iloc[-2] and self.sma_fast.iloc[-1] >= self.sma_slow.iloc[-1]
                crossdown = self.sma_fast.iloc[-2] > self.sma_slow.iloc[-2] and self.sma_fast.iloc[-1] <= self.sma_slow.iloc[-1]
                ticker = self.param["ticker"]
                curr_prc = self.data["candlestick_1h"]["close"].iloc[-1]

                if crossup:
                    self.logger.info(f"SMA crossed up, buy at {curr_prc:.2f}")
                    order = tb.Order(action="BUY", ticker=ticker, size_type="PCTG", size=1.0, type="MARKET")
                elif crossdown:
                    self.logger.info(f"SMA crossed down, sell at {curr_prc:.2f}")
                    order = tb.Order(action="SELL", ticker=ticker, size_type="PCTG", size=1.0, type="MARKET")
                else:
                    order = None

                return order

            def stop(self):
                final_nav = self.report["portfolio"]["nav"].iloc[-1]
                self.logger.info(f"Strategy stopped, final NAV={final_nav}")

        # fmt: off
        bot = tb.Bot(
            mode="backtest",  # or "paper" or "live"
            start="2024-01-01", end="2024-10-01",  # for backtest mode
        )
        # fmt: on
        bot.data = {
            # subscribe to USD/MSFT 1h OHLCV from yahoo
            "candlestick_1h": tb.data.Candlestick("yahoo", ticker="USD/MSFT", freq="1d", load_len=35)
        }
        bot.strategy = _SMACross(ticker="USD/MSFT", fast=10, slow=30)
        bot.exchange = tb.exchange.FakeSpotExchange(commission=0.001)
        bot.account = {"USD": 1000}
        bot.run()

        assert util.hash_pd(bot.strategy.report["stats"].drop("strategy")) == snapshot
        assert util.hash_pd(bot.strategy.report["portfolio"]["nav"]) == snapshot

    def test_closed_only(self, snapshot):
        class _SMACross(tb.Strategy):
            param = {"ticker": "USDT/BTC", "fast": 10, "slow": 20}

            def start(self):
                self.logger = logging.getLogger(__name__)
                self.logger.info(f"{self.__class__.__name__} started with param: {self.param}")

            @tb.schedule([tb.trigger.StandardInterval("1h")])
            def next(self, context: dict) -> tb.Order | Sequence[tb.Order] | None:
                """
                Args:
                    context (dict):
                        "trigger": list[Trigger], reason of this run
                        "pending_orders": list[Order], if any pending orders
                """
                self.sma_fast = self.data["candlestick_1h"]["close"].rolling(window=self.param["fast"]).mean()
                self.sma_slow = self.data["candlestick_1h"]["close"].rolling(window=self.param["slow"]).mean()
                crossup = self.sma_fast.iloc[-2] < self.sma_slow.iloc[-2] and self.sma_fast.iloc[-1] >= self.sma_slow.iloc[-1]
                crossdown = self.sma_fast.iloc[-2] > self.sma_slow.iloc[-2] and self.sma_fast.iloc[-1] <= self.sma_slow.iloc[-1]
                ticker = self.param["ticker"]
                curr_prc = self.data["candlestick_1h"]["close"].iloc[-1]

                if crossup:
                    self.logger.info(f"SMA crossed up, buy at {curr_prc:.2f}")
                    order = tb.Order(action="BUY", ticker=ticker, size_type="PCTG", size=1.0, type="MARKET")
                elif crossdown:
                    self.logger.info(f"SMA crossed down, sell at {curr_prc:.2f}")
                    order = tb.Order(action="SELL", ticker=ticker, size_type="PCTG", size=1.0, type="MARKET")
                else:
                    order = None

                return order

            def stop(self):
                final_nav = self.report["portfolio"]["nav"].iloc[-1]
                self.logger.info(f"Strategy stopped, final NAV={final_nav}")

        # fmt: off
        bot = tb.Bot(
            mode="backtest",
            start="2024-01-01", end="2024-01-10",
        )
        # fmt: on
        bot.data = {
            "candlestick_1h": tb.data.Candlestick("binance", ticker="USDT/BTC", freq="1h", load_len=35),
            "candlestick_4h": tb.data.Candlestick("binance", ticker="USDT/BTC", freq="4h", load_len=35, closed_only=False),
        }
        bot.strategy = _SMACross(ticker="USDT/BTC", fast=10, slow=30)
        bot.exchange = tb.exchange.FakeSpotExchange(commission=0.001)
        bot.account = {"USDT": 1000}
        bot.run()

        assert util.hash_pd(bot.strategy.report["stats"].drop("strategy")) == snapshot
        assert util.hash_pd(bot.strategy.report["portfolio"]["nav"]) == snapshot

    def test_optimize(self, snapshot):
        bot = tb.Bot(mode="backtest", start="2024-01-01", end="2024-01-10")
        bot.data = {"candlestick_1h": tb.data.Candlestick("binance", ticker="USDT/BTC", freq="1h", load_len=35)}
        bot.exchange = tb.exchange.FakeSpotExchange(commission=0.001)
        bot.account = {"USDT": 1000}
        bot.optimize({f"SMACross_{p1}": _SMACross(slow=p1) for p1 in [25, 30, 35]}, plot=False)

        for strat in bot.strategy.values():
            assert util.hash_pd(strat.report["stats"].drop("strategy")) == snapshot


# def test_holistic_input():
#     class DummyStrategy(tb.Strategy):
#         param = {}

#         def next(self, context: dict):
#             pass

#     # fmt: off
#     bot = tb.Bot(
#         mode="backtest",  # or "paper" or "live"
#         start="2024-01-01", end="2024-02-01",  # for backtest mode
#         data={
#             "candlestick_1h": tb.data.Candlestick("binance", ticker="USDT/BTC", freq="1h"),
#         },
#         strategy=DummyStrategy(),
#         exchange=tb.exchange.FakeSpotExchange(commission=0.001),
#         account={"USDT": 1000},
#     )
#     # fmt: on

#     assert bot.data
#     assert bot.strategy
#     assert bot.exchange
#     assert bot.account
