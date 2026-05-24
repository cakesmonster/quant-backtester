"""
虚拟账户 — 模拟资金/持仓/交易执行。

支持:
  - 买入/卖出按比例执行
  - 手续费 (默认万三)
  - 滑点 (默认 0.1%)
  - 100股取整
  - 交易记录
"""

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd


@dataclass
class Trade:
    """单笔交易记录"""
    date: str            # 交易日期
    action: str          # buy / sell
    price: float         # 成交价
    shares: int          # 成交股数
    amount: float        # 成交金额
    commission: float    # 手续费
    slippage_cost: float # 滑点成本
    reason: str          # 触发原因
    profit_pct: float = 0.0  # 卖出盈亏% (买入时为0)


@dataclass
class Portfolio:
    """虚拟账户。

    Attributes:
        initial_capital: 初始资金
        cash:            当前现金
        shares:          持仓股数
        cost:            持仓成本价
        commission_rate: 手续费率（默认万三）
        slippage_rate:   滑点率（默认 0.1%）
        trades:          交易记录列表
    """

    initial_capital: float
    commission_rate: float = 0.0003
    slippage_rate: float = 0.001

    cash: float = field(init=False)
    shares: int = 0
    cost: float = 0.0
    bought_day_idx: int = -1   # 买入日的索引 (-1=无持仓 或 隔夜底仓可T+0)
    trades: list[Trade] = field(default_factory=list)

    def __post_init__(self):
        self.cash = self.initial_capital

    # ── 查询 ──

    @property
    def has_position(self) -> bool:
        return self.shares > 0

    @property
    def can_sell_today(self) -> bool:
        """A股 T+1: 当日买入不可卖出。bought_day_idx=-1 表示隔夜底仓，可卖。"""
        return self.bought_day_idx == -1

    @property
    def position_value(self) -> float:
        """当前持仓市值（需要外部更新 latest_price）。"""
        return self.shares * self._latest_price

    @property
    def total_value(self) -> float:
        """总资产 = 现金 + 持仓市值。"""
        return self.cash + self.position_value

    @property
    def profit_pct(self) -> float:
        """当前持仓盈亏 (%)。无持仓返回 0。"""
        if not self.has_position or self.cost <= 0:
            return 0.0
        return (self._latest_price / self.cost - 1) * 100

    # ── 更新行情 ──

    def set_price(self, price: float):
        """更新最新价（每个交易日调用）。"""
        self._latest_price = price

    def advance_day(self, current_day_idx: int):
        """每个新交易日开始时调用。T+1: 如果持仓是昨天买的，今天解锁卖出。"""
        if self.has_position and self.bought_day_idx >= 0 and current_day_idx > self.bought_day_idx:
            self.bought_day_idx = -1  # 解锁，可卖出

    # ── 交易执行 ──

    def buy(self, price: float, pct: float, date: str, *, day_idx: int = -1, reason: str = "") -> Trade | None:
        """按比例买入。

        Args:
            price: 当前收盘价
            pct: 仓位比例 (0~1)
            date: 交易日期 "YYYY-MM-DD"
            day_idx: 当前日期索引（用于T+1记录）
            reason: 触发原因

        Returns:
            Trade 记录，资金不足时返回 None。
        """
        if pct <= 0 or self.has_position:
            return None

        # 滑点: 买入价略高于收盘价
        buy_price = price * (1 + self.slippage_rate)
        # 可买金额
        max_amount = self.cash * pct
        # 股数（100股取整）
        raw_shares = int(max_amount / buy_price / 100) * 100
        if raw_shares < 100:
            return None

        actual_amount = raw_shares * buy_price
        commission = actual_amount * self.commission_rate
        total_cost = actual_amount + commission

        if total_cost > self.cash:
            # 资金不够，降一档
            raw_shares -= 100
            if raw_shares < 100:
                return None
            actual_amount = raw_shares * buy_price
            commission = actual_amount * self.commission_rate
            total_cost = actual_amount + commission
            if total_cost > self.cash:
                return None

        self.cash -= total_cost
        # 加权成本 + T+1 记录
        if self.shares > 0:
            total_cost_basis = self.cost * self.shares + actual_amount
            self.shares += raw_shares
            self.cost = total_cost_basis / self.shares
        else:
            self.shares = raw_shares
            self.cost = buy_price
        self.bought_day_idx = day_idx     # 记录买入日

        trade = Trade(
            date=date,
            action="buy",
            price=round(buy_price, 2),
            shares=raw_shares,
            amount=round(actual_amount, 2),
            commission=round(commission, 2),
            slippage_cost=round(raw_shares * (buy_price - price), 2),
            reason=reason,
        )
        self.trades.append(trade)
        return trade

    def sell(self, price: float, pct: float, date: str, reason: str = "") -> Trade | None:
        """按比例卖出。

        Args:
            price: 当前收盘价
            pct: 卖出持仓比例 (0~1)
            date: 交易日期
            reason: 触发原因

        Returns:
            Trade 记录，无持仓时返回 None。
        """
        if pct <= 0 or not self.has_position:
            return None

        # 滑点: 卖出价略低于收盘价
        sell_price = price * (1 - self.slippage_rate)
        sell_shares = max(int(self.shares * pct / 100) * 100, 100)
        sell_shares = min(sell_shares, self.shares)

        actual_amount = sell_shares * sell_price
        commission = actual_amount * self.commission_rate
        net_cash = actual_amount - commission

        profit_pct = (sell_price / self.cost - 1) * 100 if self.cost > 0 else 0

        self.cash += net_cash
        self.shares -= sell_shares
        if self.shares == 0:
            self.cost = 0.0
            self.bought_day_idx = -1   # 清仓后重置

        trade = Trade(
            date=date,
            action="sell",
            price=round(sell_price, 2),
            shares=sell_shares,
            amount=round(actual_amount, 2),
            commission=round(commission, 2),
            slippage_cost=round(sell_shares * (price - sell_price), 2),
            reason=reason,
            profit_pct=round(profit_pct, 2),
        )
        self.trades.append(trade)
        return trade
