"""
单元测试 — 策略注册表: discover_strategies 自动扫描 strategies/ 目录。
"""

import pytest

from quant_backtester.strategies.registry import discover_strategies
from quant_backtester.strategies.base import BaseStrategy
from quant_backtester.strategies.macd_cross import MACDCross
from quant_backtester.strategies.kdj_cross import KDJCross
from quant_backtester.strategies.macd_divergence import MACDDivergence
from quant_backtester.strategies.weekly_daily_kdj import WeeklyDailyKDJ


class TestDiscoverStrategies:
    def test_finds_all_strategies(self):
        strategies = discover_strategies()
        assert len(strategies) >= 4  # 至少有 4 个策略
        assert "MACD金叉死叉" in strategies
        assert "KDJ金叉死叉" in strategies
        assert "MACD顶底背离" in strategies
        assert "周线+日线KDJ联动" in strategies

    def test_all_are_base_strategy_subclasses(self):
        strategies = discover_strategies()
        for name, cls in strategies.items():
            assert issubclass(cls, BaseStrategy)
            assert cls is not BaseStrategy
            assert cls.name != ""

    def test_names_are_unique(self):
        strategies = discover_strategies()
        names = list(strategies.keys())
        assert len(names) == len(set(names))

    def test_returns_correct_types(self):
        strategies = discover_strategies()
        assert isinstance(strategies, dict)
        assert strategies["MACD金叉死叉"] is MACDCross
        assert strategies["KDJ金叉死叉"] is KDJCross
        assert strategies["MACD顶底背离"] is MACDDivergence
        assert strategies["周线+日线KDJ联动"] is WeeklyDailyKDJ

    def test_base_not_included(self):
        strategies = discover_strategies()
        for cls in strategies.values():
            assert cls is not BaseStrategy

    def test_base_strategy_is_abstract(self):
        """BaseStrategy 不能被直接实例化（抽象类）。"""
        with pytest.raises(TypeError):
            BaseStrategy()  # 抽象方法 init/next 未实现
