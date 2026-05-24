"""
回测指标计算 — 夏普比率、最大回撤、胜率、盈亏比等。
"""

import math
from typing import Any

import numpy as np


def compute_metrics(
    equity_curve: list[dict],
    trades: list[dict],
    initial_capital: float,
    window_days: int,
    risk_free_rate: float = 0.02,
) -> dict[str, Any]:
    """从回测原始数据计算所有指标。

    Args:
        equity_curve: 每日权益 [{date, total_value, return_pct}, ...]
        trades: 交易记录 [{action, profit_pct, ...}, ...]
        initial_capital: 初始资金
        window_days: 回测天数
        risk_free_rate: 无风险利率（默认2%）

    Returns:
        指标 dict
    """
    if not equity_curve:
        return _empty_metrics()

    values = np.array([e["total_value"] for e in equity_curve])

    # ── 收益率 ──
    final_value = values[-1]
    total_return = (final_value / initial_capital - 1) * 100

    # 年化收益率 (252 个交易日)
    years = window_days / 252
    annual_return = ((final_value / initial_capital) ** (1 / max(years, 0.01)) - 1) * 100 if years > 0 else 0

    # ── 日收益率序列 ──
    daily_returns = np.diff(values) / values[:-1]
    if len(daily_returns) == 0:
        return _empty_metrics()

    # ── 夏普比率 ──
    mean_daily = np.mean(daily_returns)
    std_daily = np.std(daily_returns, ddof=1)
    daily_rf = risk_free_rate / 252

    if std_daily > 0:
        sharpe = (mean_daily - daily_rf) / std_daily * math.sqrt(252)
    else:
        sharpe = 0.0

    # ── 最大回撤 ──
    peak = np.maximum.accumulate(values)
    drawdowns = (values - peak) / peak * 100
    max_drawdown = float(np.min(drawdowns))

    # ── 胜率 / 盈亏比 ──
    sell_trades = [t for t in trades if t["action"] == "sell"]
    wins = [t for t in sell_trades if t["profit_pct"] > 0]
    losses = [t for t in sell_trades if t["profit_pct"] < 0]

    win_count = len(wins)
    loss_count = len(losses)
    total_trades = win_count + loss_count
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0

    avg_win = np.mean([t["profit_pct"] for t in wins]) if wins else 0
    avg_loss = abs(np.mean([t["profit_pct"] for t in losses])) if losses else 0
    profit_factor = (avg_win / avg_loss) if avg_loss > 0 else (999 if avg_win > 0 else 0)

    # ── 波动率 ──
    volatility = float(std_daily * math.sqrt(252) * 100)

    # ── Calmar 比率 ──
    calmar = annual_return / abs(max_drawdown) if abs(max_drawdown) > 0 else 0

    return {
        "total_return_pct": round(total_return, 2),
        "annual_return_pct": round(annual_return, 2),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown_pct": round(max_drawdown, 2),
        "volatility_pct": round(volatility, 2),
        "calmar_ratio": round(calmar, 3),
        "total_trades": total_trades,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate_pct": round(win_rate, 1),
        "avg_win_pct": round(float(avg_win), 2),
        "avg_loss_pct": round(float(avg_loss), 2),
        "profit_factor": round(float(profit_factor), 2),
        "buy_hold_return_pct": round(
            (values[-1] / values[0] - 1) * 100 if values[0] > 0 else 0, 2
        ),
    }


def aggregate_metrics(results: list[dict]) -> dict[str, Any]:
    """汇总多次回测的结果。

    Args:
        results: run_one() 返回的 dict 列表

    Returns:
        汇总指标 dict
    """
    successful = [r for r in results if r.get("success")]
    if not successful:
        return {"task_count": len(results), "success_count": 0, "error": "无成功回测"}

    returns = [r["total_return_pct"] for r in successful]
    sharpes = [m["sharpe_ratio"] for r in successful
               if (m := _metrics_from(r)) is not None]
    drawdowns = [m["max_drawdown_pct"] for r in successful
                 if (m := _metrics_from(r)) is not None]
    win_rates = [m["win_rate_pct"] for r in successful
                 if (m := _metrics_from(r)) is not None]

    # 合并所有交易
    all_trades = []
    for r in successful:
        all_trades.extend(r.get("trades", []))
    sell_trades = [t for t in all_trades if t["action"] == "sell"]
    wins = [t for t in sell_trades if t["profit_pct"] > 0]
    total_sell = len(sell_trades)

    return {
        "task_count": len(results),
        "success_count": len(successful),
        "avg_return_pct": round(np.mean(returns), 2) if returns else 0,
        "median_return_pct": round(np.median(returns), 2) if returns else 0,
        "best_return_pct": round(max(returns), 2) if returns else 0,
        "worst_return_pct": round(min(returns), 2) if returns else 0,
        "avg_sharpe": round(np.mean(sharpes), 3) if sharpes else 0,
        "avg_max_drawdown_pct": round(np.mean(drawdowns), 2) if drawdowns else 0,
        "avg_win_rate_pct": round(np.mean(win_rates), 1) if win_rates else 0,
        "total_trades": total_sell,
        "win_count": len(wins),
        "overall_win_rate_pct": round(len(wins) / total_sell * 100, 1) if total_sell > 0 else 0,
        "winning_task_pct": round(
            sum(1 for r in returns if r > 0) / len(returns) * 100, 1
        ) if returns else 0,
    }


def _metrics_from(result: dict) -> dict | None:
    """从单个回测结果中提取指标（如果还没有计算过）。"""
    if "metrics" in result:
        return result["metrics"]
    return None


def _empty_metrics() -> dict:
    return {
        "total_return_pct": 0.0,
        "annual_return_pct": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown_pct": 0.0,
        "volatility_pct": 0.0,
        "calmar_ratio": 0.0,
        "total_trades": 0,
        "win_count": 0,
        "loss_count": 0,
        "win_rate_pct": 0.0,
        "avg_win_pct": 0.0,
        "avg_loss_pct": 0.0,
        "profit_factor": 0.0,
        "buy_hold_return_pct": 0.0,
    }
