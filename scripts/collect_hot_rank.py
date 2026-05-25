#!/usr/bin/env python3
"""热榜采集 — cron 每小时调用，存入 SQLite"""
import sys
import asyncio
from pathlib import Path

# 确保 sundial 模块可导入
PROJ = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJ / "src"))

from sundial.data.ths_api import fetch_hot_rank
from sundial.db import db_session
from datetime import datetime


async def main():
    items = await fetch_hot_rank()
    hour = datetime.now().strftime("%H%M")
    today = datetime.now().strftime("%Y-%m-%d")

    with db_session() as conn:
        conn.execute("DELETE FROM hot_rank_snapshot WHERE date=? AND slot=?", (today, hour))
        for item in items:
            conn.execute(
                "INSERT OR REPLACE INTO hot_rank_snapshot (date, slot, rank, code, name, heat_value, concept_tag, is_limit_up, change_pct) VALUES (?,?,?,?,?,?,?,?,?)",
                (today, hour, item.get("rank", 0), item.get("code", ""), item.get("name", ""),
                 item.get("heat_value", 0), item.get("concept_tag", ""),
                 1 if item.get("is_limit_up") else 0, item.get("change_pct") or 0),
            )
    print(f"[{hour}] {len(items)} 条热榜数据已存储")


if __name__ == "__main__":
    asyncio.run(main())
