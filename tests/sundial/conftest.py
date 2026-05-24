"""
sundial 测试共享 fixtures — 内存 SQLite、mock API 数据。
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure sundial package is importable
PROJECT_SRC = str(Path(__file__).parent.parent.parent / "src")
if PROJECT_SRC not in sys.path:
    sys.path.insert(0, PROJECT_SRC)


# ── Mock limit-up pool data ──

def make_limit_up_item(code="000001", name="测试股", board_count=1, change_pct=10.0, sector="化工"):
    """造一个涨停池条目"""
    return {
        "code": code,
        "name": name,
        "price": 12.5,
        "change_pct": change_pct,
        "amount": 5e8,
        "turnover": 8.5,
        "sector": sector,
        "board_count": board_count,
        "first_time": "093000",
        "last_time": "093000",
        "broken_count": 0,
        "seal_amount": 1e8,
    }


def make_limit_down_item(code="600000", name="跌停股", change_pct=-10.0):
    """造一个跌停池条目"""
    return {
        "code": code,
        "name": name,
        "price": 8.0,
        "change_pct": change_pct,
        "amount": 1e8,
        "turnover": 2.0,
        "sector": "房地产",
        "continuous_limit_down": 1,
        "open_count": 0,
    }


def make_broken_item(code="000002", name="炸板股"):
    """造一个炸板条目"""
    return {
        "code": code,
        "name": name,
        "price": 15.0,
        "change_pct": 5.0,
        "amount": 3e8,
        "turnover": 10.0,
        "sector": "新能源",
        "board_count": 0,
        "first_time": "093500",
        "last_time": "100000",
        "broken_count": 1,
        "seal_amount": 0,
    }


def make_index_data(sh_close=3300, sh_pct=0.5, sz_close=11000, sz_pct=0.3, sh_amount=3500, sz_amount=5200):
    """造指数数据"""
    return {
        "sh": {"close": sh_close, "change_pct": sh_pct, "amount": sh_amount},
        "sz": {"close": sz_close, "change_pct": sz_pct, "amount": sz_amount},
        "cyb": {"close": 2200, "change_pct": 0.8, "amount": 1800},
        "kcb": {"close": 1050, "change_pct": 1.2, "amount": 300},
    }
