"""
回测引擎 — 主循环，驱动策略逐日运行。

单次回测 = 1只股票 × 1个窗口 × 1个策略。
"""

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd

from quant_backtester.data.cache import get_daily
from quant_backtester.engine.portfolio import Portfolio
from quant_backtester.strategies.base import BaseStrategy, Order

logger = logging.getLogger(__name__)


def _resample_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """日线 → 周线，按周五对齐。"""
    if len(daily) == 0:
        return pd.DataFrame()
    return daily.resample("W-FRI").agg({
        "open": "first",
        "close": "last",
        "high": "max",
        "low": "min",
        "volume": "sum",
    }).dropna()


def _resample_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    """日线 → 月线，按月对齐。"""
    if len(daily) == 0:
        return pd.DataFrame()
    return daily.resample("ME").agg({
        "open": "first",
        "close": "last",
        "high": "max",
        "low": "min",
        "volume": "sum",
    }).dropna()


def _align_to_daily(period_df: pd.DataFrame, daily_index: pd.DatetimeIndex) -> pd.DataFrame:
    """将周线/月线对齐到日线索引：每个日期映射到它所属那根周/月K线。

    引擎保证: daily.iloc[i] 和 weekly.iloc[i] 属于同一天/同一周。
    """
    if len(period_df) == 0:
        return pd.DataFrame(index=daily_index)

    # 对每个日线日期，找到它所属的周/月K线
    mapper = {}
    period_dates = period_df.index.sort_values()
    for d in daily_index:
        # 找到 <= d 的最大周/月日期
        candidates = period_dates[period_dates <= d]
        if len(candidates) > 0:
            mapper[d] = candidates[-1]

    aligned = pd.DataFrame(index=daily_index, columns=period_df.columns, dtype=float)
    for d, p_date in mapper.items():
        aligned.loc[d] = period_df.loc[p_date].values

    return aligned


def run_one(
    code: str,
    strategy_cls: type[BaseStrategy],
    window_days: int,
    initial_capital: float = 100_000,
    commission_rate: float = 0.0003,
    slippage_rate: float = 0.001,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """执行一次回测。

    Args:
        code: 股票代码
        strategy_cls: 策略类（不是实例）
        window_days: 回测窗口（交易日数）
        initial_capital: 初始资金
        commission_rate: 手续费率
        slippage_rate: 滑点率
        start_date: 可选，限定起始日（不指定则随机选）
        end_date: 可选，限定结束日
        seed: 随机种子

    Returns:
        dict:
            success: bool
            code: str
            window_start: str
            window_end: str
            equity_curve: list[dict]  # 每日权益
            trades: list[dict]
            metrics: dict
            error: str | None
    """
    # ── 1. 获取数据 ──
    try:
        full_daily = get_daily(code)
    except Exception as e:
        return {"success": False, "code": code, "error": str(e)}

    if len(full_daily) < window_days + 20:
        return {
            "success": False,
            "code": code,
            "error": f"数据不足: 仅{len(full_daily)}天 (需要≥{window_days + 20})",
        }

    # ── 2. 选择窗口 ──
    import random
    rng = random.Random(seed)

    avail_start = 0
    avail_end = len(full_daily) - window_days

    if start_date and end_date:
        # 限定日期范围
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        mask = (full_daily.index >= start_ts) & (full_daily.index <= end_ts)
        valid_idx = full_daily.index[mask]
        if len(valid_idx) < window_days:
            return {"success": False, "code": code, "error": "指定日期范围内数据不足"}
        start_idx = rng.randint(0, len(valid_idx) - window_days)
        window_start_idx = full_daily.index.get_loc(valid_idx[start_idx])
    else:
        # 随机选起点（至少留20天前置数据算指标）
        window_start_idx = rng.randint(20, avail_end)

    window_daily = full_daily.iloc[window_start_idx:window_start_idx + window_days].copy()
    window_start = window_daily.index[0].strftime("%Y-%m-%d")
    window_end = window_daily.index[-1].strftime("%Y-%m-%d")

    # ── 3. 生成周线/月线 + 对齐 ──
    full_weekly = _resample_weekly(full_daily)
    full_monthly = _resample_monthly(full_daily)

    window_weekly = _align_to_daily(full_weekly, window_daily.index)
    window_monthly = _align_to_daily(full_monthly, window_daily.index)

    # ── 4. 初始化策略 ──
    strategy = strategy_cls()
    strategy.daily = window_daily
    strategy.weekly = window_weekly
    strategy.monthly = window_monthly

    portfolio = Portfolio(
        initial_capital=initial_capital,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
    )

    try:
        strategy.init()
    except Exception as e:
        return {"success": False, "code": code, "error": f"策略初始化失败: {e}"}

    # ── 5. 逐日回测 ──
    equity_curve = []
    dates = window_daily.index

    for i in range(len(dates)):
        date_str = dates[i].strftime("%Y-%m-%d")
        price = float(window_daily.iloc[i]["close"])
        prev_close = float(window_daily.iloc[i-1]["close"]) if i > 0 else price

        # ── T+1 日切 ──
        portfolio.advance_day(i)

        # ── 涨跌停价 ──
        limit_up = round(prev_close * 1.10, 2)
        limit_down = round(prev_close * 0.90, 2)
        is_limit_up = (price >= limit_up - 0.01)
        is_limit_down = (price <= limit_down + 0.01)

        # 更新策略状态
        strategy.has_position = portfolio.has_position
        strategy.cost = portfolio.cost
        strategy.cash = portfolio.cash
        strategy._latest_price = price
        portfolio.set_price(price)

        # 调用策略
        try:
            orders = strategy.next(i)
        except Exception as e:
            logger.warning(f"[{code}] 策略异常 i={i}: {e}")
            orders = []

        # 执行订单（T+1 + 涨跌停 校验）
        for order in orders:
            if order.action == "sell":
                if not portfolio.has_position:
                    logger.warning(f"[{code}] {date_str} 卖出但无持仓: {order.reason}")
                    continue
                if portfolio.bought_day_idx >= 0 and portfolio.bought_day_idx == i:
                    logger.info(f"[{code}] {date_str} T+1锁定,跳过卖出: {order.reason}")
                    continue
                if is_limit_down:
                    logger.info(f"[{code}] {date_str} 跌停封死,跳过卖出: {order.reason}")
                    continue
                portfolio.sell(price, order.pct, date_str, reason=order.reason)
            elif order.action == "buy":
                if portfolio.has_position:
                    logger.warning(f"[{code}] {date_str} 买入但已有持仓: {order.reason}")
                    continue
                if is_limit_up:
                    logger.info(f"[{code}] {date_str} 涨停封死,跳过买入: {order.reason}")
                    continue
                portfolio.buy(price, order.pct, date_str, day_idx=i, reason=order.reason)

        # 记录权益
        equity_curve.append({
            "date": date_str,
            "price": round(price, 2),
            "cash": round(portfolio.cash, 2),
            "shares": portfolio.shares,
            "total_value": round(portfolio.total_value, 2),
            "return_pct": round((portfolio.total_value / initial_capital - 1) * 100, 2),
        })

    # ── 6. 强行平仓（如果回测结束仍持仓）──
    if portfolio.has_position:
        final_price = float(window_daily.iloc[-1]["close"])
        portfolio.sell(final_price, 1.0, window_end, "回测结束平仓")

    # ── 7. 汇总 ──
    return {
        "success": True,
        "code": code,
        "strategy": strategy.name,
        "window_start": window_start,
        "window_end": window_end,
        "window_days": window_days,
        "initial_capital": initial_capital,
        "final_value": round(portfolio.total_value, 2),
        "total_return_pct": round((portfolio.total_value / initial_capital - 1) * 100, 2),
        "equity_curve": equity_curve,
        "trades": [
            {
                "date": t.date,
                "action": t.action,
                "price": t.price,
                "shares": t.shares,
                "amount": t.amount,
                "commission": t.commission,
                "slippage": t.slippage_cost,
                "reason": t.reason,
                "profit_pct": t.profit_pct,
            }
            for t in portfolio.trades
        ],
    }
