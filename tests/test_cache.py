"""
单元测试 — 本地缓存: get_daily 增量更新 / get_weekly / get_monthly / cache_stats。

所有测试 mock 通达信 fetch_daily + 临时 CACHE_DIR。
"""

import os
import tempfile
from unittest import mock

import pandas as pd
import pytest


def make_ohlcv(n: int, start_date: str = "2020-01-02") -> pd.DataFrame:
    """生成 n 天的 OHLCV 数据。"""
    import numpy as np
    from datetime import datetime, timedelta

    dates = []
    current = datetime.strptime(start_date, "%Y-%m-%d")
    while len(dates) < n:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)

    rng = np.random.RandomState(42)
    prices = 10 + np.cumsum(rng.normal(0, 0.2, n))

    data = []
    for i in range(n):
        close = round(float(prices[i]), 2)
        data.append({
            "open": close,
            "close": close,
            "high": round(close + 0.5, 2),
            "low": round(close - 0.5, 2),
            "volume": 10_000_000,
        })

    return pd.DataFrame(data, index=pd.DatetimeIndex(dates))


@pytest.fixture
def isolated_cache():
    """隔离的缓存环境: 临时 CACHE_DIR + mock fetch_daily。"""
    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch("quant_backtester.data.cache.CACHE_DIR", tmp):
            with mock.patch("quant_backtester.data.cache.fetch_daily") as m:
                m.return_value = pd.DataFrame()
                yield tmp, m


# ═══════════════════════════════════════════════════════════════
# get_daily
# ═══════════════════════════════════════════════════════════════


class TestGetDaily:
    def test_cache_miss_fetches_full(self, isolated_cache):
        tmp, m = isolated_cache
        df = make_ohlcv(100)
        m.return_value = df

        from quant_backtester.data.cache import get_daily
        result = get_daily("000001")
        assert len(result) == 100
        assert os.path.exists(os.path.join(tmp, "000001.parquet"))
        m.assert_called_once()

    def test_cache_hit_reads_from_disk(self, isolated_cache):
        tmp, m = isolated_cache
        df = make_ohlcv(100)
        m.return_value = df

        from quant_backtester.data.cache import get_daily
        get_daily("000001")  # 第一次: 写入缓存
        m.reset_mock()
        m.return_value = pd.DataFrame()  # 增量无新数据

        result = get_daily("000001")  # 第二次: 读缓存
        assert len(result) == 100

    def test_incremental_update(self, isolated_cache):
        tmp, m = isolated_cache
        df_old = make_ohlcv(100, start_date="2020-01-02")
        m.return_value = df_old

        from quant_backtester.data.cache import get_daily
        get_daily("000001")
        m.reset_mock()

        # 增量返回 5 天新数据（日期在旧数据之后）
        df_new = make_ohlcv(5, start_date="2020-07-01")
        m.return_value = df_new

        result = get_daily("000001")
        assert len(result) >= 100

    def test_incremental_no_duplicates(self, isolated_cache):
        tmp, m = isolated_cache
        df1 = make_ohlcv(50, start_date="2020-01-02")
        m.return_value = df1

        from quant_backtester.data.cache import get_daily
        get_daily("000001")
        m.reset_mock()

        # 增量返回包含重叠日期
        df2 = make_ohlcv(10, start_date="2020-02-17")
        m.return_value = df2

        result = get_daily("000001")
        assert not result.index.duplicated().any()

    def test_fetch_exception_returns_cache(self, isolated_cache):
        tmp, m = isolated_cache
        df = make_ohlcv(100)
        m.return_value = df

        from quant_backtester.data.cache import get_daily
        get_daily("000001")
        m.reset_mock()
        m.side_effect = RuntimeError("mootdx down")

        result = get_daily("000001")
        assert len(result) == 100  # 返回已有缓存

    def test_empty_fetch_no_cache_file(self, isolated_cache):
        tmp, m = isolated_cache
        m.return_value = pd.DataFrame()

        from quant_backtester.data.cache import get_daily
        result = get_daily("000001")
        assert len(result) == 0
        assert not os.path.exists(os.path.join(tmp, "000001.parquet"))


# ═══════════════════════════════════════════════════════════════
# get_weekly / get_monthly
# ═══════════════════════════════════════════════════════════════


class TestResample:
    def test_weekly_from_daily(self, isolated_cache):
        _, m = isolated_cache
        df = make_ohlcv(200)
        m.return_value = df

        from quant_backtester.data.cache import get_weekly
        weekly = get_weekly("000001")
        assert len(weekly) > 0
        assert len(weekly) < len(df)
        assert list(weekly.columns) == ["open", "close", "high", "low", "volume"]

    def test_weekly_empty(self, isolated_cache):
        _, m = isolated_cache
        m.return_value = pd.DataFrame()

        from quant_backtester.data.cache import get_weekly
        weekly = get_weekly("000001")
        assert len(weekly) == 0

    def test_monthly_from_daily(self, isolated_cache):
        _, m = isolated_cache
        m.return_value = make_ohlcv(200)

        from quant_backtester.data.cache import get_monthly
        monthly = get_monthly("000001")
        assert len(monthly) > 0
        assert len(monthly) < 200

    def test_monthly_empty(self, isolated_cache):
        _, m = isolated_cache
        m.return_value = pd.DataFrame()

        from quant_backtester.data.cache import get_monthly
        monthly = get_monthly("000001")
        assert len(monthly) == 0


# ═══════════════════════════════════════════════════════════════
# cache_* 工具函数
# ═══════════════════════════════════════════════════════════════


class TestCacheExists:
    def test_no_cache(self, isolated_cache):
        from quant_backtester.data.cache import cache_exists
        assert not cache_exists("nonexistent")

    def test_has_cache(self, isolated_cache):
        _, m = isolated_cache
        m.return_value = make_ohlcv(50)

        from quant_backtester.data.cache import get_daily, cache_exists
        get_daily("600000")
        assert cache_exists("600000")


class TestCacheStats:
    def test_empty_dir(self, isolated_cache):
        from quant_backtester.data.cache import cache_stats
        s = cache_stats()
        assert s["count"] == 0
        assert s["total_size_mb"] == 0

    def test_with_cached_stocks(self, isolated_cache):
        _, m = isolated_cache
        m.return_value = make_ohlcv(50)

        from quant_backtester.data.cache import get_daily, cache_stats
        get_daily("000001")
        get_daily("600001")

        s = cache_stats()
        assert s["count"] == 2
        assert s["total_size_mb"] > 0
