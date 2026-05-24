"""全局配置常量。"""

import os
import uuid
from pathlib import Path

# ── 路径 ─────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # quant-backtester/
PROJECT_ROOT = str(_PROJECT_ROOT)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
STOCK_POOL_FILE = os.path.join(CACHE_DIR, "stock_pool.json")
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")

# ── 密钥（启动时自动生成） ──────────────────────
def _ensure_keys() -> tuple[str, str]:
    """确保 .env 中存在 PRIVATE_KEY 和 PUBLIC_KEY，不存在则生成 UUID 写入。"""
    env = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")

    private = env.get("PRIVATE_KEY") or str(uuid.uuid4())
    public = env.get("PUBLIC_KEY") or str(uuid.uuid4())

    # 如果有关键缺失，写回 .env
    if "PRIVATE_KEY" not in env or "PUBLIC_KEY" not in env:
        _write_env(ENV_FILE, env, private, public)

    return private, public


def _write_env(path: str, existing: dict, private: str, public: str) -> None:
    """安全覆盖写入 .env（不丢已有配置）。"""
    lines: list[str] = []
    if os.path.exists(path):
        with open(path) as f:
            lines = f.readlines()

    def _set_key(name: str, value: str):
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{name}=") or line.strip().startswith(f"{name} ="):
                lines[i] = f'{name}="{value}"\n'
                return
        lines.append(f'{name}="{value}"\n')

    _set_key("PRIVATE_KEY", private)
    _set_key("PUBLIC_KEY", public)

    with open(path, "w") as f:
        f.writelines(lines)


PRIVATE_KEY, PUBLIC_KEY = _ensure_keys()

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
