"""
单元测试 — 策略: MACD 金叉死叉, MACD 顶底背离, KDJ 金叉死叉, 周K+日K KDJ 联动。

每个策略都用 mock 数据在引擎中运行完整回测，验证信号逻辑。
"""

from unittest import mock

import pandas as pd
import pytest

from quant_backtester.engine.backtest import run_one
from quant_backtester.strategies.macd_cross import MACDCross
from quant_backtester.strategies.macd_divergence import MACDDivergence
from quant_backtester.strategies.kdj_cross import KDJCross
from quant_backtester.strategies.weekly_daily_kdj import WeeklyDailyKDJ

from .conftest import make_macd_trend_data, make_daily_ohlcv


# ═══════════════════════════════════════════════════════════════
# MACD 金叉死叉
# ═══════════════════════════════════════════════════════════════

class TestMACDCross:
    def test_strategy_metadata(self):
        assert MACDCross.name == "MACD金叉死叉"
        assert "MACD" in MACDCross.description

    def test_init_computes_indicators(self):
        df = make_macd_trend_data()
        strategy = MACDCross()
        strategy.daily = df
        strategy.init()
        assert hasattr(strategy, "dif")
        assert hasattr(strategy, "dea")
        assert len(strategy.dif) == len(df)

    def test_next_no_trade_before_enough_data(self):
        df = make_macd_trend_data()
        strategy = MACDCross()
        strategy.daily = df
        strategy.init()
        assert strategy.next(0) == []

    def test_run_one_produces_trades(self):
        df = make_macd_trend_data()
        with mock.patch("quant_backtester.engine.backtest.get_daily", lambda code: df.copy()):
            result = run_one("600000", MACDCross, 90, seed=42)
        assert result["success"]
        buys = [t for t in result["trades"] if t["action"] == "buy"]
        assert len(buys) >= 1


# ═══════════════════════════════════════════════════════════════
# MACD 顶底背离
# ═══════════════════════════════════════════════════════════════

class TestMACDDivergence:
    def test_strategy_metadata(self):
        assert MACDDivergence.name == "MACD顶底背离"

    def test_init_computes_dif(self):
        df = make_daily_ohlcv(n_days=200, start_price=10.0, trend=0.0)
        strategy = MACDDivergence()
        strategy.daily = df
        strategy.init()
        assert hasattr(strategy, "dif")
        assert len(strategy.dif) == len(df)

    def test_run_one_bullish(self):
        df = make_daily_ohlcv(n_days=200, start_price=10.0, trend=-0.001, volatility=0.03)
        with mock.patch("quant_backtester.engine.backtest.get_daily", lambda code: df.copy()):
            result = run_one("600000", MACDDivergence, 80, seed=42)
        assert result["success"]

    def test_run_one_bearish(self):
        df = make_daily_ohlcv(n_days=200, start_price=10.0, trend=0.002, volatility=0.03)
        with mock.patch("quant_backtester.engine.backtest.get_daily", lambda code: df.copy()):
            result = run_one("600000", MACDDivergence, 80, seed=42)
        assert result["success"]


# ═══════════════════════════════════════════════════════════════
# KDJ 金叉死叉
# ═══════════════════════════════════════════════════════════════

class TestKDJCross:
    def test_strategy_metadata(self):
        assert KDJCross.name == "KDJ金叉死叉"

    def test_init_computes_kdj(self):
        df = make_macd_trend_data()
        strategy = KDJCross()
        strategy.daily = df
        strategy.init()
        assert hasattr(strategy, "k")
        assert hasattr(strategy, "d")
        assert hasattr(strategy, "j")

    def test_j_over_100_triggers_sell(self):
        df = make_daily_ohlcv(n_days=200, start_price=10.0, trend=0.005, volatility=0.02)
        strategy = KDJCross()
        strategy.daily = df
        strategy.init()
        for i in range(30, len(df)):
            if pd.notna(strategy.j.iloc[i]) and strategy.j.iloc[i] > 100:
                orders = strategy.next(i)
                sells = [o for o in orders if o.action == "sell"]
                assert len(sells) >= 1
                assert "超买" in sells[0].reason
                return

    def test_run_one_completes(self):
        df = make_macd_trend_data()
        with mock.patch("quant_backtester.engine.backtest.get_daily", lambda code: df.copy()):
            result = run_one("600000", KDJCross, 90, seed=42)
        assert result["success"]


# ═══════════════════════════════════════════════════════════════
# 周线 + 日线 KDJ 联动
# ═══════════════════════════════════════════════════════════════

class TestWeeklyDailyKDJ:
    def test_strategy_metadata(self):
        assert "联动" in WeeklyDailyKDJ.name or "联动" in WeeklyDailyKDJ.description

    def test_init_computes_both_timeframes(self):
        df = make_macd_trend_data()
        strategy = WeeklyDailyKDJ()
        strategy.daily = df
        from quant_backtester.engine.backtest import _resample_weekly, _align_to_daily
        strategy.weekly = _align_to_daily(_resample_weekly(df), df.index)
        strategy.init()
        assert hasattr(strategy, "dk")
        assert hasattr(strategy, "wk")

    def test_weekly_dead_forces_sell(self):
        df = make_daily_ohlcv(n_days=200, start_price=10.0, trend=-0.003, volatility=0.03)
        strategy = WeeklyDailyKDJ()
        strategy.daily = df
        from quant_backtester.engine.backtest import _resample_weekly, _align_to_daily
        strategy.weekly = _align_to_daily(_resample_weekly(df), df.index)
        strategy.init()
        for i in range(40, len(df)):
            if strategy._weekly_dead_zone(i):
                orders = strategy.next(i)
                sells = [o for o in orders if o.action == "sell"]
                assert len(sells) >= 1
                assert "周K死叉" in sells[0].reason
                return

    def test_weekly_golden_allows_daily_buy(self):
        df = make_daily_ohlcv(n_days=200, start_price=10.0, trend=0.003, volatility=0.02)
        strategy = WeeklyDailyKDJ()
        strategy.daily = df
        from quant_backtester.engine.backtest import _resample_weekly, _align_to_daily
        strategy.weekly = _align_to_daily(_resample_weekly(df), df.index)
        strategy.init()
        for i in range(40, len(df)):
            if strategy._weekly_golden_zone(i) and strategy.d_golden.iloc[i]:
                orders = strategy.next(i)
                buys = [o for o in orders if o.action == "buy"]
                if len(buys) >= 1:
                    assert "(周金叉)" in buys[0].reason
                    return

    def test_run_one_completes(self):
        df = make_macd_trend_data()
        with mock.patch("quant_backtester.engine.backtest.get_daily", lambda code: df.copy()):
            result = run_one("600000", WeeklyDailyKDJ, 90, seed=42)
        assert result["success"]
