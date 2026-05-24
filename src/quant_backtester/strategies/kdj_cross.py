"""
KDJ 金叉死叉策略。

买入：K 上穿 D（金叉）
卖出：K 下穿 D（死叉）、J > 100、K > 80
"""

from quant_backtester.strategies.base import BaseStrategy, Order
from quant_backtester.engine.indicators import kdj, golden_cross, dead_cross


class KDJCross(BaseStrategy):
    name = "KDJ金叉死叉"
    description = "日线KDJ金叉买入，死叉/J>100/K>80卖出"

    N = 9
    K_PERIOD = 3
    D_PERIOD = 3

    def init(self):
        self.k, self.d, self.j = kdj(
            self.daily["high"],
            self.daily["low"],
            self.daily["close"],
            n=self.N,
            k_period=self.K_PERIOD,
            d_period=self.D_PERIOD,
        )
        self.golden = golden_cross(self.k, self.d)
        self.dead = dead_cross(self.k, self.d)

    def next(self, i: int) -> list[Order]:
        if i < self.N:
            return []

        orders = []

        # 卖出条件
        should_sell = (
            self.dead.iloc[i] or
            self.j.iloc[i] > 100 or
            self.k.iloc[i] > 80
        )
        if should_sell:
            if self.dead.iloc[i]:
                orders.append(Order.sell(pct=1.0, reason="KDJ死叉"))
            elif self.j.iloc[i] > 100:
                orders.append(Order.sell(pct=1.0, reason=f"KDJ超买 J={self.j.iloc[i]:.0f}"))
            elif self.k.iloc[i] > 80:
                orders.append(Order.sell(pct=1.0, reason=f"KDJ超买 K={self.k.iloc[i]:.0f}"))

        # 买入
        if self.golden.iloc[i]:
            orders.append(Order.buy(pct=1.0, reason="KDJ金叉"))

        return orders
