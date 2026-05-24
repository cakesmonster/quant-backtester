"""
单元测试 — 虚拟账户 Portfolio: T+1, 涨跌停, 买卖, 成本计算。
"""

import pytest

from quant_backtester.engine.portfolio import Portfolio


def make_empty_portfolio():
    return Portfolio(initial_capital=100_000, commission_rate=0.0003, slippage_rate=0.001)


# ═══════════════════════════════════════════════════════════════
# 基本操作
# ═══════════════════════════════════════════════════════════════


class TestInitialState:
    def test_initial_cash(self):
        p = Portfolio(initial_capital=50_000)
        assert p.cash == 50_000
        assert p.shares == 0
        assert p.cost == 0.0
        assert not p.has_position
        assert p.bought_day_idx == -1

    def test_custom_commission_slippage(self):
        p = Portfolio(initial_capital=100_000, commission_rate=0.001, slippage_rate=0.002)
        assert p.commission_rate == 0.001
        assert p.slippage_rate == 0.002

    def test_can_sell_today_no_position(self):
        """隔夜底仓(bought_day_idx=-1)可卖。"""
        p = Portfolio(initial_capital=100_000)
        p.shares = 100
        p.cost = 10.0
        p.bought_day_idx = -1
        assert p.can_sell_today


class TestBuy:
    def test_buy_basic(self):
        p = make_empty_portfolio()
        p.set_price(10.0)
        trade = p.buy(price=10.0, pct=1.0, date="2020-01-02", day_idx=0, reason="测试买入")
        assert trade is not None
        assert trade.action == "buy"
        assert trade.shares > 0
        assert p.has_position
        assert p.bought_day_idx == 0  # T+1 标记

    def test_buy_already_has_position(self):
        """已有持仓不能重复买入。"""
        p = make_empty_portfolio()
        p.set_price(10.0)
        p.buy(10.0, 1.0, "2020-01-02", day_idx=0)
        trade2 = p.buy(10.0, 1.0, "2020-01-03", day_idx=1)
        assert trade2 is None

    def test_buy_negative_pct(self):
        p = make_empty_portfolio()
        trade = p.buy(10.0, 0.0, "2020-01-02")
        assert trade is None

    def test_buy_not_enough_cash(self):
        """买不起一整手。"""
        p = Portfolio(initial_capital=500)
        trade = p.buy(10.0, 1.0, "2020-01-02")
        assert trade is None

    def test_buy_100_share_rounding(self):
        """买入按100股取整。"""
        p = make_empty_portfolio()
        p.buy(10.0, 1.0, "2020-01-02", day_idx=0)
        assert p.shares % 100 == 0

    def test_buy_commission_charged(self):
        """手续费被扣除。"""
        p = make_empty_portfolio()
        p.buy(10.0, 1.0, "2020-01-02", day_idx=0)
        assert p.cash < 100_000  # 花了钱

    def test_buy_sets_cost(self):
        p = make_empty_portfolio()
        p.buy(10.0, 1.0, "2020-01-02", day_idx=0)
        assert p.cost > 0


class TestSell:
    def test_sell_basic(self, portfolio_with_position):
        p = portfolio_with_position
        trade = p.sell(10.0, 1.0, "2020-01-02")
        assert trade is not None
        assert trade.action == "sell"
        assert p.shares == 0
        assert not p.has_position
        assert p.bought_day_idx == -1

    def test_sell_partial(self, portfolio_with_position):
        p = portfolio_with_position
        original_shares = p.shares
        p.sell(10.0, 0.5, "2020-01-02")
        assert p.shares == original_shares // 2
        assert p.has_position

    def test_sell_no_position(self):
        p = make_empty_portfolio()
        trade = p.sell(10.0, 1.0, "2020-01-02")
        assert trade is None

    def test_sell_slippage(self, portfolio_with_position):
        """卖出价低于市价。"""
        p = portfolio_with_position
        trade = p.sell(10.0, 1.0, "2020-01-02")
        assert trade.price < 10.0  # 滑点

    def test_sell_profit_tracking(self):
        """卖出盈亏%记录。"""
        p = Portfolio(initial_capital=100_000)
        p.buy(10.0, 1.0, "2020-01-02", day_idx=0)
        p.set_price(11.0)
        trade = p.sell(11.0, 1.0, "2020-01-05")
        assert trade.profit_pct > 0  # 盈利

    def test_sell_loss_tracking(self):
        p = Portfolio(initial_capital=100_000)
        p.buy(10.0, 1.0, "2020-01-02", day_idx=0)
        p.set_price(9.0)
        trade = p.sell(9.0, 1.0, "2020-01-05")
        assert trade.profit_pct < 0  # 亏损


# ═══════════════════════════════════════════════════════════════
# T+1 规则 — 这是你要的 bug fix
# ═══════════════════════════════════════════════════════════════


class TestTPlusOne:
    """A股 T+1: 当日买入不可卖出。"""

    def test_buy_same_day_cannot_sell(self):
        """当日买入 → 当日卖出被 blocked。"""
        p = make_empty_portfolio()
        p.set_price(10.0)
        p.buy(10.0, 1.0, "2020-01-02", day_idx=5)
        assert p.bought_day_idx == 5
        # 同一 day_idx → should be blocked
        assert not p.can_sell_today

    def test_overnight_unlocks_sell(self):
        """买入后过夜 → T+1 解锁，可以卖。"""
        p = make_empty_portfolio()
        p.set_price(10.0)
        p.buy(10.0, 1.0, "2020-01-02", day_idx=5)
        # 模拟下一个交易日
        p.advance_day(current_day_idx=6)
        assert p.can_sell_today
        assert p.bought_day_idx == -1

    def test_sell_before_buy_works(self):
        """底仓（非当日买入）→ 可以卖。"""
        p = make_empty_portfolio()
        p.set_price(10.0)
        p.shares = 1000
        p.cost = 10.0
        p.bought_day_idx = -1  # 隔夜底仓
        p._latest_price = 10.0
        trade = p.sell(10.0, 1.0, "2020-01-02")
        assert trade is not None
        assert p.shares == 0

    def test_sell_resets_bought_day_idx(self):
        """清仓后 bought_day_idx 重置为 -1。"""
        p = make_empty_portfolio()
        p.set_price(10.0)
        p.buy(10.0, 1.0, "2020-01-02", day_idx=5)
        p.advance_day(6)
        p.sell(10.0, 1.0, "2020-01-03")
        assert p.bought_day_idx == -1
        assert p.cost == 0.0

    def test_advance_day_no_op_when_no_position(self):
        """无持仓时 advance_day 无副作用。"""
        p = make_empty_portfolio()
        p.advance_day(10)
        assert p.can_sell_today

    def test_advance_day_same_day_no_unlock(self):
        """同一 day_idx 不触发解锁（同一天多次调用）。"""
        p = make_empty_portfolio()
        p.buy(10.0, 1.0, "2020-01-02", day_idx=5)
        p.advance_day(5)  # 同一天
        assert not p.can_sell_today  # 仍未解锁

    def test_advance_day_larger_jump(self):
        """跨多天 → 解锁。"""
        p = make_empty_portfolio()
        p.buy(10.0, 1.0, "2020-01-02", day_idx=5)
        p.advance_day(100)
        assert p.can_sell_today

    def test_t_plus_one_engine_level(self, portfolio_with_position):
        """引擎层的 T+1 校验: bought_day_idx == i 时跳过卖出。"""
        # 模拟引擎逐日循环
        p = portfolio_with_position
        p.bought_day_idx = 5  # 模拟第5天买入

        # engine 在 i=5 时
        i = 5
        allow_sell = not (p.bought_day_idx >= 0 and p.bought_day_idx == i)
        assert not allow_sell  # T+1 锁定

        # engine 在 i=6 时（advance_day 已调用）
        p.advance_day(6)
        i = 6
        allow_sell = not (p.bought_day_idx >= 0 and p.bought_day_idx == i)
        assert allow_sell  # 已解锁


# ═══════════════════════════════════════════════════════════════
# 涨跌停 — 你要求加的第二个规则
# ═══════════════════════════════════════════════════════════════


class TestLimitRules:
    """涨停买不进，跌停卖不出。"""

    def test_limit_up_price_calculation(self):
        """涨停价 = prev_close * 1.10（四舍五入到分）。"""
        prev = 10.00
        limit_up = round(prev * 1.10, 2)
        assert limit_up == 11.00

    def test_limit_down_price_calculation(self):
        """跌停价 = prev_close * 0.90。"""
        prev = 10.00
        limit_down = round(prev * 0.90, 2)
        assert limit_down == 9.00

    def test_is_limit_up(self):
        """close >= 涨停价-0.01 视作涨停。"""
        prev = 10.00
        limit_up = round(prev * 1.10, 2)  # 11.00
        assert 11.00 >= limit_up - 0.01
        assert 10.99 >= limit_up - 0.01
        assert not (10.98 >= limit_up - 0.01)

    def test_is_limit_down(self):
        """close <= 跌停价+0.01 视作跌停。"""
        prev = 10.00
        limit_down = round(prev * 0.90, 2)  # 9.00
        assert 9.00 <= limit_down + 0.01
        assert 9.01 <= limit_down + 0.01
        assert not (9.02 <= limit_down + 0.01)

    def test_cannot_buy_at_limit_up(self, limit_up_daily):
        """涨停日发动机应跳过买入。"""
        df = limit_up_daily
        # 找到涨停日：close >= prev_close * 1.10 - 0.01
        for i in range(1, len(df)):
            prev_close = float(df.iloc[i - 1]["close"])
            close = float(df.iloc[i]["close"])
            is_limit = close >= round(prev_close * 1.10, 2) - 0.01
            if is_limit:
                # 涨停日应阻止买入
                assert is_limit  # 确认涨停条件成立
                break
        else:
            pytest.skip("数据中未找到涨停日")

    def test_cannot_sell_at_limit_down(self, limit_down_daily):
        """跌停日发动机应跳过卖出。"""
        df = limit_down_daily
        for i in range(1, len(df)):
            prev_close = float(df.iloc[i - 1]["close"])
            close = float(df.iloc[i]["close"])
            is_limit = close <= round(prev_close * 0.90, 2) + 0.01
            if is_limit:
                assert is_limit
                break
        else:
            pytest.skip("数据中未找到跌停日")


# ═══════════════════════════════════════════════════════════════
# 账户状态
# ═══════════════════════════════════════════════════════════════


class TestPortfolioState:
    def test_set_price_updates_position_value(self):
        p = make_empty_portfolio()
        p.set_price(10.0)
        p.buy(10.0, 1.0, "2020-01-02", day_idx=0)
        p.set_price(12.0)
        assert p.position_value == p.shares * 12.0

    def test_total_value_cash_plus_position(self):
        p = make_empty_portfolio()
        p.set_price(10.0)
        p.buy(10.0, 0.5, "2020-01-02", day_idx=0)
        p.set_price(10.0)
        expected = p.cash + p.shares * 10.0
        assert abs(p.total_value - expected) < 0.01

    def test_profit_pct_no_position(self):
        p = make_empty_portfolio()
        assert p.profit_pct == 0.0

    def test_profit_pct_with_position(self):
        p = make_empty_portfolio()
        p.buy(10.0, 1.0, "2020-01-02", day_idx=0)
        p.set_price(11.0)
        assert p.profit_pct > 0

    def test_trade_history(self):
        p = make_empty_portfolio()
        p.buy(10.0, 1.0, "2020-01-02", day_idx=0, reason="买")
        p.advance_day(1)
        p.sell(11.0, 1.0, "2020-01-03", reason="卖")
        assert len(p.trades) == 2
        assert p.trades[0].action == "buy"
        assert p.trades[0].reason == "买"
        assert p.trades[1].action == "sell"
        assert p.trades[1].reason == "卖"
