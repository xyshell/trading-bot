import pytest
import pandas as pd

from tradingbot.data.candlestick import Candlestick
import tradingbot.util as util


class TestYahooCandlestick:
    def test_currency_mismatch(self):
        with pytest.raises(AssertionError):
            Candlestick("yahoo", ticker="CNY/MSFT", freq="1d")

    def test_get_daily(self):
        df = Candlestick("yahoo", ticker="USD/MSFT", freq="1d", load_len=500).get(pd.Timestamp("2024-01-01"))
        assert len(df) == 500
        assert df.close_time.max() == pd.Timestamp("2023-12-29")

        df = Candlestick("yahoo", ticker="USD/MSFT", freq="1wk", load_len=500).get(pd.Timestamp("2024-01-01"))
        assert len(df) == 500
        assert df.close_time.max() == pd.Timestamp("2024-01-01")

    def test_get_intraday(self):
        now = pd.Timestamp.now()
        df = Candlestick("yahoo", ticker="USD/MSFT", freq="5m", load_len=500).get(now)
        assert len(df) == 500
        assert df.close_time.max() < now


class TestBinanceCandlestick:
    def test_load_sharp(self, snapshot):
        now = pd.Timestamp("2024-01-01")

        df = Candlestick("binance", ticker="USDT/BTC", freq="1h", load_len=1000, closed_only=False).load(now)
        assert len(df) == 1000
        assert df["close_time"].max() <= now
        assert util.hash_pd(df) == snapshot

        df2 = Candlestick("binance", ticker="USDT/BTC", freq="1h", load_len=1000, closed_only=True).load(now)
        pd.testing.assert_frame_equal(df, df2)

        df = Candlestick("binance", ticker="USDT/BTC", freq="1d", load_len=500, closed_only=False).load(now)
        assert len(df) == 500
        assert df["close_time"].max() <= now
        assert util.hash_pd(df) == snapshot

        df2 = Candlestick("binance", ticker="USDT/BTC", freq="1d", load_len=500, closed_only=True).load(now)
        pd.testing.assert_frame_equal(df, df2)

    def test_load_between(self, snapshot):
        df = Candlestick("binance", ticker="USDT/BTC", freq="4h", load_len=500, closed_only=True).load(
            pd.Timestamp("2024-01-01 01:00:00")
        )
        assert len(df) == 500
        assert df["close_time"].max() <= pd.Timestamp("2024-01-01 00:00:00")
        assert util.hash_pd(df) == snapshot

        df = Candlestick("binance", ticker="USDT/BTC", freq="4h", load_len=500, closed_only=False).load(
            pd.Timestamp("2024-01-01 01:00:00")
        )
        assert len(df) == 500
        assert pd.Timestamp("2024-01-01 00:00:00") < df["close_time"].max() <= pd.Timestamp("2024-01-01 01:00:00")
        assert util.hash_pd(df) == snapshot

        df = Candlestick("binance", ticker="USDT/BTC", freq="4h", load_len=500, closed_only=False).load(
            pd.Timestamp("2024-01-01 01:06:00")
        )
        assert len(df) == 500
        assert df["close_time"].max() > pd.Timestamp("2024-01-01 01:00:00")
        assert util.hash_pd(df) == snapshot

    def test_get_history(self, snapshot):
        df = Candlestick("binance", ticker="USDT/BTC", freq="1h", load_len=500, closed_only=False).get(pd.Timestamp("2024-01-01"))
        assert len(df) == 500
        assert util.hash_pd(df) == snapshot

        df2 = Candlestick("binance", ticker="USDT/BTC", freq="1h", load_len=500, closed_only=True).get(pd.Timestamp("2024-01-01"))
        pd.testing.assert_frame_equal(df, df2)  # no lookahead regardless of closed_only in history

        df = Candlestick("binance", ticker="USDT/BTC", freq="1h", load_len=500, closed_only=False).get(
            pd.Timestamp("2024-01-01 00:05:00")
        )
        assert len(df) == 500
        assert util.hash_pd(df) == snapshot

        df2 = Candlestick("binance", ticker="USDT/BTC", freq="1h", load_len=500, closed_only=True).get(
            pd.Timestamp("2024-01-01 00:05:00")
        )
        pd.testing.assert_frame_equal(df, df2)

    def test_get_now_backtest(self):
        now = pd.Timestamp.utcnow().tz_localize(None)

        df = Candlestick("binance", ticker="USDT/BTC", freq="1d", load_len=500, closed_only=True).get(now)
        assert len(df) == 500
        assert df.close_time.max() < now

        df2 = Candlestick("binance", ticker="USDT/BTC", freq="1d", load_len=500, closed_only=False).get(now)
        pd.testing.assert_frame_equal(df, df2)

    @pytest.mark.live
    def test_get_now_live(self):
        now = pd.Timestamp.utcnow().tz_localize(None)

        df = Candlestick("binance", mode="live", ticker="USDT/BTC", freq="1d", load_len=500, closed_only=True).get(now)
        assert len(df) == 500
        assert df["close_time"].max() < now

        df2 = Candlestick("binance", mode="live", ticker="USDT/BTC", freq="1d", load_len=500, closed_only=False).get(now)
        assert len(df2) == 500
        assert df2["close_time"].max() > now


class TestOkxCandlestick:

    def test_load_sharp(self, snapshot):
        now = pd.Timestamp("2024-01-01")

        df = Candlestick("okx", ticker="USDT/BTC", freq="1h", load_len=1000, closed_only=False).load(now)
        assert len(df) == 1000
        assert df["close_time"].max() <= now
        assert util.hash_pd(df) == snapshot

        df2 = Candlestick("okx", ticker="USDT/BTC", freq="1h", load_len=1000, closed_only=True).load(now)
        pd.testing.assert_frame_equal(df, df2)

        df = Candlestick("okx", ticker="USDT/BTC", freq="1d", load_len=500, closed_only=False).load(now)
        assert len(df) == 500
        assert df["close_time"].max() <= now
        assert util.hash_pd(df) == snapshot

        df2 = Candlestick("okx", ticker="USDT/BTC", freq="1d", load_len=500, closed_only=True).load(now)
        pd.testing.assert_frame_equal(df, df2)

    def test_load_between(self, snapshot):
        df = Candlestick("okx", ticker="USDT/BTC", freq="4h", load_len=500, closed_only=True).load(
            pd.Timestamp("2024-01-01 01:00:00")
        )
        assert len(df) == 500
        assert df["close_time"].max() <= pd.Timestamp("2024-01-01 00:00:00")
        assert util.hash_pd(df) == snapshot

        df = Candlestick("okx", ticker="USDT/BTC", freq="4h", load_len=500, closed_only=False).load(
            pd.Timestamp("2024-01-01 01:00:00")
        )
        assert len(df) == 500
        assert pd.Timestamp("2024-01-01 00:00:00") < df["close_time"].max() <= pd.Timestamp("2024-01-01 01:00:00")
        assert util.hash_pd(df) == snapshot

        df = Candlestick("okx", ticker="USDT/BTC", freq="4h", load_len=500, closed_only=False).load(
            pd.Timestamp("2024-01-01 01:06:00")
        )
        assert len(df) == 500
        assert df["close_time"].max() > pd.Timestamp("2024-01-01 01:00:00")
        assert util.hash_pd(df) == snapshot

    def test_get_history(self, snapshot):
        df = Candlestick("okx", ticker="USDT/BTC", freq="1h", load_len=500, closed_only=False).get(pd.Timestamp("2024-01-01"))
        assert len(df) == 500
        assert util.hash_pd(df) == snapshot

        df2 = Candlestick("okx", ticker="USDT/BTC", freq="1h", load_len=500, closed_only=True).get(pd.Timestamp("2024-01-01"))
        pd.testing.assert_frame_equal(df, df2)  # no lookahead regardless of closed_only in history

        df = Candlestick("okx", ticker="USDT/BTC", freq="1h", load_len=500, closed_only=False).get(
            pd.Timestamp("2024-01-01 00:05:00")
        )
        assert len(df) == 500
        assert util.hash_pd(df) == snapshot

        df2 = Candlestick("okx", ticker="USDT/BTC", freq="1h", load_len=500, closed_only=True).get(
            pd.Timestamp("2024-01-01 00:05:00")
        )
        pd.testing.assert_frame_equal(df, df2)

    def test_get_now_backtest(self):
        now = pd.Timestamp.utcnow().tz_localize(None)

        df = Candlestick("okx", ticker="USDT/BTC", freq="1d", load_len=500, closed_only=True).get(now)
        assert len(df) == 500
        assert df.close_time.max() < now

        df2 = Candlestick("okx", ticker="USDT/BTC", freq="1d", load_len=500, closed_only=False).get(now)
        pd.testing.assert_frame_equal(df, df2)

    @pytest.mark.live
    def test_get_now_live(self):
        now = pd.Timestamp.utcnow().tz_localize(None)

        df = Candlestick("okx", mode="live", ticker="USDT/BTC", freq="1d", load_len=500, closed_only=True).get(now)
        assert len(df) == 500
        assert df["close_time"].max() < now

        df2 = Candlestick("okx", mode="live", ticker="USDT/BTC", freq="1d", load_len=500, closed_only=False).get(now)
        assert len(df2) == 500
        assert df2["close_time"].max() > now