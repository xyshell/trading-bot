import math
import types
import numpy as np
import pandas as pd

import tradingbot.util as util
from tradingbot.strategy import Strategy
from tradingbot.model import Order, Transaction


class Reporter:
    @staticmethod
    def get_position_report(strategy: Strategy) -> pd.DataFrame:
        if not strategy.account_history:
            return pd.DataFrame()
        position_report = {}
        for timestamp, account in strategy.account_history.items():
            position_report[timestamp] = pd.concat(
                {pos.ticker: pd.Series(pos.model_dump(exclude="ticker")) for pos in account.position}
            )
        position_report = pd.concat(position_report).unstack()
        position_report.index.rename(["timestamp", "ticker"], inplace=True)
        position_report.rename(columns={"prc": "entry_prc"}, inplace=True)
        return position_report

    @staticmethod
    def get_portfolio_report(strategy: Strategy) -> pd.DataFrame:
        position_report = strategy.report["position"] if "position" in strategy.report else Reporter.get_position_report(strategy)
        if position_report.empty:
            return pd.DataFrame()
        cash_component = (
            position_report.loc[position_report["market_val"].isna(), "qty"].groupby(["timestamp", "ticker"]).sum().unstack()
        )
        asset_component = (
            position_report.loc[position_report["market_val"].notna(), "market_val"].groupby(["timestamp", "ticker"]).sum().unstack()
        )
        portfolio_report = pd.concat([cash_component, asset_component], axis=1).fillna(0.0)
        portfolio_report.insert(0, "nav", portfolio_report.sum(axis=1))
        return portfolio_report

    @staticmethod
    def get_transaction_report(strategy: Strategy) -> pd.DataFrame:
        if not strategy.transaction_history:
            field = Transaction.model_fields.copy()
            del field["from_"], field["to_"], field["tcost"]
            return pd.DataFrame(columns=list(field) + ["from_ticker", "from_qty", "to_ticker", "to_qty", "tcost_ticker", "tcost_qty"])
        transaction_report = pd.concat(
            {trans.timestamp: pd.Series(trans.model_dump(exclude="timestamp")) for trans in strategy.transaction_history}
        ).unstack()
        transaction_report[["from_ticker", "from_qty"]] = pd.DataFrame(
            transaction_report["from_"].tolist(), index=transaction_report.index
        )
        transaction_report[["to_ticker", "to_qty"]] = pd.DataFrame(transaction_report["to_"].tolist(), index=transaction_report.index)
        transaction_report[["tcost_ticker", "tcost_qty"]] = pd.DataFrame(
            transaction_report["tcost"].tolist(), index=transaction_report.index
        )
        transaction_report.drop(columns=["from_", "to_", "tcost"], inplace=True)
        return transaction_report

    @staticmethod
    def get_order_report(strategy: Strategy) -> pd.DataFrame:
        if not strategy.order_history:
            return pd.DataFrame(columns=Order.model_fields)
        order_report = pd.concat(
            {timestamp: pd.Series(order.model_dump(mode="json")) for timestamp, order in strategy.order_history.items()}
        ).unstack()
        return order_report

    @staticmethod
    def get_trade_report(strategy: Strategy) -> pd.DataFrame:
        ptf_report = strategy.report["portfolio"]
        _ptf_hist_ret = ptf_report.nav.pct_change()
        _is_exposed = _ptf_hist_ret.fillna(0.0) != 0.0
        _is_exposed_chg = _is_exposed.astype(int).diff()
        trade_start = _is_exposed_chg.index[_is_exposed_chg == 1]
        trade_end = _is_exposed_chg.index[_is_exposed_chg == -1]
        if (trade_start[-1] > trade_end[-1]) if len(trade_end) > 0 else True:
            trade_end = trade_end.append(pd.Index([_is_exposed.index[-1]]))
        trade_report = pd.concat([pd.Series(trade_start, name="entry_time"), pd.Series(trade_end, name="exit_time")], axis=1)
        trade_report["duration"] = trade_report["exit_time"] - trade_report["entry_time"]
        trade_report = trade_report.merge(ptf_report.nav.rename("entry_nav"), left_on="entry_time", right_index=True, how="left")
        trade_report = trade_report.merge(ptf_report.nav.rename("exit_nav"), left_on="exit_time", right_index=True, how="left")
        trade_report["pnl_abs"] = trade_report["exit_nav"] - trade_report["entry_nav"]
        trade_report["pnl_pct"] = trade_report["pnl_abs"] / trade_report["entry_nav"]
        return trade_report

    @staticmethod
    def get_stats_report(strategy: Strategy) -> pd.Series:
        _ptf_report = strategy.report["portfolio"] if "portfolio" in strategy.report else Reporter.get_portfolio_report(strategy)
        _trade_report = strategy.report["trade"] if "trade" in strategy.report else Reporter.get_trade_report(strategy)

        _freq = util.inferred_freq2freq(_ptf_report.index.inferred_freq)
        start = _ptf_report.index[0]
        end = _ptf_report.index[-1]
        duration = end - start
        _n = pd.Timedelta("365 days") / duration
        _N = pd.Timedelta("365 days") / pd.Timedelta(_freq)
        # portfolio
        _ptf_hist_ret = _ptf_report.nav.pct_change()
        _is_exposed = _ptf_hist_ret.fillna(0.0) != 0.0
        exposure_time = _is_exposed.sum() / len(_is_exposed)
        ptf_ret = _ptf_report.nav.iloc[-1] / _ptf_report.nav.iloc[0] - 1
        ptf_ret_peak = _ptf_report.nav.max() / _ptf_report.nav.iloc[0] - 1
        ptf_ret_ann = (1 + ptf_ret) ** _n - 1
        ptf_vol_ann = _ptf_hist_ret.std() * _N**0.5
        # benchmark
        _bmk_data = next((data for data in strategy.data.values() if data.freq == _freq), None)
        _bmk_data = _bmk_data or next(iter(strategy.data.ticker2candle.values()))
        _len_mul = pd.Timedelta(_freq) / pd.Timedelta(_bmk_data.freq)
        _bmk_df = _bmk_data.load(end, load_len=math.ceil(len(_ptf_report) * _len_mul))
        _bmk_close = _bmk_df.set_index("close_time").close.reindex(_ptf_hist_ret.index, method="ffill")
        _bmk_hist_ret = _bmk_close.pct_change()
        bmk_ret = _bmk_close.iloc[-1] / _bmk_close.iloc[0] - 1
        bmk_ret_ann = (1 + bmk_ret) ** _n - 1
        bmk_vol_ann = _bmk_hist_ret.std() * _N**0.5
        # kpi
        _ptf_hist_ret_mean = _ptf_hist_ret.mean()
        sharpe = _ptf_hist_ret_mean * _N / ptf_vol_ann
        _act_hist_ret = _ptf_hist_ret - _bmk_hist_ret
        _act_vol_ann = _act_hist_ret.std() * _N**0.5
        ir = _act_hist_ret.mean() * _N / _act_vol_ann
        _downsize_vol_ann = _ptf_hist_ret[_ptf_hist_ret < 0].std() * _N**0.5
        sortino = _ptf_hist_ret_mean * _N / _downsize_vol_ann
        # max drawdown
        _drawdown = _ptf_report.nav / _ptf_report.nav.expanding(min_periods=1).max() - 1
        max_drawdown = abs(_drawdown.min())
        _in_drawdown = _drawdown < 0
        _in_drawdown_chg = _in_drawdown.astype(int).diff()
        _drawdown_start = _in_drawdown.index[_in_drawdown_chg == 1]
        _drawdown_start = _in_drawdown.index[-1:] if len(_drawdown_start) == 0 else _drawdown_start
        _drawdown_end = _in_drawdown.index[_in_drawdown_chg == -1]
        if (_drawdown_start[-1] > _drawdown_end[-1]) if len(_drawdown_end) > 0 else True:
            _drawdown_end = _drawdown_end.append(pd.Index([_drawdown.index[-1]]))
        _drawdown_period = _drawdown_end - _drawdown_start
        max_drawdown_period = _drawdown_period.max()
        _max_drawdown_loc = np.argmax(_drawdown_period == max_drawdown_period)
        max_drawdown_start = _drawdown_start[_max_drawdown_loc]
        max_drawdown_end = _drawdown_end[_max_drawdown_loc]
        calmar = _ptf_hist_ret_mean * _N / max_drawdown
        # trade
        trade_num = len(_trade_report)
        win_rate = (_trade_report["pnl_abs"] > 0).sum() / trade_num
        avg_win_pnl_pct = _trade_report.loc[_trade_report["pnl_abs"] > 0, "pnl_pct"].mean()
        avg_lose_pnl_pct = _trade_report.loc[_trade_report["pnl_abs"] < 0, "pnl_pct"].mean()
        avg_duration = _trade_report["duration"].mean()
        profit_factor = abs(
            _trade_report.loc[_trade_report["pnl_abs"] > 0, "pnl_abs"].sum()
            / _trade_report.loc[_trade_report["pnl_abs"] < 0, "pnl_abs"].sum()
        )
        expectancy = win_rate * avg_win_pnl_pct + (1 - win_rate) * avg_lose_pnl_pct
        sqn = (_trade_report["pnl_pct"].mean() / _trade_report["pnl_pct"].std()) * trade_num**0.5

        return pd.Series(
            {
                k: v
                for k, v in locals().items()
                if not k.startswith("_") and k != "globals" and not k[0].isupper() and not isinstance(v, types.ModuleType)
            }
        )

    @staticmethod
    def display(strategy: Strategy) -> None:
        stats_report = strategy.report["stats"] if "stats" in strategy.report else Reporter.get_stats_report(strategy)
        msg = pd.Series(
            {
                "Strategy": strategy,
                "Period": f"{stats_report['start']} - {stats_report['end']}",
                "Exposure Time": f"{stats_report['exposure_time']:.2%} x {stats_report['duration']}",
                "Return Ann vs Benchmark": f"{stats_report['ptf_ret_ann']:.2%} vs {stats_report['bmk_ret_ann']:.2%}",
                "Vol Ann vs Benchmark": f"{stats_report['ptf_vol_ann']:.2%} vs {stats_report['bmk_vol_ann']:.2%}",
                "Max Drawdown": f"{stats_report['max_drawdown']:.2%} ({stats_report['max_drawdown_period']})",
                "Sharpe": f"{stats_report['sharpe']:.2f}",
                "Sortino": f"{stats_report['sortino']:.2f}",
                "Calmar": f"{stats_report['calmar']:.2f}",
                "IR": f"{stats_report['ir']:.2f}",
                "Trade #": f"{stats_report['trade_num']}",
                "Win Rate": f"{stats_report['win_rate']:.2%}",
                "Avg Win vs Lost Pct": f"{stats_report['avg_win_pnl_pct']:.2%} vs {stats_report['avg_lose_pnl_pct']:.2%}",
                "Avg Trade Duration": stats_report["avg_duration"],
                "Profit Factor": f"{stats_report['profit_factor']:.2f}",
                "Expectancy": f"{stats_report['expectancy']:.2%}",
                "SQN": f"{stats_report['sqn']:.2f}",
            }
        )
        with pd.option_context("display.max_colwidth", None):
            print(msg)

    @classmethod
    def set(cls, strategy: Strategy) -> None:
        strategy.report["position"] = Reporter.get_position_report(strategy)
        strategy.report["portfolio"] = Reporter.get_portfolio_report(strategy)
        strategy.report["transaction"] = Reporter.get_transaction_report(strategy)
        strategy.report["order"] = Reporter.get_order_report(strategy)
        strategy.report["trade"] = Reporter.get_trade_report(strategy)
        strategy.report["stats"] = Reporter.get_stats_report(strategy)
