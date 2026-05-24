"""MACD 金叉死叉策略 — 用于验证回测框架。"""

from quant_backtester.strategies.base import BaseStrategy, Order
from quant_backtester.engine.indicators import macd, golden_cross, dead_cross


class MACDCross(BaseStrategy):
    name = "MACD金叉死叉"
    description = "日线MACD金叉买入，死叉卖出"

    def init(self):
        close = self.daily["close"]
        self.dif, self.dea, self.hist = macd(close, fast=12, slow=26, signal=9)
        self.golden = golden_cross(self.dif, self.dea)
        self.dead = dead_cross(self.dif, self.dea)

    def next(self, i: int) -> list[Order]:
        if i < 26:  # MACD 需要足够数据
            return []

        if self.golden.iloc[i]:
            return [Order.buy(pct=1.0, reason="MACD金叉")]

        if self.dead.iloc[i]:
            return [Order.sell(pct=1.0, reason="MACD死叉")]

        return []
