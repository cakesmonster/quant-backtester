"""
均线趋势策略 — 验证 add_mas 日周月K 三周期均线。
"""

from quant_backtester.strategies.base import BaseStrategy, Order
from quant_backtester.engine.indicators import add_mas


class MATrend(BaseStrategy):
    name = "均线趋势"
    description = "日线 MA5>MA20 买入，MA5<MA20 卖出；周月线参考"

    def init(self):
        # 日线均线
        add_mas(self.daily)
        # 周线均线
        add_mas(self.weekly, periods=[5, 10, 20])
        # 月线均线
        add_mas(self.monthly, periods=[3, 5, 10])

    def next(self, i: int) -> list[Order]:
        if i < 60:
            return []

        ma5 = self.daily["ma5"].iloc[i]
        ma20 = self.daily["ma20"].iloc[i]
        prev_ma5 = self.daily["ma5"].iloc[i - 1]
        prev_ma20 = self.daily["ma20"].iloc[i - 1]

        # 周线趋势确认（避免逆势做多）
        w_ma5 = self.weekly["ma5"].iloc[i]
        w_ma20 = self.weekly["ma20"].iloc[i]

        # 买入：日线金叉 + 周线多头排列
        if ma5 > ma20 and prev_ma5 <= prev_ma20 and w_ma5 > w_ma20:
            return [Order.buy(pct=1.0, reason="MA5上穿MA20(日)+周线多头")]

        # 卖出：日线死叉
        if ma5 < ma20 and prev_ma5 >= prev_ma20:
            return [Order.sell(pct=1.0, reason="MA5下穿MA20")]

        return []
