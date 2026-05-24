"""
技术指标工具 — 纯函数，接受 pd.Series/DataFrame，返回计算结果。

所有函数不依赖策略基类，可以直接在策略的 init() 中调用。
"""

import numpy as np
import pandas as pd


# ── 均线 ────────────────────────────────────────────

def sma(series: pd.Series, n: int) -> pd.Series:
    """简单移动平均"""
    return series.rolling(window=n).mean()


def ema(series: pd.Series, n: int) -> pd.Series:
    """指数移动平均"""
    return series.ewm(span=n, adjust=False).mean()


def sma_multi(series: pd.Series, periods: list[int]) -> pd.DataFrame:
    """一次计算多条 SMA。

    Args:
        series: 价格序列（通常 close）
        periods: 周期列表，如 [5, 10, 20, 60]

    Returns:
        DataFrame，列名 ma5/ma10/ma20/ma60
    """
    result = pd.DataFrame(index=series.index)
    for n in periods:
        result[f"ma{n}"] = sma(series, n)
    return result


def ema_multi(series: pd.Series, periods: list[int]) -> pd.DataFrame:
    """一次计算多条 EMA。"""
    result = pd.DataFrame(index=series.index)
    for n in periods:
        result[f"ema{n}"] = ema(series, n)
    return result


def add_mas(df: pd.DataFrame, periods: list[int] | None = None) -> pd.DataFrame:
    """为 OHLCV DataFrame 原地添加 MA 列。

    Args:
        df: 含 close 列的 OHLCV DataFrame
        periods: 周期列表，默认日线 [5,10,20,60]

    Returns:
        同一个 DataFrame（已附加 ma5/ma10/... 列）
    """
    if periods is None:
        periods = [5, 10, 20, 60]
    close = df["close"]
    for n in periods:
        df[f"ma{n}"] = sma(close, n)
    return df


# ── MACD ────────────────────────────────────────────


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD 指标。

    Returns:
        (dif, dea, histogram) — 三个 pd.Series
        dif = EMA(fast) - EMA(slow)
        dea = EMA(dif, signal)
        histogram = 2 * (dif - dea)
    """
    dif = ema(close, fast) - ema(close, slow)
    dea = ema(dif, signal)
    hist = 2 * (dif - dea)
    return dif, dea, hist


# ── KDJ ─────────────────────────────────────────────


def kdj(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    n: int = 9,
    k_period: int = 3,
    d_period: int = 3,
):
    """KDJ 指标。

    Returns:
        (k, d, j) — 三个 pd.Series
    """
    low_n = low.rolling(window=n).min()
    high_n = high.rolling(window=n).max()

    rsv = (close - low_n) / (high_n - low_n) * 100
    rsv = rsv.fillna(50)  # 极端情况兜底

    k = rsv.ewm(alpha=1.0 / k_period, adjust=False).mean()
    d = k.ewm(alpha=1.0 / d_period, adjust=False).mean()
    j = 3 * k - 2 * d

    return k, d, j


# ── RSI ─────────────────────────────────────────────


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI 指标 (Wilder's smoothing)。"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.ewm(alpha=1.0 / n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / n, adjust=False).mean()

    # avg_loss=0 → RSI=100 (纯上涨，无下跌日)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    result[avg_loss == 0] = 100.0
    return result


# ── 布林带 ──────────────────────────────────────────


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    """布林带。

    Returns:
        (upper, middle, lower) — 三个 pd.Series
    """
    middle = sma(close, n)
    std = close.rolling(window=n).std()
    upper = middle + k * std
    lower = middle - k * std
    return upper, middle, lower


# ── ATR ─────────────────────────────────────────────


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    """平均真实波幅 (ATR)。"""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


# ── 成交量均线 ──────────────────────────────────────


def vol_ma(volume: pd.Series, n: int = 20) -> pd.Series:
    """成交量 N 日均线。"""
    return sma(volume, n)


# ── 金叉/死叉 ───────────────────────────────────────


def golden_cross(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """金叉：fast 上穿 slow（前一根 fast <= slow，当前 fast > slow）。"""
    return (fast > slow) & (fast.shift(1) <= slow.shift(1))


def dead_cross(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """死叉：fast 下穿 slow（前一根 fast >= slow，当前 fast < slow）。"""
    return (fast < slow) & (fast.shift(1) >= slow.shift(1))


# ── 极值点检测 ──────────────────────────────────────


def find_peaks(series: pd.Series, order: int = 5) -> pd.Series:
    """找局部高点（布尔 Series）。"""
    from scipy.signal import argrelextrema
    idx = argrelextrema(series.values, np.greater, order=order)[0]
    result = pd.Series(False, index=series.index)
    result.iloc[idx] = True
    return result


def find_troughs(series: pd.Series, order: int = 5) -> pd.Series:
    """找局部低点（布尔 Series）。"""
    from scipy.signal import argrelextrema
    idx = argrelextrema(series.values, np.less, order=order)[0]
    result = pd.Series(False, index=series.index)
    result.iloc[idx] = True
    return result
