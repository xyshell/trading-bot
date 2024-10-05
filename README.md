# TradingBot

Backtest, paper trading and live trading all in one place

## Installation

### For End Users

1. Find the [latest release](https://github.com/xyshell/trading-bot/releases) and download the whl file.

2. Pip install the whl

```bash
pip install trading_bot.whl
```

Note: Optionally install extra dependencies based on your usage.

```bash
pip install mplfinance  # for plot
pip install yfinance  # for Candlestick(source="yahoo")
pip install python-binance  # for Candlestick(source="binance")
pip install ccxt  # for CCXTExchange
```

### For Developers

1. Clone the repository

```bash
git clone https://github.com/xyshell/trading-bot
```

2. Pip install in editable mode

```bash
pip install -e .[dev]
```

## Quick Start

1. find out `config_example.toml` in `site-packages\tradingbot`, copy as `config.toml` (find out by `pip show trading-bot`), and edit the config as needed.

```powershell
cd C:\anaconda3\envs\py3.12\Lib\site-packages\tradingbot
cp ./config_example.toml ./config.toml
```

2. Run demo examples under `/example`

- `demo_backtest_msft.ipynb`: backtest MSFT using yahoo finance price data
- `demo_backtest_btcusdt.ipynb`: backtest BTCUSDT using binance price data 

3. Get result

| **Metric**              | **Value**                                                |
| ----------------------- | -------------------------------------------------------- |
| Strategy                | SMACross({'ticker': 'USD/MSFT', 'fast': 10, 'slow': 30}) |
| Period                  | 2024-01-01 00:00:00 - 2024-10-01 00:00:00                |
| Exposure Time           | 49.45% x 274 days 00:00:00                               |
| Return Ann vs Benchmark | 12.61% vs 20.54%                                         |
| Vol Ann vs Benchmark    | 14.98% vs 19.46%                                         |
| Max Drawdown            | 9.33% (101 days 00:00:00)                                |
| Sharpe                  | 0.87                                                     |
| Sortino                 | 0.89                                                     |
| Calmar                  | 1.39                                                     |
| IR                      | -0.61                                                    |
| Trade #                 | 34                                                       |
| Win Rate                | 55.88%                                                   |
| Avg Win vs Lost Pct     | 1.67% vs -1.71%                                          |
| Avg Trade Duration      | 4 days 00:00:00                                          |
| Profit Factor           | 1.38                                                     |
| Expectancy              | 0.18%                                                    |
| SQN                     | 0.83                                                     |

![demo_backtest_msft](https://github.com/user-attachments/assets/605af263-b8e4-4c98-9ab2-a09733ea3f8b)

## Troubleshoot:

1. sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) unable to open database file

python may not have write access to your `site-packages\tradingbot`, edit `db_url` in `config.toml` to somewhere you have write acess to, e.g.:

```toml
[general]
db_url = "sqlite:///D:\\tradingbot.db" # override path to create local db
```
