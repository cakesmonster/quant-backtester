"""
MACD 顶底背离策略。

买入（底背离）：股价创新低，MACD DIF 未创新低
卖出（顶背离）：股价创新高，MACD DIF 未创新高
"""

import numpy as np

from quant_backtester.strategies.base import BaseStrategy, Order
from quant_backtester.engine.indicators import macd, find_peaks, find_troughs


class MACDDivergence(BaseStrategy):
    name = "MACD顶底背离"
    description = "日线MACD底背离买入，顶背离卖出"

    # 可调参数
    LOOKBACK = 60       # 回看多少天找极值点
    PEAK_ORDER = 5      # 极值点邻域大小

    def init(self):
        close = self.daily["close"]
        self.dif, self.dea, _ = macd(close)

    def _check_bullish_divergence(self, i: int) -> bool:
        """底背离：价格低点更低，DIF低点更高。"""
        if i < self.LOOKBACK:
            return False

        window_p = self.daily["close"].iloc[max(0, i - self.LOOKBACK):i + 1]
        window_d = self.dif.iloc[max(0, i - self.LOOKBACK):i + 1]

        troughs_p = find_troughs(window_p, order=self.PEAK_ORDER)
        troughs_d = find_troughs(window_d, order=self.PEAK_ORDER)

        if troughs_p.sum() < 2 or troughs_d.sum() < 2:
            return False

        # 取最近两个低点
        p_idx = np.where(troughs_p.values)[0][-2:]
        d_idx = np.where(troughs_d.values)[0][-2:]

        p1, p2 = window_p.iloc[p_idx[0]], window_p.iloc[p_idx[1]]
        d1, d2 = window_d.iloc[d_idx[0]], window_d.iloc[d_idx[1]]

        # 价格低点更低 + DIF 低点更高 = 底背离
        return bool(p2 < p1 and d2 > d1)

    def _check_bearish_divergence(self, i: int) -> bool:
        """顶背离：价格高点更高，DIF高点更低。"""
        if i < self.LOOKBACK:
            return False

        window_p = self.daily["close"].iloc[max(0, i - self.LOOKBACK):i + 1]
        window_d = self.dif.iloc[max(0, i - self.LOOKBACK):i + 1]

        peaks_p = find_peaks(window_p, order=self.PEAK_ORDER)
        peaks_d = find_peaks(window_d, order=self.PEAK_ORDER)

        if peaks_p.sum() < 2 or peaks_d.sum() < 2:
            return False

        p_idx = np.where(peaks_p.values)[0][-2:]
        d_idx = np.where(peaks_d.values)[0][-2:]

        p1, p2 = window_p.iloc[p_idx[0]], window_p.iloc[p_idx[1]]
        d1, d2 = window_d.iloc[d_idx[0]], window_d.iloc[d_idx[1]]

        # 价格高点更高 + DIF 高点更低 = 顶背离
        return bool(p2 > p1 and d2 < d1)

    def next(self, i: int) -> list[Order]:
        if i < 26:
            return []

        if self._check_bullish_divergence(i):
            return [Order.buy(pct=1.0, reason="MACD底背离")]

        if self._check_bearish_divergence(i):
            return [Order.sell(pct=1.0, reason="MACD顶背离")]

        return []
