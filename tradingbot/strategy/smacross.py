import logging

from .core import Strategy
from ..trigger import schedule, StrategyFirstRun, StandardInterval
from ..order import Order


class SMACross(Strategy):
    param = {"ticker": "USDT/BTC", "fast": 10, "slow": 20}  # default strategy param

    def start(self):  # function to be called at the startup
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"{self.__class__.__name__} started with param: {self.param}")

    @schedule([StrategyFirstRun(), StandardInterval("1h")])  # when to trigger the function
    def next(self, context: dict) -> Order | list[Order] | None:  # function to be called when triggered
        """
        Args:
            context (dict):
                "now": pd.Timestamp, current time
                "trigger": list[Trigger], reason of this run
                "open_order": list[Order], any open orders
        """
        close = self.data["candlestick_1h"]["close"]  # get access to subscribed data from self.data['key']['field']
        ticker, pfast, pslow = self.param["ticker"], self.param["fast"], self.param["slow"]  # get access to parameters from self.param

        # use your favorable way to compute indicators from a pd.Series
        self.sma_fast = close.rolling(window=pfast).mean()  
        self.sma_slow = close.rolling(window=pslow).mean()
        crossup = self.sma_fast.iloc[-2] < self.sma_slow.iloc[-2] and self.sma_fast.iloc[-1] >= self.sma_slow.iloc[-1]
        crossdown = self.sma_fast.iloc[-2] > self.sma_slow.iloc[-2] and self.sma_fast.iloc[-1] <= self.sma_slow.iloc[-1]
        curr_prc = close.iloc[-1]

        if crossup:
            self.logger.info(f"SMA crossed up, buy at {curr_prc:.2f} 🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢")
            order = Order(action="BUY", ticker=ticker, size_type="PCTG", size=1.0, type="MARKET")  # create an all-in market order
        elif crossdown:
            self.logger.info(f"SMA crossed down, sell at {curr_prc:.2f} 🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴")
            order = Order(action="SELL", ticker=ticker, size_type="PCTG", size=1.0, type="MARKET")
        else:
            order = None

        return order

    def stop(self):  # function to be called in the end
        self.logger.info(f"{self.__class__.__name__} stopped")

if __name__ == "__main__":
    import tradingbot as tb
    
    # fmt: off
    bot = tb.Bot( # init a bot
        mode="backtest",  # or "live"
        start="2024-09-01", end="2024-10-01",  # for backtest mode only
    )
    bot.data = { # subscribe to data 
        # subscribe to USDT/BTC 1h OHLCV from binance
        "candlestick_1h": tb.data.Candlestick("binance", ticker="USDT/BTC", freq="1h", load_len=35)
    }
    bot.strategy = SMACross(ticker="USDT/BTC", fast=10, slow=30)  # define strategy with param
    bot.exchange = tb.exchange.FakeSpotExchange(commission=0.001)  # plug in exchange
    bot.account = {"USDT": 10_000}  # init from cash
    bot.run(plot=True)  # run the bot