"""
策略基类 — 所有策略必须继承 BaseStrategy，实现 init() 和 next()。

同时定义 Order 交易指令和 Signal 信号枚举。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd


@dataclass
class Order:
    """单笔交易指令。

    action: 'buy' 买入 / 'sell' 卖出
    pct:    比例 (买入=仓位%, 卖出=持仓%)
    reason: 原因备注（交易记录用）
    """

    action: Literal["buy", "sell"]
    pct: float
    reason: str = ""

    @classmethod
    def buy(cls, pct: float = 1.0, reason: str = "") -> "Order":
        return cls(action="buy", pct=pct, reason=reason)

    @classmethod
    def sell(cls, pct: float = 1.0, reason: str = "") -> "Order":
        return cls(action="sell", pct=pct, reason=reason)


class BaseStrategy(ABC):
    """策略抽象基类。

    子类必须定义:
      - name: str        策略名称（显示在看板）
      - description: str 一句话描述
      - init()           回测前初始化
      - next(i)          每日决策

    引擎注入的数据:
      - self.daily:      DataFrame, 日线 OHLCV, 索引=日期
      - self.weekly:     DataFrame, 周线 OHLCV, 索引对齐到日线
      - self.monthly:    DataFrame, 月线 OHLCV, 索引对齐到日线

    引擎注入的账户状态:
      - self.has_position: bool   是否持仓
      - self.position_pct: float  持仓占比 (0~1)
      - self.profit_pct: float    当前盈亏 (%)
      - self.cost: float          成本价
      - self.cash: float          现金余额
    """

    name: str = ""
    description: str = ""

    # ── 引擎注入（策略不要手动赋值）──
    daily: pd.DataFrame
    weekly: pd.DataFrame
    monthly: pd.DataFrame
    has_position: bool = False
    position_pct: float = 0.0
    profit_pct: float = 0.0
    cost: float = 0.0
    cash: float = 0.0

    @abstractmethod
    def init(self):
        """回测开始前调用一次。在此预计算指标。"""
        ...

    @abstractmethod
    def next(self, i: int) -> list[Order]:
        """每个交易日调用一次。

        Args:
            i: 当前日期索引 (0=第一天, len(daily)-1=最后一天)

        Returns:
            Order 列表。空列表=不做任何操作。
            引擎层保证: sell但无持仓 → 跳过 / buy但已有持仓 → 跳过
        """
        ...
