"""
均线趋势策略 — 日线 MA5 上穿 MA10 买入（周线多头确认），RSI>80 或跌破 MA5 卖出。
"""

from quant_backtester.strategies.base import BaseStrategy, Order
from quant_backtester.engine.indicators import add_mas, rsi


class MATrend(BaseStrategy):
    name = "均线趋势"
    description = "日线 MA5 上穿 MA10 买入(周线多头确认)，RSI>80 或跌破 MA5 卖出"

    def init(self):
        # 日线均线
        add_mas(self.daily)
        # 日线 RSI
        self.daily["rsi"] = rsi(self.daily["close"], n=14)
        # 周线均线
        add_mas(self.weekly, periods=[5, 10, 20])
        # 月线均线
        add_mas(self.monthly, periods=[3, 5, 10])

    def next(self, i: int) -> list[Order]:
        if i < 60:
            return []

        ma5 = self.daily["ma5"].iloc[i]
        ma10 = self.daily["ma10"].iloc[i]
        prev_ma5 = self.daily["ma5"].iloc[i - 1]
        prev_ma10 = self.daily["ma10"].iloc[i - 1]

        close = self.daily["close"].iloc[i]
        rsi_val = self.daily["rsi"].iloc[i]

        # 周线趋势确认（避免逆势做多）
        w_ma5 = self.weekly["ma5"].iloc[i]
        w_ma10 = self.weekly["ma10"].iloc[i]

        # 买入：日线 MA5 上穿 MA10 + 周线多头排列
        if ma5 > ma10 and prev_ma5 <= prev_ma10 and w_ma5 > w_ma10:
            return [Order.buy(pct=1.0, reason="MA5上穿MA10(日)+周线多头")]

        # 卖出：RSI > 80（超买）或 跌破 MA5
        if rsi_val > 80:
            return [Order.sell(pct=1.0, reason=f"RSI超买({rsi_val:.0f})")]
        if close < ma5:
            return [Order.sell(pct=1.0, reason="跌破MA5")]

        return []
