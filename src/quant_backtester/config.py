"""全局配置常量。"""

import os
from pathlib import Path

# ── 路径 ─────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # quant-backtester/
PROJECT_ROOT = str(_PROJECT_ROOT)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
STOCK_POOL_FILE = os.path.join(CACHE_DIR, "stock_pool.json")
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")

# ── 服务 ─────────────────────────────────────────
FASTAPI_HOST = "127.0.0.1"
FASTAPI_PORT = 8100

# ── 通达信 ───────────────────────────────────────
# 日线最早拉到2015年（10年足够）
DAILY_BEGIN = "2015-01-01"

# ── 股票池排除规则 ──────────────────────────────
EXCLUDE_PREFIXES = ("688", "8", "900", "301")  # 科创/北交/B股/创业板注册制
EXCLUDE_NAME_PATTERNS = ("ST", "*ST")            # ST股
EXCLUDE_300 = True                               # 创业板
