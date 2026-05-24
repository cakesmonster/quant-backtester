"""
周线 KDJ + 日线 KDJ 联动策略。

- 周K KDJ 金叉区间 → 允许日线操作
- 日K KDJ 金叉 → 买入
- 日K KDJ 死叉 / J>100 / K>80 → 卖出
- 周K KDJ 死叉 → 强制清仓
"""

import pandas as pd

from quant_backtester.strategies.base import BaseStrategy, Order
from quant_backtester.engine.indicators import kdj, golden_cross, dead_cross


class WeeklyDailyKDJ(BaseStrategy):
    name = "周线+日线KDJ联动"
    description = "周K金叉区间内，日K金叉买；日K死叉/J>100/K>80卖；周K死叉强制清仓"

    N = 9
    K_PERIOD = 3
    D_PERIOD = 3

    def init(self):
        # 日线 KDJ
        self.dk, self.dd, self.dj = kdj(
            self.daily["high"], self.daily["low"], self.daily["close"],
            n=self.N, k_period=self.K_PERIOD, d_period=self.D_PERIOD,
        )
        self.d_golden = golden_cross(self.dk, self.dd)
        self.d_dead = dead_cross(self.dk, self.dd)

        # 周线 KDJ
        self.wk, self.wd, self.wj = kdj(
            self.weekly["high"], self.weekly["low"], self.weekly["close"],
            n=self.N, k_period=self.K_PERIOD, d_period=self.D_PERIOD,
        )

    def _weekly_golden_zone(self, i: int) -> bool:
        """当前是否处于周K金叉区间（周K > 周D）。"""
        if i < self.N:
            return False
        wk_val = self.wk.iloc[i]
        wd_val = self.wd.iloc[i]
        if pd.isna(wk_val) or pd.isna(wd_val):
            return False
        return bool(wk_val > wd_val)

    def _weekly_dead_zone(self, i: int) -> bool:
        """当前是否处于周K死叉区间（周K < 周D）。"""
        if i < self.N:
            return False
        wk_val = self.wk.iloc[i]
        wd_val = self.wd.iloc[i]
        if pd.isna(wk_val) or pd.isna(wd_val):
            return False
        return bool(wk_val < wd_val)

    def next(self, i: int) -> list[Order]:
        if i < self.N * 2:  # 需要足够周线和日线数据
            return []

        orders = []

        # 周K死叉 → 强制清仓（最高优先级）
        if self._weekly_dead_zone(i):
            return [Order.sell(pct=1.0, reason="周K死叉清仓")]

        # 在周K金叉区间内
        if self._weekly_golden_zone(i):
            # 日线卖出
            if self.d_dead.iloc[i]:
                orders.append(Order.sell(pct=1.0, reason="日K死叉(周金叉)"))

            if pd.notna(self.dj.iloc[i]) and self.dj.iloc[i] > 100:
                orders.append(Order.sell(pct=1.0, reason=f"日J超买={self.dj.iloc[i]:.0f}(周金叉)"))

            if pd.notna(self.dk.iloc[i]) and self.dk.iloc[i] > 80:
                orders.append(Order.sell(pct=1.0, reason=f"日K超买={self.dk.iloc[i]:.0f}(周金叉)"))

            # 日线买入
            if self.d_golden.iloc[i]:
                orders.append(Order.buy(pct=1.0, reason="日K金叉(周金叉)"))

        return orders
