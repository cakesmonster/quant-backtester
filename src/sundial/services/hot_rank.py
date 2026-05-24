"""热榜采集服务 — cron 定时调用，存入 SQLite"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sundial.data.ths_api import fetch_hot_rank
from sundial.db import save_hot_rank


async def collect(slot: str):
    """采集并存储一个时段的热榜快照"""
    items = await fetch_hot_rank()
    save_hot_rank(slot, items)
    print(f"[{slot}] 已存储 {len(items)} 条热榜数据")


async def main():
    slots = sys.argv[1:] or ["1500"]  # 默认15:00
    for slot in slots:
        await collect(slot)


if __name__ == "__main__":
    asyncio.run(main())
