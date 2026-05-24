"""
共享 fixtures: mock 通达信数据、虚拟账户、合成行情。

所有测试不连通达信，用合成数据完全覆盖。
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from quant_backtester.engine.portfolio import Portfolio


# ═══════════════════════════════════════════════════════════════
# 合成行情数据生成器
# ═══════════════════════════════════════════════════════════════


def make_daily_ohlcv(
    n_days: int = 200,
    start_price: float = 10.0,
    trend: float = 0.0,
    volatility: float = 0.02,
    seed: int = 42,
    start_date: str = "2020-01-02",
) -> pd.DataFrame:
    """生成合成日线 OHLCV 数据。

    Args:
        n_days: 交易日数
        start_price: 起始价格
        trend: 日均对数收益率（0=横盘, 0.001=慢牛, -0.001=阴跌）
        volatility: 日波动率
        seed: 随机种子
        start_date: 起始日期 (YYYY-MM-DD)，实际日期会跳过周末

    Returns:
        DataFrame, index=日期(datetime), columns=[open,close,high,low,volume]
    """
    rng = np.random.RandomState(seed)

    # 生成连续的交易日（跳过周末）
    dates = []
    current = datetime.strptime(start_date, "%Y-%m-%d")
    while len(dates) < n_days:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)

    # 对数收益 → 价格序列
    returns = rng.normal(trend, volatility, n_days)
    prices = start_price * np.exp(np.cumsum(returns))

    data = []
    for i in range(n_days):
        close = prices[i]
        daily_range = close * volatility * rng.uniform(0.5, 2.0)
        high = close + daily_range * rng.uniform(0.3, 1.0)
        low = close - daily_range * rng.uniform(0.3, 1.0)
        open_price = close * (1 + rng.uniform(-volatility, volatility))

        # 确保 OHLC 自洽
        high = max(high, open_price, close)
        low = min(low, open_price, close)

        volume = int(rng.uniform(1_000_000, 50_000_000))

        data.append({
            "open": round(open_price, 2),
            "close": round(close, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "volume": volume,
        })

    df = pd.DataFrame(data, index=pd.DatetimeIndex(dates))
    df.index.name = "date"
    return df


def make_limit_data(
    direction: str = "up",
    n_days: int = 100,
    limit_days: list[int] | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """生成含涨跌停的合成数据。

    Args:
        direction: 'up' 涨停, 'down' 跌停
        n_days: 总天数
        limit_days: 哪些天涨跌停（索引列表），默认 [10, 30, 50, 70]
        seed: 随机种子
    """
    rng = np.random.RandomState(seed)

    if limit_days is None:
        limit_days = [10, 30, 50, 70]

    limit_set = set(limit_days)

    # 生成日期
    dates = []
    current = datetime(2020, 1, 2)
    while len(dates) < n_days:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)

    base_price = 10.0
    prices = []
    data = []

    for i in range(n_days):
        if i == 0:
            close = base_price
        elif i in limit_set:
            if direction == "up":
                close = round(prices[-1] * 1.10, 2)
            else:
                close = round(prices[-1] * 0.90, 2)
        else:
            change = rng.uniform(-0.05, 0.05)
            close = round(prices[-1] * (1 + change), 2)

        prices.append(close)
        daily_range = close * 0.02
        open_price = round(close * (1 + rng.uniform(-0.02, 0.02)), 2)
        high = round(max(open_price, close) + daily_range * rng.uniform(0, 0.5), 2)
        low = round(min(open_price, close) - daily_range * rng.uniform(0, 0.5), 2)
        volume = int(rng.uniform(1_000_000, 50_000_000))

        data.append({
            "open": max(open_price, 0.01),
            "close": max(close, 0.01),
            "high": max(high, 0.01),
            "low": max(low, 0.01),
            "volume": volume,
        })

    df = pd.DataFrame(data, index=pd.DatetimeIndex(dates))
    df.index.name = "date"
    return df


def make_macd_trend_data(seed: int = 42) -> pd.DataFrame:
    """生成有明显 MACD 金叉/死叉的行情数据。

    前1/3: 震荡上行 → 中1/3: 持续下跌 → 后1/3: 反弹
    这样一定会产生金叉和死叉。
    """
    rng = np.random.RandomState(seed)
    n = 200
    x = np.linspace(0, 4 * np.pi, n)

    # 趋势 + 震荡 = MACD 可识别的走势
    trend = np.sin(x) * 3 + np.linspace(-1, 1, n) * 2
    prices = 10 + trend + rng.normal(0, 0.3, n)
    prices = np.maximum(prices, 1.0)

    dates = []
    current = datetime(2020, 1, 2)
    while len(dates) < n:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)

    data = []
    for i in range(n):
        close = round(float(prices[i]), 2)
        daily_range = close * 0.02
        high = round(close + daily_range * rng.uniform(0.3, 1.0), 2)
        low = round(close - daily_range * rng.uniform(0.3, 1.0), 2)
        open_p = round(close * (1 + rng.uniform(-0.01, 0.01)), 2)
        volume = int(rng.uniform(1_000_000, 50_000_000))

        data.append({
            "open": open_p,
            "close": close,
            "high": max(high, open_p, close),
            "low": min(low, open_p, close),
            "volume": volume,
        })

    return pd.DataFrame(data, index=pd.DatetimeIndex(dates))


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def basic_daily() -> pd.DataFrame:
    """100天横盘合成数据。"""
    return make_daily_ohlcv(n_days=100, start_price=10.0, trend=0.0)


@pytest.fixture
def uptrend_daily() -> pd.DataFrame:
    """200天上升趋势数据。"""
    return make_daily_ohlcv(n_days=200, start_price=10.0, trend=0.002)


@pytest.fixture
def macd_trend_daily() -> pd.DataFrame:
    """200天震荡趋势数据（适合 MACD 策略测试）。"""
    return make_macd_trend_data()


@pytest.fixture
def limit_up_daily() -> pd.DataFrame:
    """含涨停日的数据。"""
    return make_limit_data(direction="up", n_days=100, limit_days=[10, 30, 50, 70])


@pytest.fixture
def limit_down_daily() -> pd.DataFrame:
    """含跌停日的数据。"""
    return make_limit_data(direction="down", n_days=100, limit_days=[10, 30, 50, 70])


@pytest.fixture
def portfolio_100k() -> Portfolio:
    """10万初始资金的虚拟账户。"""
    return Portfolio(initial_capital=100_000)


@pytest.fixture
def portfolio_with_position() -> Portfolio:
    """持有 1000 股、成本 10 元的账户。"""
    p = Portfolio(initial_capital=100_000)
    # 手动设置持仓（模拟已买入跨夜）
    p.shares = 1000
    p.cost = 10.0
    p.cash = 90_000
    p.bought_day_idx = -1  # 隔夜底仓，可卖出
    p._latest_price = 10.0
    return p
