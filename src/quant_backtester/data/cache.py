"""
本地 Parquet 缓存 — 增量更新，避免重复从通达信拉数据。

每只股票一个文件: data/cache/{code}.parquet

策略:
  - 文件不存在 → 从通达信拉全量（2015年起）
  - 文件存在 → 读最后日期 → 只拉增量部分（最后日期+1天 ~ 今天）
"""

import os
from datetime import date, timedelta

import pandas as pd

from quant_backtester.config import CACHE_DIR, DAILY_BEGIN
from quant_backtester.data.fetcher import fetch_daily


def _cache_path(code: str) -> str:
    return os.path.join(CACHE_DIR, f"{code}.parquet")


def get_daily(code: str) -> pd.DataFrame:
    """获取股票日线数据（优先缓存，无缓存则拉取）。

    Returns:
        DataFrame, index=日期(datetime), columns=[open,close,high,low,volume]
    """
    path = _cache_path(code)

    if os.path.exists(path):
        df = pd.read_parquet(path)
        if len(df) == 0:
            return df

        # 增量更新：从最后日期+1天拉到今天
        last_date = pd.Timestamp(df.index[-1]).date()
        today = date.today()
        delta_begin = (last_date + timedelta(days=1)).isoformat()

        if last_date < today:
            try:
                delta_df = fetch_daily(code, begin=delta_begin, end=today.isoformat())
            except Exception:
                # 拉增量失败，返回已有缓存（可能是非交易日无新数据）
                return df

            if len(delta_df) > 0:
                # 去重后合并
                existing_dates = set(df.index)
                new_rows = delta_df[~delta_df.index.isin(existing_dates)]
                if len(new_rows) > 0:
                    df = pd.concat([df, new_rows]).sort_index()
                    df.to_parquet(path, compression="snappy")

        return df

    # 无缓存 → 全量拉取
    today = date.today().isoformat()
    df = fetch_daily(code, begin=DAILY_BEGIN, end=today)

    if len(df) > 0:
        os.makedirs(CACHE_DIR, exist_ok=True)
        df.to_parquet(path, compression="snappy")

    return df


def get_weekly(code: str) -> pd.DataFrame:
    """获取周线 — 从日线 resample 生成（不单独缓存）。

    按周五为分界，取 OHLCV:
      open = 周一开盘价, close = 周五收盘价,
      high = 周最高, low = 周最低, volume = 周合计
    """
    daily = get_daily(code)
    if len(daily) == 0:
        return pd.DataFrame()

    weekly = daily.resample("W-FRI").agg({
        "open": "first",
        "close": "last",
        "high": "max",
        "low": "min",
        "volume": "sum",
    }).dropna()

    return weekly


def get_monthly(code: str) -> pd.DataFrame:
    """获取月线 — 从日线 resample 生成。"""
    daily = get_daily(code)
    if len(daily) == 0:
        return pd.DataFrame()

    monthly = daily.resample("ME").agg({
        "open": "first",
        "close": "last",
        "high": "max",
        "low": "min",
        "volume": "sum",
    }).dropna()

    return monthly


def cache_exists(code: str) -> bool:
    """检查某只股票是否有本地缓存。"""
    return os.path.exists(_cache_path(code))


def cache_stats() -> dict:
    """缓存统计：已缓存股票数 + 总大小。"""
    if not os.path.isdir(CACHE_DIR):
        return {"count": 0, "total_size_mb": 0}

    files = [f for f in os.listdir(CACHE_DIR) if f.endswith(".parquet")]
    total = sum(os.path.getsize(os.path.join(CACHE_DIR, f)) for f in files)
    return {
        "count": len(files),
        "total_size_mb": round(total / 1024 / 1024, 2),
    }
