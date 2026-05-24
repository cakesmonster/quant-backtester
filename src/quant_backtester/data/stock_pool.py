"""
股票池管理 — 全市场股票列表 + 排除规则 + 随机采样。

股票来源: mootdx stock_count 获取全市场代码列表 → 应用排除规则 → 缓存到 JSON。
"""

import json
import os
import random
from datetime import date

from quant_backtester.config import (
    STOCK_POOL_FILE,
    EXCLUDE_PREFIXES,
    EXCLUDE_NAME_PATTERNS,
    EXCLUDE_300,
)

# 缓存全局股票池（进程内），避免反复读 JSON
_pool_cache: list[str] | None = None


def _build_pool() -> list[str]:
    """从通达信获取全市场股票列表，应用排除规则。"""
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market="std")

        all_codes = []
        for market in [0, 1]:  # 0=深圳, 1=上海
            try:
                df = client.stocks(market=market)
                if df is not None and len(df) > 0:
                    all_codes.extend(df["code"].tolist())
            except Exception:
                continue  # 一个市场失败不阻塞另一个

        if not all_codes:
            raise RuntimeError("通达信返回 0 只股票")
    except Exception as e:
        raise RuntimeError(f"获取股票列表失败: {e}") from e

    # 去重
    all_codes = list(dict.fromkeys(all_codes))

    # 应用排除规则
    filtered = []
    for code in all_codes:
        code_str = str(code).zfill(6)

        # 只保留标准A股: 00xxxx(深主板), 002xxx(中小板), 003xxx(新深主), 60xxxx(沪主板)
        if not (code_str.startswith(("00", "60"))):
            continue
        # 排除科创板/北交/B股
        if code_str.startswith(EXCLUDE_PREFIXES):
            continue
        # 排除创业板
        if EXCLUDE_300 and code_str.startswith("300"):
            continue

        filtered.append(code_str)

    # 排除 ST（需要股票名称，这里用前缀匹配）
    # mootdx stock_count 返回的列表不带名称，ST 过滤依赖后续业务层
    # 这里先只做代码前缀级别的过滤
    return sorted(filtered)


def _load_pool() -> list[str]:
    """加载股票池（JSON → 自动构建）。"""
    global _pool_cache

    if _pool_cache is not None:
        return _pool_cache

    if os.path.exists(STOCK_POOL_FILE):
        try:
            with open(STOCK_POOL_FILE) as f:
                data = json.load(f)
            _pool_cache = data.get("codes", [])
            if _pool_cache:
                return _pool_cache
        except (json.JSONDecodeError, KeyError):
            pass

    # 无缓存或损坏 → 重新构建
    codes = _build_pool()
    os.makedirs(os.path.dirname(STOCK_POOL_FILE), exist_ok=True)
    with open(STOCK_POOL_FILE, "w") as f:
        json.dump({
            "updated": date.today().isoformat(),
            "count": len(codes),
            "codes": codes,
        }, f, ensure_ascii=False, indent=2)

    _pool_cache = codes
    return codes


def get_pool() -> list[str]:
    """获取全部可回测股票代码列表。"""
    return _load_pool()


def random_sample(n: int, seed: int | None = None) -> list[str]:
    """从股票池中随机抽取 n 只。

    Args:
        n: 抽取数量
        seed: 随机种子（用于可复现回测）

    Returns:
        n 只股票代码列表
    """
    pool = _load_pool()
    if n >= len(pool):
        return pool.copy()

    rng = random.Random(seed)
    return rng.sample(pool, n)


def pool_stats() -> dict:
    """股票池统计信息。"""
    pool = _load_pool()
    return {
        "total": len(pool),
        "last_updated": (
            json.load(open(STOCK_POOL_FILE))["updated"]
            if os.path.exists(STOCK_POOL_FILE) else "unknown"
        ),
    }
