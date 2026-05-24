"""
单元测试 — 通达信数据拉取: fetch_daily / fetch_weekly / fetch_monthly。

mock _get_client() 返回 mock Quotes，验证列映射/空数据处理/分页循环。
"""

from unittest import mock

import pandas as pd
import pytest


def _make_k_df(dates: list[str], close_prices: list[float]) -> pd.DataFrame:
    """构造 mootdx k() 返回格式（带 vol 列）。"""
    data = []
    for d, c in zip(dates, close_prices):
        data.append({
            "open": round(c * 0.99, 2),
            "close": c,
            "high": round(c * 1.02, 2),
            "low": round(c * 0.98, 2),
            "vol": 10_000_000,
        })
    return pd.DataFrame(data, index=pd.DatetimeIndex(
        [pd.Timestamp(d) for d in dates]
    ))


def _make_bars_df(n: int) -> pd.DataFrame:
    """构造 mootdx bars() 返回格式。"""
    import numpy as np
    rng = np.random.RandomState(42)
    prices = 10 + np.cumsum(rng.normal(0, 0.5, n))
    data = []
    for i in range(n):
        c = round(float(prices[i]), 2)
        data.append({
            "open": round(c * 0.99, 2),
            "close": c,
            "high": round(c * 1.02, 2),
            "low": round(c * 0.98, 2),
            "vol": 10_000_000,
        })
    dates = pd.date_range("2015-01-01", periods=n, freq="W-FRI")
    return pd.DataFrame(data, index=dates)


@pytest.fixture(autouse=True)
def _mock_get_client():
    """每个测试 mock _get_client() 返回独立 mock client，避免单例污染。"""
    client = mock.MagicMock()
    with mock.patch(
        "quant_backtester.data.fetcher._get_client",
        return_value=client,
    ) as m:
        m.client = client  # 附加到 mock 对象上方便测试访问
        yield m


# ═══════════════════════════════════════════════════════════════
# fetch_daily
# ═══════════════════════════════════════════════════════════════


class TestFetchDaily:
    def test_basic(self, _mock_get_client):
        c = _mock_get_client.client
        df = _make_k_df(["2020-01-02", "2020-01-03", "2020-01-06"], [10.0, 10.5, 11.0])
        c.k.return_value = df

        from quant_backtester.data.fetcher import fetch_daily
        result = fetch_daily("000001", "2020-01-01", "2020-12-31")

        assert len(result) == 3
        assert list(result.columns) == ["open", "close", "high", "low", "volume"]
        assert result.iloc[-1]["close"] == 11.0

    def test_empty_result(self, _mock_get_client):
        c = _mock_get_client.client
        c.k.return_value = None

        from quant_backtester.data.fetcher import fetch_daily
        result = fetch_daily("000001", "2020-01-01", "2020-12-31")

        assert len(result) == 0

    def test_empty_dataframe(self, _mock_get_client):
        c = _mock_get_client.client
        c.k.return_value = pd.DataFrame()

        from quant_backtester.data.fetcher import fetch_daily
        result = fetch_daily("000001", "2020-01-01", "2020-12-31")

        assert len(result) == 0

    def test_keyerror_is_handled(self, _mock_get_client):
        c = _mock_get_client.client
        c.k.side_effect = KeyError("no data")

        from quant_backtester.data.fetcher import fetch_daily
        result = fetch_daily("bond_code", "2020-01-01", "2020-12-31")

        assert len(result) == 0

    def test_other_exception_raised(self, _mock_get_client):
        c = _mock_get_client.client
        c.k.side_effect = ConnectionError("网络错误")

        from quant_backtester.data.fetcher import fetch_daily
        with pytest.raises(RuntimeError, match="拉取"):
            fetch_daily("000001", "2020-01-01", "2020-12-31")

    def test_vol_renamed_to_volume(self, _mock_get_client):
        c = _mock_get_client.client
        df = _make_k_df(["2020-01-02"], [10.0])
        c.k.return_value = df

        from quant_backtester.data.fetcher import fetch_daily
        result = fetch_daily("000001", "2020-01-01", "2020-12-31")

        assert "volume" in result.columns
        assert "vol" not in result.columns

    def test_extra_columns_stripped(self, _mock_get_client):
        c = _mock_get_client.client
        df = _make_k_df(["2020-01-02"], [10.0])
        df["amount"] = 100_000_000
        c.k.return_value = df

        from quant_backtester.data.fetcher import fetch_daily
        result = fetch_daily("000001", "2020-01-01", "2020-12-31")

        assert "amount" not in result.columns


# ═══════════════════════════════════════════════════════════════
# fetch_daily_latest_date
# ═══════════════════════════════════════════════════════════════


class TestFetchDailyLatestDate:
    def test_returns_date(self, _mock_get_client):
        c = _mock_get_client.client
        df = _make_k_df(["2024-06-15"], [10.0])
        c.k.return_value = df

        from quant_backtester.data.fetcher import fetch_daily_latest_date
        result = fetch_daily_latest_date("000001")

        assert result == "2024-06-15"

    def test_returns_empty_when_no_data(self, _mock_get_client):
        c = _mock_get_client.client
        c.k.return_value = pd.DataFrame()

        from quant_backtester.data.fetcher import fetch_daily_latest_date
        result = fetch_daily_latest_date("000001")

        assert result == ""


# ═══════════════════════════════════════════════════════════════
# _fetch_bars (周线/月线内部实现)
# ═══════════════════════════════════════════════════════════════


class TestFetchBars:
    def test_single_page(self, _mock_get_client):
        c = _mock_get_client.client
        df = _make_bars_df(50)
        c.bars.return_value = df

        from quant_backtester.data.fetcher import _fetch_bars
        result = _fetch_bars("000001", "week")

        assert len(result) == 50
        c.bars.assert_called_once()

    def test_multi_page(self, _mock_get_client):
        c = _mock_get_client.client
        df1 = _make_bars_df(800)
        df2 = _make_bars_df(200)
        c.bars.side_effect = [df1, df2]

        from quant_backtester.data.fetcher import _fetch_bars
        result = _fetch_bars("000001", "week")

        assert len(result) == 1000
        assert c.bars.call_count == 2

    def test_empty(self, _mock_get_client):
        c = _mock_get_client.client
        c.bars.return_value = pd.DataFrame()

        from quant_backtester.data.fetcher import _fetch_bars
        result = _fetch_bars("000001", "week")

        assert len(result) == 0

    def test_vol_renamed(self, _mock_get_client):
        c = _mock_get_client.client
        df = _make_bars_df(10)
        c.bars.return_value = df

        from quant_backtester.data.fetcher import _fetch_bars
        result = _fetch_bars("000001", "week")

        assert "vol" not in result.columns
        assert "volume" in result.columns


# ═══════════════════════════════════════════════════════════════
# fetch_weekly / fetch_monthly
# ═══════════════════════════════════════════════════════════════


class TestFetchWeekly:
    def test_delegates_to_fetch_bars(self, _mock_get_client):
        c = _mock_get_client.client
        c.bars.return_value = _make_bars_df(100)

        from quant_backtester.data.fetcher import fetch_weekly
        result = fetch_weekly("000001")

        assert len(result) == 100


class TestFetchMonthly:
    def test_delegates_to_fetch_bars(self, _mock_get_client):
        c = _mock_get_client.client
        c.bars.return_value = _make_bars_df(60)

        from quant_backtester.data.fetcher import fetch_monthly
        result = fetch_monthly("000001")

        assert len(result) == 60
