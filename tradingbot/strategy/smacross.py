from .core import Strategy
from tradingbot.exchange import FakeExchange
from tradingbot.trigger import schedule, StrategyFirstRun, StandardInterval
from tradingbot.trader import Trader
from tradingbot.balance import Balance
from tradingbot.data import Candlestick


class SMACross(Strategy):
    param = {"coin": "BTC", "freq": "1h", "fast": 10, "slow": 30}

    def __init__(self):
        super().__init__()
        self.trader = Trader(FakeExchange(commission=0.001))
        self.balance = Balance(USDT=10_000)
        self.data = {
            "candlestick": Candlestick("binance", ticker=f"USDT/{self.param['coin']}", freq=self.param['freq'], load_len=self.param["slow"] + 5)
        }

    def start(self):  # function to be called at the startup
        self.logger.debug(f"{self.__class__.__name__} started with param: {self.param}")

    @schedule([StrategyFirstRun(), StandardInterval("1h")])  # when to trigger the function
    def next(self):  # function to be called when triggered
        close = self.data["candlestick"]["close"]  # get access to subscribed data from self.data['key']['field']
        pfast, pslow = self.param["fast"], self.param["slow"]  # get access to parameters from self.param

        # use your favorable way to compute indicators from a pd.Series
        sma_fast = close.rolling(window=pfast).mean()  
        sma_slow = close.rolling(window=pslow).mean()
        crossup = sma_fast.iloc[-2] < sma_slow.iloc[-2] and sma_fast.iloc[-1] >= sma_slow.iloc[-1]
        crossdown = sma_fast.iloc[-2] > sma_slow.iloc[-2] and sma_fast.iloc[-1] <= sma_slow.iloc[-1]

        # store any information for later use, e.g. plotting
        self.store = {
            "sma_fast": sma_fast.iloc[-1],
            "sma_slow": sma_slow.iloc[-1],
            "crossup": crossup,
            "crossdown": crossdown,
        }

        if crossup:
            self.logger.debug(f"SMA crossed up, buy at {close.iloc[-1]:.2f} 🟢🟢🟢")
            self.balance.convert(1.0, "PCTG", "USDT", self.param["coin"], trader=self.trader)  # convert [100] [percentage] of [USDT] to [BTC]
           
            # quantity instead of percentage
            # self.balance.convert(50, "QTY", "USDT", self.param["coin"], trader=self.trader)  # convert [50] [USDT] to [BTC]

            # split into 5 market orders, delay 60s between each order
            # self.balance.convert(1.0, "USDT", self.param["coin"], trader=self.trader, method="market", param={"n": 5, "delay": 60})

            # place a limit order at 80_000, wait for 300s, if not filled, split into 5 market orders with 60s delay in between 
            # self.balance.convert(1.0, "USDT", self.param["coin"], trader=self.trader, method="limit2market", param={"price": 80_000, "wait": 300, "n": 5, "delay": 60})

        elif crossdown:
            self.logger.debug(f"SMA crossed down, sell at {close.iloc[-1]:.2f} 🔴🔴🔴")
            self.balance.convert(1.0, "PCTG", self.param["coin"], "USDT", trader=self.trader)  # convert [100] [percentage] of [BTC] to [USDT]

    def stop(self):  # function to be called in the end
        self.logger.debug(f"{str(self)} stopped")




class SMACrossFuture(Strategy):
    param = {"coin": "BTC", "freq": "1h", "fast": 10, "slow": 30}

    def __init__(self):
        super().__init__()
        self.trader = Trader(FakeExchange(commission=0.001))
        self.balance = Balance(USDT=10_000)
        self.data = {
            "candlestick": Candlestick("binance", ticker=f"USDT/{self.param['coin']}:USDT", freq=self.freq, load_len=self.param["slow"] + 5)
        }

    @schedule([StrategyFirstRun(), StandardInterval("1h")])  # when to trigger the function
    def next(self):  # function to be called when triggered
        close = self.data["candlestick"]["close"]  # get access to subscribed data from self.data['key']['field']
        pfast, pslow = self.param["fast"], self.param["slow"]  # get access to parameters from self.param

        # use your favorable way to compute indicators from a pd.Series
        sma_fast = close.rolling(window=pfast).mean()  
        sma_slow = close.rolling(window=pslow).mean()
        crossup = sma_fast.iloc[-2] < sma_slow.iloc[-2] and sma_fast.iloc[-1] >= sma_slow.iloc[-1]
        crossdown = sma_fast.iloc[-2] > sma_slow.iloc[-2] and sma_fast.iloc[-1] <= sma_slow.iloc[-1]

        # store any information for later use, e.g. plotting
        self.store = {
            "sma_fast": sma_fast.iloc[-1],
            "sma_slow": sma_slow.iloc[-1],
            "crossup": crossup,
            "crossdown": crossdown,
        }

        if crossup:
            self.logger.debug(f"SMA crossed up, close short and open long at {close.iloc[-1]:.2f} 🟢🟢🟢")
            self.balance.target(
                0.0, "PCTG", "SHORT", f"USDT/{self.param['coin']}:USDT", trader=self.trader
            )  # target [0] [percentage] of [short] position of contract [USDT/BTC:USDT]
            self.balance.target(
                1.0, "PCTG", "LONG", f"USDT/{self.param['coin']}:USDT", leverage=5, trader=self.trader
            )  # convert [100] [percentage] of [long] position of contract [USDT/BTC:USDT], with leverage x[5]
        elif crossdown:
            self.logger.debug(f"SMA crossed down, sell at {close.iloc[-1]:.2f} 🔴🔴🔴")
            self.balance.target(
                0.0, "PCTG", "LONG", f"USDT/{self.param['coin']}:USDT", trader=self.trader
            )  # target [0] [percentage] of [long] position of contract [USDT/BTC:USDT]
            self.balance.target(
                1.0, "PCTG", "SHORT", f"USDT/{self.param['coin']}:USDT", leverage=5, trader=self.trader
            )  # target [100] [percentage] of [short] position of contract [USDT/BTC:USDT], with leverage x[5]


if __name__ == "__main__":
    import tradingbot as tb
    
    # step 1: initialize a bot
    bot = tb.Bot(mode="backtest", start="2024-09-01", end="2024-10-01")  # backtest
    # bot = tb.Bot(mode="paper")  # paper
    # bot = tb.Bot(mode="live")  # live

    # step 2: add strategy
    bot.add_strategy(SMACross(ticker="USDT/BTC", capital=10))

    # step 3: run the bot
    bot.run()
