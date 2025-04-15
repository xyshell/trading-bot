from dataclasses import asdict
import math
import logging

import numpy as np
import pandas as pd

import tradingbot.util as util
from tradingbot.strategy import Strategy


logger = logging.getLogger(__name__)


class Reporter:

    @staticmethod
    def get_asset_report(strategy: Strategy) -> pd.DataFrame:
        if not strategy.balance_history:
            return pd.DataFrame()
        asset_report = {}
        for timestamp, balance in strategy.balance_history.items():
            asset_report[timestamp] = pd.Series(balance)
        asset_report = pd.concat(asset_report).unstack()
        asset_report.index.rename("timestamp", inplace=True)
        return asset_report.reset_index()

    @staticmethod
    def get_portfolio_report(strategy: Strategy) -> pd.DataFrame:
        asset_report = strategy.report["asset"] if "asset" in strategy.report else Reporter.get_asset_report(strategy)
        if asset_report.empty:
            return pd.DataFrame()
        evaluated_balance = pd.concat({ts: pd.Series(store["_evaluated_balance"]) for ts, store in strategy.store_history.items()})
        evaluated_balance.index.rename(["timestamp", "asset"], inplace=True)
        portfolio_report = evaluated_balance.groupby(["timestamp", "asset"]).sum().unstack().fillna(0.0).sum(axis=1)
        portfolio_report = portfolio_report.to_frame(f"NAV_{strategy.currency}")
        return portfolio_report.reset_index()

    @staticmethod
    def get_transaction_report(strategy: Strategy) -> pd.DataFrame:
        if not strategy.transaction_history:
            return pd.DataFrame()
        transaction_report = pd.DataFrame([
            pd.Series(asdict(trans)) for trans in strategy.transaction_history
        ])
        return transaction_report

    @staticmethod
    def get_order_report(strategy: Strategy) -> pd.DataFrame:
        if not strategy.order_history:
            return pd.DataFrame()

        order_report = pd.DataFrame(
            [order.model_dump() for order in strategy.order_history]
        )
        return order_report

    @staticmethod
    def get_trade_report(strategy: Strategy) -> pd.DataFrame:
        ptf_report = strategy.report["portfolio"] if "portfolio" in strategy.report else Reporter.get_portfolio_report(strategy)
        ptf_report = ptf_report.set_index("timestamp")
        nav_col = f"NAV_{strategy.currency}"
        ptf_hist_ret = ptf_report[nav_col].pct_change()
        is_exposed = ptf_hist_ret.fillna(0.0) != 0.0
        is_exposed_chg = is_exposed.astype(int).diff()
        trade_start = is_exposed_chg.index[is_exposed_chg == 1]
        trade_end = is_exposed_chg.index[is_exposed_chg == -1]
        if (trade_start[-1] > trade_end[-1]) if len(trade_end) > 0 else True:
            trade_end = trade_end.append(pd.Index([is_exposed.index[-1]]))
        trade_report = pd.concat([pd.Series(trade_start, name="entry_time"), pd.Series(trade_end, name="exit_time")], axis=1)
        trade_report["duration"] = trade_report["exit_time"] - trade_report["entry_time"]
        trade_report = trade_report.merge(ptf_report[nav_col].rename("entry_nav"), left_on="entry_time", right_index=True, how="left")
        trade_report = trade_report.merge(ptf_report[nav_col].rename("exit_nav"), left_on="exit_time", right_index=True, how="left")
        trade_report["pnl_abs"] = trade_report["exit_nav"] - trade_report["entry_nav"]
        trade_report["pnl_pct"] = trade_report["pnl_abs"] / trade_report["entry_nav"]
        return trade_report

    @staticmethod
    def get_summary_report(strategy: Strategy) -> pd.Series:
        ptf_report = strategy.report["portfolio"] if "portfolio" in strategy.report else Reporter.get_portfolio_report(strategy)
        trade_report = strategy.report["trade"] if "trade" in strategy.report else Reporter.get_trade_report(strategy)
        ptf_report = ptf_report.set_index("timestamp")
        nav_col = f"NAV_{strategy.currency}"

        freq = util.inferred_freq2freq(ptf_report.index.inferred_freq or next(iter(strategy.data.ticker2candle.values())).freq)
        start = ptf_report.index[0]
        end = ptf_report.index[-1]
        duration = end - start
        n = pd.Timedelta("365 days") / (duration or pd.NaT)
        N = pd.Timedelta("365 days") / pd.Timedelta(freq)
        # portfolio
        ptf_hist_ret = ptf_report[nav_col].pct_change()
        is_exposed = ptf_hist_ret.fillna(0.0) != 0.0
        exposure_time = is_exposed.sum() / len(is_exposed)
        ptf_ret = ptf_report[nav_col].iloc[-1] / ptf_report[nav_col].iloc[0] - 1
        ptf_ret_peak = ptf_report[nav_col].max() / ptf_report[nav_col].iloc[0] - 1
        ptf_ret_trough = ptf_report[nav_col].min() / ptf_report[nav_col].iloc[0] - 1
        ptf_ret_ann = (1 + ptf_ret) ** n - 1
        ptf_vol_ann = ptf_hist_ret.std() * N**0.5
        # benchmark
        bmk_data = next((data for data in strategy.data.values() if data.freq == freq), None)
        bmk_data = bmk_data or next(iter(strategy.data.ticker2candle.values()))
        len_mul = pd.Timedelta(freq) / pd.Timedelta(bmk_data.freq)
        bmk_df = bmk_data.load(end, load_len=math.ceil(len(ptf_report) * len_mul))
        bmk_close = bmk_df.set_index("close_time").close.reindex(ptf_hist_ret.index, method="ffill")
        bmk_hist_ret = bmk_close.pct_change()
        bmk_ret = bmk_close.iloc[-1] / bmk_close.iloc[0] - 1
        bmk_ret_ann = (1 + bmk_ret) ** n - 1
        bmk_vol_ann = bmk_hist_ret.std() * N**0.5
        # kpi
        ptf_hist_ret_mean = ptf_hist_ret.mean()
        ptf_sharpe = ptf_hist_ret_mean * N / ptf_vol_ann
        bmk_sharpe = bmk_hist_ret.mean() * N / bmk_vol_ann
        act_hist_ret = ptf_hist_ret - bmk_hist_ret
        act_vol_ann = act_hist_ret.std() * N**0.5
        ir = act_hist_ret.mean() * N / act_vol_ann
        downsize_vol_ann = ptf_hist_ret[ptf_hist_ret < 0].std() * N**0.5
        sortino = ptf_hist_ret_mean * N / downsize_vol_ann
        # max drawdown
        drawdown = ptf_report[nav_col] / ptf_report[nav_col].expanding(min_periods=1).max() - 1
        max_drawdown = abs(drawdown.min())
        in_drawdown = drawdown < 0
        in_drawdown_chg = in_drawdown.astype(int).diff()
        drawdown_start = in_drawdown.index[in_drawdown_chg == 1]
        drawdown_start = in_drawdown.index[-1:] if len(drawdown_start) == 0 else drawdown_start
        drawdown_end = in_drawdown.index[in_drawdown_chg == -1]
        if (drawdown_start[-1] > drawdown_end[-1]) if len(drawdown_end) > 0 else True:
            drawdown_end = drawdown_end.append(pd.Index([drawdown.index[-1]]))
        drawdown_period = drawdown_end - drawdown_start
        max_drawdown_period = drawdown_period.max()
        max_drawdown_loc = np.argmax(drawdown_period == max_drawdown_period)
        max_drawdown_start = drawdown_start[max_drawdown_loc]
        max_drawdown_end = drawdown_end[max_drawdown_loc]
        calmar = ptf_hist_ret_mean * N / max_drawdown
        # trade
        trade_num = len(trade_report)
        win_rate = (trade_report["pnl_abs"] > 0).sum() / trade_num
        best_trade = trade_report['pnl_pct'].max()
        worst_trade = trade_report['pnl_pct'].min()
        avg_win_pnl_pct = trade_report.loc[trade_report["pnl_abs"] > 0, "pnl_pct"].mean()
        avg_lose_pnl_pct = trade_report.loc[trade_report["pnl_abs"] < 0, "pnl_pct"].mean()
        avg_duration = trade_report["duration"].mean()
        profit_factor = abs(
            trade_report.loc[trade_report["pnl_abs"] > 0, "pnl_abs"].sum()
            / trade_report.loc[trade_report["pnl_abs"] < 0, "pnl_abs"].sum()
        )
        expectancy = win_rate * avg_win_pnl_pct + (1 - win_rate) * avg_lose_pnl_pct
        sqn = (trade_report["pnl_pct"].mean() / trade_report["pnl_pct"].std()) * trade_num**0.5

        return pd.Series({
            "start": ptf_report.index[0],
            "end": ptf_report.index[-1],
            "exposure_time": exposure_time,
            "duration": duration,
            "ptf_ret": ptf_ret,
            "bmk_ret": bmk_ret,
            "ptf_ret_peak": ptf_ret_peak,
            "ptf_ret_trough": ptf_ret_trough,
            "ptf_ret_ann": ptf_ret_ann,
            "bmk_ret_ann": bmk_ret_ann,
            "ptf_vol_ann": ptf_vol_ann,
            "bmk_vol_ann": bmk_vol_ann,
            "ptf_sharpe": ptf_sharpe,
            "bmk_sharpe": bmk_sharpe,
            "sortino": sortino,
            "ir": ir,
            "max_drawdown": max_drawdown,
            "max_drawdown_period": max_drawdown_period,
            "max_drawdown_start": max_drawdown_start,
            "max_drawdown_end": max_drawdown_end,
            "calmar": calmar,
            "trade_num": trade_num,
            "win_rate": win_rate,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "avg_win_pnl_pct": avg_win_pnl_pct,
            "avg_lose_pnl_pct": avg_lose_pnl_pct,
            "avg_duration": avg_duration,
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "sqn": sqn
        })

    @staticmethod
    def get_store_report(strategy: Strategy) -> pd.DataFrame:
        store_report = pd.concat({ts: pd.Series({k: v for k, v in store.items() if not k.startswith("_")}) for ts, store in strategy.store_history.items()})
        store_report = store_report.unstack(level=-1)
        store_report.index.rename("timestamp", inplace=True)
        return store_report

    @staticmethod
    def get_display_report(strategy: Strategy) -> pd.Series:
        summary_report = strategy.report["summary"] if "summary" in strategy.report else Reporter.get_summary_report(strategy)
        if summary_report.empty:
            return pd.Series()
        
        display_report = pd.Series(
            {
                "Strategy": strategy,
                "Period": f"{summary_report['start']} - {summary_report['end']}",
                "Exposure Time": f"{summary_report['exposure_time']:.2%} x {summary_report['duration']}",
                "Return Ann vs Benchmark": f"{summary_report['ptf_ret_ann']:.2%} vs {summary_report['bmk_ret_ann']:.2%}",
                "Vol Ann vs Benchmark": f"{summary_report['ptf_vol_ann']:.2%} vs {summary_report['bmk_vol_ann']:.2%}",
                "Max Drawdown": f"{summary_report['max_drawdown']:.2%} ({summary_report['max_drawdown_period']})",
                "Sharpe": f"{summary_report['ptf_sharpe']:.2f} vs {summary_report['bmk_sharpe']:.2f}",
                "Sortino": f"{summary_report['sortino']:.2f}",
                "Calmar": f"{summary_report['calmar']:.2f}",
                "IR": f"{summary_report['ir']:.2f}",
                "Trade #": f"{summary_report['trade_num']}",
                "Win Rate": f"{summary_report['win_rate']:.2%}",
                "Best Trade": f"{summary_report['best_trade']:.2%}",
                "Worst Trade": f"{summary_report['worst_trade']:.2%}",
                "Avg Win vs Lost Pct": f"{summary_report['avg_win_pnl_pct']:.2%} vs {summary_report['avg_lose_pnl_pct']:.2%}",
                "Avg Trade Duration": summary_report["avg_duration"],
                "Profit Factor": f"{summary_report['profit_factor']:.2f}",
                "Expectancy": f"{summary_report['expectancy']:.2%}",
                "SQN": f"{summary_report['sqn']:.2f}",
            }
        )
        return display_report

    @staticmethod
    def display(strategy: Strategy) -> None:
        display_report = Reporter.get_display_report(strategy)
        with pd.option_context("display.max_colwidth", None):
            logger.info(f"\n{display_report}")

    @classmethod
    def set(cls, strategy: Strategy) -> None:
        strategy.report["asset"] = Reporter.get_asset_report(strategy)
        strategy.report["portfolio"] = Reporter.get_portfolio_report(strategy)
        strategy.report["transaction"] = Reporter.get_transaction_report(strategy)
        strategy.report["order"] = Reporter.get_order_report(strategy)
        strategy.report["trade"] = Reporter.get_trade_report(strategy)
        strategy.report["summary"] = Reporter.get_summary_report(strategy)
        strategy.report["store"] = Reporter.get_store_report(strategy)

