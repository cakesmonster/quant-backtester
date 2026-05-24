"""
单元测试 — 技术指标: MACD, KDJ, RSI, 布林带, ATR, 均线, 金叉死叉, 极值点。
"""

import numpy as np
import pandas as pd
import pytest

from quant_backtester.engine.indicators import (
    sma, ema, sma_multi, ema_multi, add_mas,
    macd, kdj, rsi,
    bollinger, atr, vol_ma,
    golden_cross, dead_cross,
    find_peaks, find_troughs,
)


# ═══════════════════════════════════════════════════════════════
# SMA / EMA
# ═══════════════════════════════════════════════════════════════

class TestSMA:
    def test_sma_basic(self):
        s = pd.Series([1, 2, 3, 4, 5], dtype=float)
        result = sma(s, 3)
        assert pd.isna(result.iloc[0])
        assert pd.isna(result.iloc[1])
        assert result.iloc[2] == 2.0
        assert result.iloc[3] == 3.0
        assert result.iloc[4] == 4.0

    def test_sma_all_same(self):
        s = pd.Series([5.0] * 10)
        result = sma(s, 5)
        assert result.iloc[-1] == 5.0


class TestEMA:
    def test_ema_basic(self):
        s = pd.Series([1, 2, 3, 4, 5], dtype=float)
        result = ema(s, 3)
        assert pd.notna(result.iloc[-1])
        assert result.iloc[-1] > 3.0

    def test_ema_follows_trend(self):
        """EMA 比 SMA 更快跟随趋势变化。"""
        s = pd.Series(list(range(1, 11)), dtype=float)
        ema3 = ema(s, 3)
        sma3 = sma(s, 3)
        assert ema3.iloc[-1] > sma3.iloc[-1]


# ═══════════════════════════════════════════════════════════════
# sma_multi / ema_multi / add_mas
# ═══════════════════════════════════════════════════════════════


class TestMultiMA:
    def test_sma_multi_columns(self):
        close = pd.Series(np.linspace(10, 20, 200), dtype=float)
        mas = sma_multi(close, [5, 10, 20])
        assert list(mas.columns) == ["ma5", "ma10", "ma20"]
        assert len(mas) == 200

    def test_sma_multi_values_consistent(self):
        close = pd.Series(np.linspace(10, 20, 200), dtype=float)
        mas = sma_multi(close, [5, 10])
        s5 = sma(close, 5)
        # 后段数据应一致
        assert (mas["ma5"].iloc[50:].round(6) == s5.iloc[50:].round(6)).all()

    def test_ema_multi(self):
        close = pd.Series(np.linspace(10, 20, 100), dtype=float)
        emas = ema_multi(close, [12, 26])
        assert list(emas.columns) == ["ema12", "ema26"]

    def test_add_mas_default_periods(self):
        import numpy as np
        df = pd.DataFrame({
            "open": np.linspace(10, 20, 100),
            "close": np.linspace(10, 20, 100),
            "high": np.linspace(11, 21, 100),
            "low": np.linspace(9, 19, 100),
            "volume": np.ones(100) * 1e6,
        })
        result = add_mas(df)
        assert "ma5" in result.columns
        assert "ma10" in result.columns
        assert "ma20" in result.columns
        assert "ma60" in result.columns
        # 原地修改
        assert result is df

    def test_add_mas_custom_periods(self):
        df = pd.DataFrame({
            "close": pd.Series(np.linspace(10, 20, 100), dtype=float),
        })
        add_mas(df, periods=[3, 7])
        assert "ma3" in df.columns
        assert "ma7" in df.columns
        assert "ma5" not in df.columns  # 不在自定义列表

    def test_add_mas_nan_prefix(self):
        """前 N-1 根 bar 的 MA 为 NaN。"""
        df = pd.DataFrame({
            "close": pd.Series(np.linspace(10, 20, 100), dtype=float),
        })
        add_mas(df, periods=[20])
        assert pd.isna(df["ma20"].iloc[0])
        assert pd.isna(df["ma20"].iloc[18])
        assert pd.notna(df["ma20"].iloc[19])  # 第 20 根有值


# ═══════════════════════════════════════════════════════════════
# MACD
# ═══════════════════════════════════════════════════════════════

class TestMACD:
    def test_macd_returns_three_series(self):
        close = pd.Series(np.random.randn(100).cumsum() + 10, dtype=float)
        dif, dea, hist = macd(close)
        assert len(dif) == 100
        assert len(dea) == 100
        assert len(hist) == 100

    def test_macd_nan_prefix(self):
        """前 slow-1 根 bar DIF 可能为 0（EMA 正在初始化）。"""
        close = pd.Series(np.random.randn(100).cumsum() + 10, dtype=float)
        dif, _, _ = macd(close, fast=12, slow=26, signal=9)
        # EMA 用 adjust=False，第一根 bar = 第一个数据点本身
        # DIF[0] = EMA12[0] - EMA26[0] = close[0] - close[0] = 0
        assert dif.iloc[0] == 0.0
        # 几根之后 DIF 就分化了
        assert dif.iloc[25] != 0.0

    def test_macd_hist_relation(self):
        """hist = 2 * (dif - dea)。"""
        close = pd.Series(np.random.randn(100).cumsum() + 10, dtype=float)
        dif, dea, hist = macd(close)
        for i in range(30, 100):
            if pd.notna(hist.iloc[i]):
                expected = 2 * (dif.iloc[i] - dea.iloc[i])
                assert abs(hist.iloc[i] - expected) < 1e-10

    def test_macd_uptrend_dif_positive(self):
        """持续上涨 → DIF 应 > 0。"""
        prices = pd.Series(np.linspace(10, 20, 200), dtype=float)
        dif, _, _ = macd(prices)
        # 后半段 DIF 应为正
        assert dif.iloc[-1] > 0

    def test_macd_downtrend_dif_negative(self):
        """持续下跌 → DIF 应 < 0。"""
        prices = pd.Series(np.linspace(20, 10, 200), dtype=float)
        dif, _, _ = macd(prices)
        assert dif.iloc[-1] < 0


# ═══════════════════════════════════════════════════════════════
# KDJ
# ═══════════════════════════════════════════════════════════════

class TestKDJ:
    def test_kdj_returns_three_series(self):
        n = 100
        close = pd.Series(np.random.randn(n).cumsum() + 10, dtype=float)
        high = close + 0.5
        low = close - 0.5
        k, d, j = kdj(high, low, close)
        assert len(k) == n
        assert len(d) == n
        assert len(j) == n

    def test_kdj_range_bound(self):
        """K/D 理论范围 0~100。"""
        close = pd.Series(np.random.randn(200).cumsum() + 10, dtype=float)
        high = close + 1.0
        low = close - 1.0
        k, d, j = kdj(high, low, close)
        # 后期数据应稳定在 0~100
        valid_k = k.iloc[20:]
        valid_d = d.iloc[20:]
        assert valid_k.min() >= -1  # 浮点误差
        assert valid_k.max() <= 101
        assert valid_d.min() >= -1
        assert valid_d.max() <= 101

    def test_kdj_nan_prefix(self):
        """KDJ 的 RSV fillna(50)，所以第一根不是 NaN。"""
        close = pd.Series(np.random.randn(50).cumsum() + 10, dtype=float)
        high = close + 0.5
        low = close - 0.5
        k, d, j = kdj(high, low, close, n=9)
        # RSV 在数据不足时 fillna(50)，所以 K 不为 NaN
        assert pd.notna(k.iloc[0])  # 填了50
        assert pd.notna(k.iloc[8])  # 第9根有真实数据

    def test_kdj_j_formula(self):
        """J = 3K - 2D。"""
        close = pd.Series(np.random.randn(100).cumsum() + 10, dtype=float)
        high = close + 0.5
        low = close - 0.5
        k, d, j = kdj(high, low, close)
        for i in range(20, 100):
            expected = 3 * k.iloc[i] - 2 * d.iloc[i]
            assert abs(j.iloc[i] - expected) < 1e-10

    def test_kdj_uptrend_k_high(self):
        """持续上涨后期 K 值应该较高。"""
        prices = pd.Series(np.linspace(10, 20, 200), dtype=float)
        high = prices + 0.1
        low = prices - 0.1
        k, d, j = kdj(high, low, prices)
        assert k.iloc[-1] > 50  # 上涨中 K 应在高位

    def test_kdj_downtrend_k_low(self):
        """持续下跌后期 K 值应该较低。"""
        prices = pd.Series(np.linspace(20, 10, 200), dtype=float)
        high = prices + 0.1
        low = prices - 0.1
        k, d, j = kdj(high, low, prices)
        assert k.iloc[-1] < 50  # 下跌中 K 应在低位


# ═══════════════════════════════════════════════════════════════
# RSI
# ═══════════════════════════════════════════════════════════════

class TestRSI:
    def test_rsi_range(self):
        close = pd.Series(np.random.randn(200).cumsum() + 10, dtype=float)
        r = rsi(close, 14)
        valid = r.iloc[30:]
        assert valid.min() >= 0
        assert valid.max() <= 100

    def test_rsi_uptrend_high(self):
        """纯上升 → RSI 偏高。"""
        close = pd.Series(np.linspace(10, 20, 200), dtype=float)
        r = rsi(close, 14)
        assert r.iloc[-1] > 50

    def test_rsi_downtrend_low(self):
        """纯下跌 → RSI 偏低。"""
        close = pd.Series(np.linspace(20, 10, 200), dtype=float)
        r = rsi(close, 14)
        assert r.iloc[-1] < 50


# ═══════════════════════════════════════════════════════════════
# 布林带 / ATR / VOL_MA
# ═══════════════════════════════════════════════════════════════

class TestBollinger:
    def test_bands_order(self):
        close = pd.Series(np.random.randn(200).cumsum() + 10, dtype=float)
        upper, middle, lower = bollinger(close, 20, 2.0)
        valid = slice(40, None)
        assert (upper.iloc[valid] >= middle.iloc[valid]).all()
        assert (middle.iloc[valid] >= lower.iloc[valid]).all()

    def test_bollinger_narrow_price(self):
        """窄幅震荡 → 带宽窄。"""
        close = pd.Series([10.0 + np.sin(i * 0.01) * 0.1 for i in range(100)], dtype=float)
        upper, middle, lower = bollinger(close, 20, 2.0)
        bandwidth = (upper.iloc[-1] - lower.iloc[-1]) / middle.iloc[-1]
        assert bandwidth < 0.1  # 很窄


class TestATR:
    def test_atr_positive(self):
        close = pd.Series(np.random.randn(200).cumsum() + 10, dtype=float)
        high = close + 0.5
        low = close - 0.5
        a = atr(high, low, close, 14)
        valid = a.iloc[30:]
        assert (valid > 0).all()


class TestVolMA:
    def test_vol_ma_basic(self):
        vol = pd.Series([1_000_000, 2_000_000, 3_000_000, 4_000_000, 5_000_000], dtype=float)
        result = vol_ma(vol, 3)
        assert result.iloc[2] == 2_000_000
        assert result.iloc[3] == 3_000_000
        assert result.iloc[4] == 4_000_000


# ═══════════════════════════════════════════════════════════════
# 金叉 / 死叉
# ═══════════════════════════════════════════════════════════════

class TestCrossSignals:
    def test_golden_cross_detected(self):
        """fast 从下方上穿 slow。"""
        fast = pd.Series([1, 2, 3, 4, 5], dtype=float)
        slow = pd.Series([3, 3, 3, 3, 3], dtype=float)
        gc = golden_cross(fast, slow)
        assert not gc.iloc[0]
        assert not gc.iloc[1]
        assert not gc.iloc[2]  # fast=3 == slow=3, 不算金叉
        assert gc.iloc[3]      # fast=4 > slow=3, prev fast=3 <= slow=3 ✓
        assert not gc.iloc[4]

    def test_dead_cross_detected(self):
        """fast 从上方下穿 slow。"""
        fast = pd.Series([5, 4, 3, 2, 1], dtype=float)
        slow = pd.Series([3, 3, 3, 3, 3], dtype=float)
        dc = dead_cross(fast, slow)
        assert not dc.iloc[0]
        assert not dc.iloc[1]
        assert not dc.iloc[2]  # fast=3 == slow=3, 不算死叉
        assert dc.iloc[3]      # fast=2 < slow=3, prev fast=3 >= slow=3 ✓
        assert not dc.iloc[4]

    def test_no_cross_when_parallel(self):
        """两条线始终分离 → 无交叉。"""
        fast = pd.Series([1, 2, 3, 4, 5], dtype=float)
        slow = pd.Series([0, 0, 0, 0, 0], dtype=float)
        gc = golden_cross(fast, slow)
        dc = dead_cross(fast, slow)
        assert not gc.any()
        assert not dc.any()

    def test_golden_cross_single_day(self):
        """金叉只持续一天。"""
        fast = pd.Series([3, 4, 5], dtype=float)
        slow = pd.Series([3, 3, 3], dtype=float)
        gc = golden_cross(fast, slow)
        assert gc.sum() == 1


# ═══════════════════════════════════════════════════════════════
# 极值点检测
# ═══════════════════════════════════════════════════════════════

class TestExtremaDetection:
    def test_find_peaks_simple(self):
        s = pd.Series([1, 3, 2, 5, 4, 6, 3, 7, 5], dtype=float)
        # order=1 → 每个局部高点
        peaks = find_peaks(s, order=1)
        # 分析: peak at idx 1 (3), idx 3 (5), idx 5 (6), idx 7 (7)
        # But order=1, scipy argrelextrema with order=1 will find points > neighbors
        peak_indices = np.where(peaks.values)[0]
        assert len(peak_indices) >= 2

    def test_find_troughs_simple(self):
        s = pd.Series([5, 2, 4, 1, 3, 0, 2], dtype=float)
        troughs = find_troughs(s, order=1)
        trough_indices = np.where(troughs.values)[0]
        assert len(trough_indices) >= 1

    def test_peaks_not_at_start_end(self):
        """极值点检测不会把首尾当极值。"""
        s = pd.Series(range(100), dtype=float)
        peaks = find_peaks(s, order=3)
        assert not peaks.iloc[0]
        assert not peaks.iloc[-1]

    def test_flat_series_no_extrema(self):
        s = pd.Series([5.0] * 50)
        peaks = find_peaks(s, order=3)
        troughs = find_troughs(s, order=3)
        assert not peaks.any()
        assert not troughs.any()
