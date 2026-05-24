"""
单元测试 — 股票池: 全市场列表 + 排除规则 + 随机采样。

mock _build_pool 或 mock mootdx.quotes.Quotes（函数内 import）。
"""

import json
import os
import tempfile
from unittest import mock

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def _clear_pool_cache():
    """每个测试前后清除进程内股票池缓存。"""
    import quant_backtester.data.stock_pool as sp
    sp._pool_cache = None
    yield
    sp._pool_cache = None


@pytest.fixture
def isolated_pool():
    """临时 STOCK_POOL_FILE。"""
    with tempfile.TemporaryDirectory() as tmp:
        pool_file = os.path.join(tmp, "stock_pool.json")
        with mock.patch("quant_backtester.data.stock_pool.STOCK_POOL_FILE", pool_file):
            yield pool_file


def _set_pool(codes: list[str], pool_file: str):
    os.makedirs(os.path.dirname(pool_file), exist_ok=True)
    with open(pool_file, "w") as f:
        json.dump({"updated": "2024-01-01", "count": len(codes), "codes": codes}, f)


# ═══════════════════════════════════════════════════════════════
# random_sample
# ═══════════════════════════════════════════════════════════════


class TestRandomSample:
    def test_sample_all(self, isolated_pool):
        codes = [f"0000{i:02d}" for i in range(1, 6)] + [f"6000{i:02d}" for i in range(1, 6)]
        _set_pool(codes, isolated_pool)
        from quant_backtester.data.stock_pool import random_sample
        result = random_sample(100)
        assert sorted(result) == sorted(codes)

    def test_sample_subset(self, isolated_pool):
        codes = [f"0000{i:02d}" for i in range(1, 51)]
        _set_pool(codes, isolated_pool)
        from quant_backtester.data.stock_pool import random_sample
        result = random_sample(10)
        assert len(result) == 10
        assert all(c in codes for c in result)

    def test_seed_reproducible(self, isolated_pool):
        codes = [f"0000{i:02d}" for i in range(1, 101)]
        _set_pool(codes, isolated_pool)
        from quant_backtester.data.stock_pool import random_sample
        r1 = random_sample(10, seed=42)
        r2 = random_sample(10, seed=42)
        assert r1 == r2

    def test_different_seeds_differ(self, isolated_pool):
        codes = [f"0000{i:02d}" for i in range(1, 101)]
        _set_pool(codes, isolated_pool)
        from quant_backtester.data.stock_pool import random_sample
        r1 = random_sample(10, seed=1)
        r2 = random_sample(10, seed=2)
        assert r1 != r2


# ═══════════════════════════════════════════════════════════════
# 缓存 / 去重 / 容错
# ═══════════════════════════════════════════════════════════════


class TestPoolCache:
    def test_cached_in_memory(self, isolated_pool):
        _set_pool(["000001", "000002", "600001"], isolated_pool)
        from quant_backtester.data.stock_pool import get_pool
        pool1 = get_pool()
        pool2 = get_pool()
        assert pool1 == pool2
        assert pool1 is pool2

    def test_corrupt_json_rebuilds(self):
        import quant_backtester.data.stock_pool as sp
        sp._pool_cache = None

        with tempfile.TemporaryDirectory() as tmp:
            pool_file = os.path.join(tmp, "stock_pool.json")
            with open(pool_file, "w") as f:
                f.write("not json")

            with mock.patch("quant_backtester.data.stock_pool.STOCK_POOL_FILE", pool_file):
                with mock.patch("quant_backtester.data.stock_pool._build_pool") as m:
                    m.return_value = ["000001", "600001"]
                    pool = sp._load_pool()
                    assert pool == ["000001", "600001"]

    def test_empty_json_triggers_rebuild(self):
        import quant_backtester.data.stock_pool as sp
        sp._pool_cache = None

        with tempfile.TemporaryDirectory() as tmp:
            pool_file = os.path.join(tmp, "stock_pool.json")
            _set_pool([], pool_file)

            with mock.patch("quant_backtester.data.stock_pool.STOCK_POOL_FILE", pool_file):
                with mock.patch("quant_backtester.data.stock_pool._build_pool") as m:
                    m.return_value = ["000001"]
                    pool = sp._load_pool()
                    assert pool == ["000001"]


class TestPoolStats:
    def test_stats(self, isolated_pool):
        _set_pool(["000001", "000002", "000003", "600001"], isolated_pool)
        from quant_backtester.data.stock_pool import pool_stats
        s = pool_stats()
        assert s["total"] == 4
        assert "last_updated" in s


# ═══════════════════════════════════════════════════════════════
# _build_pool — 过滤规则（mock mootdx.quotes.Quotes）
# ═══════════════════════════════════════════════════════════════


def _mock_mootdx(stocks_side_effect):
    """mock mootdx.quotes.Quotes（_build_pool 内部 `from mootdx.quotes import Quotes`）。"""
    client = mock.MagicMock()
    client.stocks.side_effect = stocks_side_effect
    return mock.patch(
        "mootdx.quotes.Quotes",
        **{"factory.return_value": client},
    )


class TestBuildPoolFilters:
    def test_keeps_main_board_only(self):
        import quant_backtester.data.stock_pool as sp

        def _stocks(market):
            if market == 0:
                return pd.DataFrame({"code": ["000001", "300001", "688001"]})
            return pd.DataFrame({"code": ["600001", "800001", "900001"]})

        with _mock_mootdx(_stocks):
            pool = sp._build_pool()

        assert "000001" in pool
        assert "600001" in pool
        assert "300001" not in pool
        assert "688001" not in pool
        assert "800001" not in pool
        assert "900001" not in pool

    def test_code_padded_to_6_digits(self):
        import quant_backtester.data.stock_pool as sp

        def _stocks(market):
            return pd.DataFrame({"code": ["1", "600"]})

        with _mock_mootdx(_stocks):
            pool = sp._build_pool()

        assert "000001" in pool
        assert "000600" in pool  # "600" → zfill(6) → "000600", 以 "00" 开头

    def test_one_market_failure_doesnt_block(self):
        import quant_backtester.data.stock_pool as sp

        def _stocks(market):
            if market == 0:
                raise RuntimeError("深圳宕机")
            return pd.DataFrame({"code": ["600001", "600002"]})

        with _mock_mootdx(_stocks):
            pool = sp._build_pool()

        assert "600001" in pool
        assert "600002" in pool

    def test_dedup(self):
        import quant_backtester.data.stock_pool as sp

        def _stocks(market):
            if market == 0:
                return pd.DataFrame({"code": ["000001", "000002"]})
            return pd.DataFrame({"code": ["000002", "600001"]})

        with _mock_mootdx(_stocks):
            pool = sp._build_pool()

        assert pool.count("000002") == 1

    def test_excludes_300_when_enabled(self):
        import quant_backtester.data.stock_pool as sp

        def _stocks(market):
            return pd.DataFrame({"code": ["000001", "300001", "300002"]})

        with _mock_mootdx(_stocks):
            with mock.patch("quant_backtester.data.stock_pool.EXCLUDE_300", True):
                pool = sp._build_pool()

        assert "000001" in pool
        assert "300001" not in pool
        assert "300002" not in pool
