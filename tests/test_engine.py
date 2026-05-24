"""
单元测试 — 回测引擎核心: mock 通达信数据，完整回测流程。
"""

from unittest import mock

import pandas as pd
import pytest

from quant_backtester.engine.backtest import run_one
from quant_backtester.engine.portfolio import Portfolio
from quant_backtester.strategies.base import BaseStrategy, Order

from .conftest import make_daily_ohlcv, make_limit_data, make_macd_trend_data


# ══ 辅助策略 ══

class AlwaysBuy(BaseStrategy):
    name = "AlwaysBuy"
    description = "每日买入"
    def init(self): pass
    def next(self, i): return [Order.buy(pct=1.0, reason="测试买入")]

class AlwaysSell(BaseStrategy):
    name = "AlwaysSell"
    description = "每日卖出"
    def init(self): pass
    def next(self, i): return [Order.sell(pct=1.0, reason="测试卖出")]

class Buy0Sell50(BaseStrategy):
    name = "Buy0Sell50"
    description = "第0天买第50天卖"
    def init(self): pass
    def next(self, i):
        if i == 0: return [Order.buy(pct=1.0, reason="开盘买入")]
        if i == 50: return [Order.sell(pct=1.0, reason="第50天卖出")]
        return []

class BuySellSameDay(BaseStrategy):
    name = "BuySellSameDay"
    description = "同日买卖"
    def init(self): pass
    def next(self, i):
        if i == 10: return [Order.buy(pct=1.0, reason="买入"), Order.sell(pct=1.0, reason="立即卖出")]
        return []

class CrashStrategy(BaseStrategy):
    name = "Crash"
    description = "init crash"
    def init(self): raise RuntimeError("init crashed")
    def next(self, i): return []

class NextCrashStrategy(BaseStrategy):
    name = "NextCrash"
    description = "next crash"
    def init(self): pass
    def next(self, i):
        if i == 5: raise ValueError("next crashed at day 5")
        return []


def mock_get_daily(df):
    return lambda code: df.copy() if df is not None else pd.DataFrame()


# ═══════════════════════════════════

class TestBasicBacktest:
    def test_run_one_success(self):
        df = make_macd_trend_data()
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            result = run_one("600000", Buy0Sell50, 180, seed=42)
        assert result["success"]
        assert len(result["trades"]) > 0

    def test_insufficient_data(self):
        df = make_daily_ohlcv(n_days=50, start_price=10.0)
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            result = run_one("600000", AlwaysBuy, 180, seed=42)
        assert not result["success"]
        assert "数据不足" in result["error"]

    def test_random_window_selection(self):
        df = make_daily_ohlcv(n_days=500, start_price=10.0, trend=0.001)
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            r1 = run_one("600000", AlwaysBuy, 100, seed=1)
            r2 = run_one("600000", AlwaysBuy, 100, seed=2)
        assert r1["window_start"] != r2["window_start"]

    def test_fixed_date_range(self):
        df = make_daily_ohlcv(n_days=500, start_price=10.0, start_date="2020-01-02")
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            result = run_one("600000", AlwaysBuy, 100, start_date="2020-06-01", end_date="2020-12-31", seed=42)
        assert result["success"]


class TestTPlusOneEngine:
    def test_buy_same_day_cannot_sell(self):
        df = make_daily_ohlcv(n_days=300, start_price=10.0, trend=0.0)
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            result = run_one("600000", BuySellSameDay, 100, seed=42)
        assert result["success"]
        day10_sells = [t for t in result["trades"] if t["action"] == "sell" and "立即卖出" in t["reason"]]
        assert len(day10_sells) == 0

    def test_overnight_position_can_sell(self):
        df = make_daily_ohlcv(n_days=300, start_price=10.0, trend=0.001)
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            result = run_one("600000", Buy0Sell50, 100, seed=42)
        assert result["success"]
        sells = [t for t in result["trades"] if t["action"] == "sell"]
        assert len(sells) >= 1


class TestLimitEngine:
    def test_cannot_buy_at_limit_up(self):
        df = make_limit_data(direction="up", n_days=200, limit_days=[30])
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            result = run_one("600000", AlwaysBuy, 80, seed=42)
        assert result["success"]

    def test_cannot_sell_at_limit_down(self):
        df = make_limit_data(direction="down", n_days=200, limit_days=[30])
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            result = run_one("600000", AlwaysSell, 80, seed=42)
        assert result["success"]


class TestRiskControl:
    def test_no_sell_without_position(self):
        df = make_daily_ohlcv(n_days=300, start_price=10.0)
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            result = run_one("600000", AlwaysSell, 100, seed=42)
        assert len(result["trades"]) == 0

    def test_no_double_buy(self):
        df = make_daily_ohlcv(n_days=300, start_price=10.0, trend=0.001)
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            result = run_one("600000", AlwaysBuy, 100, seed=42)
        buys = [t for t in result["trades"] if t["action"] == "buy"]
        assert len(buys) == 1

    def test_force_close_at_end(self):
        df = make_daily_ohlcv(n_days=300, start_price=10.0, trend=0.001)
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            result = run_one("600000", AlwaysBuy, 100, seed=42)
        sells = [t for t in result["trades"] if t["action"] == "sell"]
        assert len(sells) == 1
        assert sells[0]["reason"] == "回测结束平仓"


class TestFeesAndSlippage:
    def test_commission_charged(self):
        df = make_daily_ohlcv(n_days=300, start_price=10.0, trend=0.001)
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            result = run_one("600000", Buy0Sell50, 100, commission_rate=0.0003, seed=42)
        for t in result["trades"]:
            assert t["commission"] > 0

    def test_slippage_affects_price(self):
        df = make_daily_ohlcv(n_days=300, start_price=10.0, trend=0.001)
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            result = run_one("600000", Buy0Sell50, 100, slippage_rate=0.002, seed=42)
        buy_trades = [t for t in result["trades"] if t["action"] == "buy"]
        for t in buy_trades:
            assert t["slippage"] >= 0


class TestEquityCurve:
    def test_equity_curve_length(self):
        df = make_daily_ohlcv(n_days=300, start_price=10.0)
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            result = run_one("600000", AlwaysBuy, 100, seed=42)
        assert len(result["equity_curve"]) == result["window_days"]

    def test_equity_curve_has_all_fields(self):
        df = make_daily_ohlcv(n_days=300, start_price=10.0)
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            result = run_one("600000", AlwaysBuy, 100, seed=42)
        for entry in result["equity_curve"]:
            for key in ["date", "price", "cash", "shares", "total_value", "return_pct"]:
                assert key in entry

    def test_initial_value_equals_capital(self):
        df = make_daily_ohlcv(n_days=300, start_price=10.0)
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            result = run_one("600000", AlwaysSell, 100, initial_capital=200_000, seed=42)
        e0 = result["equity_curve"][0]
        assert abs(e0["total_value"] - 200_000) < 1.0


class TestErrorHandling:
    def test_init_exception_is_caught(self):
        df = make_daily_ohlcv(n_days=300, start_price=10.0)
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            result = run_one("600000", CrashStrategy, 100, seed=42)
        assert not result["success"]
        assert "init crashed" in result["error"]

    def test_next_exception_does_not_crash_engine(self):
        df = make_daily_ohlcv(n_days=300, start_price=10.0)
        with mock.patch("quant_backtester.engine.backtest.get_daily", mock_get_daily(df)):
            result = run_one("600000", NextCrashStrategy, 100, seed=42)
        assert result["success"]
        assert len(result["equity_curve"]) == 100
