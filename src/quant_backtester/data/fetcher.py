"""
通达信K线数据拉取 — 通过 mootdx 获取日线/周线/月线 OHLCV。

日线: c.k(code, begin, end) — 无上限，按日期区间
周线: c.bars(code, frequency='week', start, offset) — 单次800根
月线: c.bars(code, frequency='mon', start, offset) — 单次800根
"""

from datetime import date

import pandas as pd
from mootdx.quotes import Quotes

# 延迟初始化，避免首次 import 就连接
_client: Quotes | None = None


def _get_client() -> Quotes:
    global _client
    if _client is None:
        _client = Quotes.factory(market="std")
    return _client


# ── 日线 ───────────────────────────────────────────


def fetch_daily(code: str, begin: str, end: str) -> pd.DataFrame:
    """拉取日线 OHLCV。

    Returns:
        DataFrame, index=日期(datetime), columns=[open,close,high,low,volume,amount]
        数据为空时返回空 DataFrame。
    """
    try:
        df = _get_client().k(symbol=code, begin=begin, end=end)
    except KeyError:
        # 某些代码（债券/基金）没有K线数据，mootdx 可能抛出 KeyError
        return pd.DataFrame()
    except Exception as e:
        raise RuntimeError(f"拉取 {code} 日线失败 [{begin}~{end}]: {e}") from e

    if df is None or len(df) == 0:
        return pd.DataFrame()

    # 统一列名，只保留核心列
    column_map = {"vol": "volume"} if "vol" in df.columns else {}
    df = df.rename(columns=column_map)
    df.index.name = "date"

    # 只保留核心列
    cols = ["open", "close", "high", "low", "volume"]
    available = [c for c in cols if c in df.columns]
    # 去重：mootdx 可能同事返回 vol 和 volume
    df = df[available].copy()
    # 如果有重复列名，取第一个
    df = df.loc[:, ~df.columns.duplicated()]
    return df


def fetch_daily_latest_date(code: str) -> str:
    """拉取一只股票最近一天的数据，用于检查缓存新鲜度。"""
    today = date.today().isoformat()
    df = fetch_daily(code, begin=today, end=today)
    if len(df) == 0:
        # 当天无数据（非交易日），返回空
        return ""
    return df.index[-1].strftime("%Y-%m-%d")


# ── 周线 / 月线 ────────────────────────────────────


def _fetch_bars(code: str, frequency: str, max_offset: int = 800) -> pd.DataFrame:
    """拉取周线或月线（mootdx bars 方法，单次最多 800 根）。

    frequency: 'week' | 'mon'
    """
    all_parts = []
    start = 0
    while True:
        try:
            df = _get_client().bars(symbol=code, frequency=frequency, start=start, offset=max_offset)
        except Exception as e:
            raise RuntimeError(f"拉取 {code} {frequency} 失败 [start={start}]: {e}") from e

        if df is None or len(df) == 0:
            break

        all_parts.append(df)
        if len(df) < max_offset:
            break
        start += max_offset

    if not all_parts:
        return pd.DataFrame()

    result = pd.concat(all_parts)
    result.index.name = "date"

    # 统一列名，去重
    if "vol" in result.columns:
        result = result.rename(columns={"vol": "volume"})

    cols = ["open", "close", "high", "low", "volume"]
    available = [c for c in cols if c in result.columns]
    result = result[available].copy()
    result = result.loc[:, ~result.columns.duplicated()]
    return result.sort_index()


def fetch_weekly(code: str) -> pd.DataFrame:
    """拉取周线（全量，约16年）。"""
    return _fetch_bars(code, frequency="week")


def fetch_monthly(code: str) -> pd.DataFrame:
    """拉取月线（全量，上市以来）。"""
    return _fetch_bars(code, frequency="mon")
