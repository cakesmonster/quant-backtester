"""
多头排列策略 — MA5>MA10>MA20>MA60 趋势向上，MA5上穿MA10买入，跌破MA5卖出。
"""

from quant_backtester.strategies.base import BaseStrategy, Order
from quant_backtester.engine.indicators import add_mas


class MALongAlignment(BaseStrategy):
    name = "多头排列"
    description = "MA5>10>20>60趋势向上，MA5上穿MA10买入，跌破MA5卖出"

    def init(self):
        add_mas(self.daily, periods=[5, 10, 20, 60])

    def next(self, i: int) -> list[Order]:
        if i < 60:
            return []

        ma5 = self.daily["ma5"].iloc[i]
        ma10 = self.daily["ma10"].iloc[i]
        ma20 = self.daily["ma20"].iloc[i]
        ma60 = self.daily["ma60"].iloc[i]
        close = self.daily["close"].iloc[i]

        # 卖出：跌破 MA5
        if self.has_position and close < ma5:
            return [Order.sell(pct=1.0, reason=f"跌破MA5 ({close:.2f}<{ma5:.2f})")]

        # 多头排列：MA5 > MA10 > MA20 > MA60，且方向向上
        if not (ma5 > ma10 > ma20 > ma60):
            return []
        prev_ma5 = self.daily["ma5"].iloc[i - 1]
        prev_ma10 = self.daily["ma10"].iloc[i - 1]
        prev_ma20 = self.daily["ma20"].iloc[i - 1]
        prev_ma60 = self.daily["ma60"].iloc[i - 1]
        if not (ma5 > prev_ma5 and ma10 > prev_ma10 and ma20 > prev_ma20 and ma60 > prev_ma60):
            return []

        # 买入：MA5 上穿 MA10
        if ma5 > ma10 and prev_ma5 <= prev_ma10:
            return [Order.buy(pct=1.0, reason="MA5上穿MA10(多头排列)")]

        return []
