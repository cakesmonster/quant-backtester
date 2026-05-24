"""全局配置常量。"""

import os

# ── 路径 ─────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
STOCK_POOL_FILE = os.path.join(CACHE_DIR, "stock_pool.json")

# ── 服务 ─────────────────────────────────────────
FASTAPI_HOST = "0.0.0.0"
FASTAPI_PORT = 8100

# ── 通达信 ───────────────────────────────────────
# 日线最早拉到2015年（10年足够）
DAILY_BEGIN = "2015-01-01"

# ── 股票池排除规则 ──────────────────────────────
EXCLUDE_PREFIXES = ("688", "8", "900", "301")  # 科创/北交/B股/创业板注册制
EXCLUDE_NAME_PATTERNS = ("ST", "*ST")            # ST股
EXCLUDE_300 = True                               # 创业板
