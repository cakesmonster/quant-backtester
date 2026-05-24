"""
单元测试 — 回测指标: 收益率/夏普/回撤/胜率/盈亏比/汇总。

所有测试用合成权益曲线和交易记录，不依赖通达信。
"""

import math

import numpy as np
import pytest

from quant_backtester.engine.metrics import compute_metrics, aggregate_metrics


# ══ 辅助函数 ══


def make_equity_curve(values: list[float], start_date: str = "2020-01-02") -> list[dict]:
    """从总资产序列生成 equity_curve（最小格式）。"""
    curve = []
    for i, v in enumerate(values):
        curve.append({
            "date": f"day_{i}",
            "total_value": v,
            "return_pct": 0.0,  # compute_metrics 不读这个字段
        })
    return curve


def make_trade(action: str, profit_pct: float) -> dict:
    """单笔交易记录（最小必要字段）。"""
    return {"action": action, "profit_pct": profit_pct}


# ═══════════════════════════════════════════════════════════════
# compute_metrics
# ═══════════════════════════════════════════════════════════════


class TestEmptyMetrics:
    def test_empty_equity_curve(self):
        m = compute_metrics([], [], 100_000, 252)
        assert m["total_return_pct"] == 0.0
        assert m["total_trades"] == 0
        assert m["sharpe_ratio"] == 0.0

    def test_single_day_equity(self):
        """单日权益 → daily_returns 为空。"""
        curve = make_equity_curve([100_000])
        m = compute_metrics(curve, [], 100_000, 1)
        assert m["total_trades"] == 0
        assert m["sharpe_ratio"] == 0.0


class TestTotalReturn:
    def test_zero_return(self):
        curve = make_equity_curve([100_000] * 100)
        m = compute_metrics(curve, [], 100_000, 100)
        assert m["total_return_pct"] == 0.0

    def test_positive_return(self):
        curve = make_equity_curve([100_000, 101_000, 102_000, 110_000])
        m = compute_metrics(curve, [], 100_000, 4)
        assert m["total_return_pct"] == 10.0  # (110000/100000 - 1)*100

    def test_negative_return(self):
        curve = make_equity_curve([100_000, 99_000, 98_000, 90_000])
        m = compute_metrics(curve, [], 100_000, 4)
        assert m["total_return_pct"] == -10.0


class TestAnnualReturn:
    def test_annual_return_one_year(self):
        """一年翻倍 → 年化 100%"""
        curve = make_equity_curve([100_000, 200_000])
        m = compute_metrics(curve, [], 100_000, 252)
        assert m["annual_return_pct"] == pytest.approx(100.0, abs=5)

    def test_annual_return_flat(self):
        curve = make_equity_curve([100_000, 100_000])
        m = compute_metrics(curve, [], 100_000, 252)
        assert m["annual_return_pct"] == pytest.approx(0.0, abs=1)


class TestSharpeRatio:
    def test_sharpe_flat_zero(self):
        """无波动 → 夏普=0（std=0，被处理为0）"""
        curve = make_equity_curve([100_000] * 100)
        m = compute_metrics(curve, [], 100_000, 100)
        assert m["sharpe_ratio"] == 0.0

    def test_sharpe_positive_return(self):
        """持续上涨 → 夏普 > 0"""
        n = 252
        rng = np.random.RandomState(42)
        noise = rng.normal(0.001, 0.01, n)
        prices = 100_000 * np.exp(np.cumsum(noise))
        curve = make_equity_curve(prices.tolist())
        m = compute_metrics(curve, [], 100_000, n)
        assert m["sharpe_ratio"] > 0.5  # 趋势 + 小波动应该不错

    def test_sharpe_negative_return(self):
        """持续下跌 → 夏普 < 0"""
        n = 252
        rng = np.random.RandomState(99)
        noise = rng.normal(-0.001, 0.01, n)
        prices = 100_000 * np.exp(np.cumsum(noise))
        curve = make_equity_curve(prices.tolist())
        m = compute_metrics(curve, [], 100_000, n)
        assert m["sharpe_ratio"] < 0


class TestMaxDrawdown:
    def test_no_drawdown(self):
        curve = make_equity_curve([100_000, 101_000, 102_000, 105_000])
        m = compute_metrics(curve, [], 100_000, 4)
        assert m["max_drawdown_pct"] == 0.0

    def test_visible_drawdown(self):
        """先涨到 110k 再跌到 99k"""
        curve = make_equity_curve([100_000, 110_000, 105_000, 99_000])
        m = compute_metrics(curve, [], 100_000, 4)
        dd = (99_000 - 110_000) / 110_000 * 100  # = -10%
        assert m["max_drawdown_pct"] == pytest.approx(dd, abs=0.1)

    def test_multiple_drawdowns(self):
        """多次回撤，取最大"""
        curve = make_equity_curve([
            100_000, 110_000, 105_000, 100_000,  # -9.1%
            120_000, 108_000, 96_000,             # -20% (更大)
            130_000,
        ])
        m = compute_metrics(curve, [], 100_000, 8)
        peak = 120_000
        trough = 96_000
        expected = (trough - peak) / peak * 100
        assert m["max_drawdown_pct"] == pytest.approx(expected, abs=0.1)


class TestWinRate:
    def test_all_wins(self):
        trades = [make_trade("sell", 10.0), make_trade("sell", 5.0), make_trade("sell", 3.0)]
        curve = make_equity_curve([100_000] * 100)
        m = compute_metrics(curve, trades, 100_000, 100)
        assert m["win_rate_pct"] == 100.0
        assert m["total_trades"] == 3
        assert m["win_count"] == 3
        assert m["loss_count"] == 0

    def test_all_losses(self):
        trades = [make_trade("sell", -5.0), make_trade("sell", -3.0)]
        curve = make_equity_curve([100_000] * 100)
        m = compute_metrics(curve, trades, 100_000, 100)
        assert m["win_rate_pct"] == 0.0
        assert m["loss_count"] == 2

    def test_mixed_win_loss(self):
        trades = [
            make_trade("sell", 10.0),
            make_trade("sell", -5.0),
            make_trade("sell", -3.0),
            make_trade("sell", 8.0),
        ]
        curve = make_equity_curve([100_000] * 100)
        m = compute_metrics(curve, trades, 100_000, 100)
        assert m["win_rate_pct"] == 50.0
        assert m["win_count"] == 2
        assert m["loss_count"] == 2

    def test_zero_profit_not_counted(self):
        """profit_pct == 0 不计入胜或败（代码中只比较 >0 和 <0）"""
        trades = [make_trade("sell", 0.0)]
        curve = make_equity_curve([100_000] * 100)
        m = compute_metrics(curve, trades, 100_000, 100)
        assert m["total_trades"] == 0
        assert m["win_rate_pct"] == 0.0

    def test_buy_trades_ignored(self):
        """买入交易不计入胜率。"""
        trades = [
            make_trade("buy", 0.0),
            make_trade("sell", 10.0),
        ]
        curve = make_equity_curve([100_000] * 100)
        m = compute_metrics(curve, trades, 100_000, 100)
        assert m["total_trades"] == 1  # 只统计 sell


class TestAvgWinLoss:
    def test_avg_win(self):
        trades = [make_trade("sell", 10.0), make_trade("sell", 20.0), make_trade("sell", -5.0)]
        curve = make_equity_curve([100_000] * 100)
        m = compute_metrics(curve, trades, 100_000, 100)
        assert m["avg_win_pct"] == 15.0  # (10+20)/2

    def test_avg_loss(self):
        trades = [make_trade("sell", 10.0), make_trade("sell", -5.0), make_trade("sell", -15.0)]
        curve = make_equity_curve([100_000] * 100)
        m = compute_metrics(curve, trades, 100_000, 100)
        assert m["avg_loss_pct"] == 10.0  # abs((-5+-15)/2)

    def test_profit_factor(self):
        trades = [make_trade("sell", 10.0), make_trade("sell", -5.0)]
        curve = make_equity_curve([100_000] * 100)
        m = compute_metrics(curve, trades, 100_000, 100)
        assert m["profit_factor"] == 2.0  # 10 / 5

    def test_profit_factor_no_losses(self):
        trades = [make_trade("sell", 10.0), make_trade("sell", 5.0)]
        curve = make_equity_curve([100_000] * 100)
        m = compute_metrics(curve, trades, 100_000, 100)
        assert m["profit_factor"] == 999.0  # avg_loss=0, avg_win>0


class TestVolatilityAndCalmar:
    def test_volatility_zero(self):
        curve = make_equity_curve([100_000] * 100)
        m = compute_metrics(curve, [], 100_000, 100)
        assert m["volatility_pct"] == 0.0

    def test_volatility_nonzero(self):
        n = 200
        rng = np.random.RandomState(42)
        noise = rng.normal(0, 0.02, n)
        values = (100_000 * np.exp(np.cumsum(noise))).tolist()
        curve = make_equity_curve(values)
        m = compute_metrics(curve, [], 100_000, n)
        assert m["volatility_pct"] > 0

    def test_calmar_ratio(self):
        """calmar = 年化收益 / abs(最大回撤) — 用合理时间窗口"""
        n = 200
        rng = np.random.RandomState(42)
        noise = rng.normal(0.0005, 0.015, n)
        values = (100_000 * np.exp(np.cumsum(noise))).tolist()
        curve = make_equity_curve(values)
        m = compute_metrics(curve, [], 100_000, n)
        if m["max_drawdown_pct"] != 0:
            expected = m["annual_return_pct"] / abs(m["max_drawdown_pct"])
            assert m["calmar_ratio"] == pytest.approx(expected, abs=0.01)


# ═══════════════════════════════════════════════════════════════
# aggregate_metrics
# ═══════════════════════════════════════════════════════════════


class TestAggregateEmpty:
    def test_all_failed(self):
        results = [
            {"success": False, "code": "000001", "error": "数据不足"},
            {"success": False, "code": "000002", "error": "数据不足"},
        ]
        agg = aggregate_metrics(results)
        assert agg["task_count"] == 2
        assert agg["success_count"] == 0


class TestAggregateBasic:
    def test_success_count(self):
        results = [
            {"success": True, "total_return_pct": 10.0, "trades": [make_trade("sell", 10.0)]},
            {"success": True, "total_return_pct": -5.0, "trades": [make_trade("sell", -5.0)]},
            {"success": False, "code": "000003", "error": "fail"},
        ]
        agg = aggregate_metrics(results)
        assert agg["task_count"] == 3
        assert agg["success_count"] == 2

    def test_avg_return(self):
        results = [
            {"success": True, "total_return_pct": 10.0, "trades": []},
            {"success": True, "total_return_pct": 20.0, "trades": []},
        ]
        agg = aggregate_metrics(results)
        assert agg["avg_return_pct"] == 15.0

    def test_best_worst_return(self):
        results = [
            {"success": True, "total_return_pct": 5.0, "trades": []},
            {"success": True, "total_return_pct": -10.0, "trades": []},
            {"success": True, "total_return_pct": 30.0, "trades": []},
        ]
        agg = aggregate_metrics(results)
        assert agg["best_return_pct"] == 30.0
        assert agg["worst_return_pct"] == -10.0

    def test_median_return(self):
        results = [
            {"success": True, "total_return_pct": 10.0, "trades": []},
            {"success": True, "total_return_pct": 20.0, "trades": []},
            {"success": True, "total_return_pct": 30.0, "trades": []},
        ]
        agg = aggregate_metrics(results)
        assert agg["median_return_pct"] == 20.0

    def test_winning_task_pct(self):
        results = [
            {"success": True, "total_return_pct": 10.0, "trades": []},
            {"success": True, "total_return_pct": -5.0, "trades": []},
            {"success": True, "total_return_pct": 5.0, "trades": []},
            {"success": True, "total_return_pct": -2.0, "trades": []},
        ]
        agg = aggregate_metrics(results)
        assert agg["winning_task_pct"] == 50.0  # 2/4 > 0

    def test_overall_trades_merge(self):
        """多只股票的交易合并统计。"""
        results = [
            {"success": True, "total_return_pct": 10.0,
             "trades": [make_trade("sell", 10.0), make_trade("sell", -5.0)]},
            {"success": True, "total_return_pct": 5.0,
             "trades": [make_trade("sell", 3.0), make_trade("sell", -2.0)]},
        ]
        agg = aggregate_metrics(results)
        assert agg["total_trades"] == 4
        assert agg["win_count"] == 2
        assert agg["overall_win_rate_pct"] == 50.0
