"""日晷全局配置"""

import os
from pathlib import Path

# 基础路径
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = Path(os.environ.get("SUNDIAL_DATA_DIR", PROJECT_ROOT / "data"))

# SQLite 路径
DB_PATH = DATA_DIR / "sundial.db"

# 服务配置
HOST = os.environ.get("SUNDIAL_HOST", "127.0.0.1")
PORT = int(os.environ.get("SUNDIAL_PORT", "8200"))

# 同花顺热榜 API
THS_HOT_RANK_URL = "https://eq.10jqka.com.cn/open/api/hot_list/v1/hot_stock/a/hour/data.txt"

# cron 热榜采集时段
HOT_RANK_SLOTS = ["1130", "1500", "2100"]
