"""
策略注册表 — 自动扫描 strategies/ 目录，发现所有 BaseStrategy 子类。
"""

import importlib
import inspect
import os
import pkgutil
from typing import Type

from quant_backtester.strategies.base import BaseStrategy


def discover_strategies(reload: bool = False) -> dict[str, Type[BaseStrategy]]:
    """自动发现 strategies/ 目录下所有策略类。

    Args:
        reload: 如果 True，先清除 importlib 缓存再重新导入。

    Returns:
        {策略name: 策略类} 字典，如 {"MACD金叉死叉": MACDCross}
    """
    import sys

    if reload:
        # 重载所有已缓存的 strategies 子模块
        import quant_backtester.strategies as pkg
        for key in list(sys.modules.keys()):
            if key.startswith("quant_backtester.strategies."):
                try:
                    importlib.reload(sys.modules[key])
                except Exception:
                    pass

    import quant_backtester.strategies as pkg

    pkg_dir = os.path.dirname(pkg.__file__)
    strategies: dict[str, Type[BaseStrategy]] = {}

    for _, module_name, _ in pkgutil.iter_modules([pkg_dir]):
        if module_name in ("base",):
            continue

        try:
            module = importlib.import_module(f"quant_backtester.strategies.{module_name}")
        except Exception:
            continue

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, BaseStrategy) or obj is BaseStrategy:
                continue
            strategies[obj.name] = obj

    return strategies
