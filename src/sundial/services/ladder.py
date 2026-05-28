"""连板天梯 — 按连板数分组"""

from collections import defaultdict
from sundial.data.eastmoney_api import fetch_limit_up_pool


async def compute_ladder(target_date: str) -> dict:
    """返回连板天梯，按连板模式分组（含非连续性「X天Y板」）。

    分组 key 格式：
      - N天N板 → "N连板"  （连续性涨停）
      - X天Y板 → "X天Y板" （X≠Y 时，非连续性）
    """
    pool = await fetch_limit_up_pool(target_date)
    ladder = defaultdict(list)
    for item in pool:
        td = item.get("total_days", 1)
        tb = item.get("total_boards", 1)
        # 只有 ≥2 板的进天梯
        if tb < 2:
            continue
        label = f"{td}连板" if td == tb else f"{td}天{tb}板"
        ladder[label].append({
            "code": item["code"],
            "name": item["name"],
            "change_pct": item.get("change_pct", 0),
            "sector": item.get("sector", ""),
            "first_time": item.get("first_time", ""),
            "broken_count": item.get("broken_count", 0),
            "board_count": item.get("board_count", 1),
        })

    # 排序：按模式中的天数降序，同模式按涨跌幅降序
    def _sort_key(label):
        import re
        m = re.match(r'(\d+)', label)
        return int(m.group(1)) if m else 0

    sorted_ladder = {
        k: sorted(v, key=lambda x: x["change_pct"] or 0, reverse=True)
        for k, v in sorted(ladder.items(), key=lambda x: _sort_key(x[0]), reverse=True)
    }

    return {
        "date": target_date,
        "total_limit_up": len(pool),
        "ladder": sorted_ladder,
    }


async def compute_yesterday_performance(target_date: str) -> dict:
    """昨日涨停今日表现"""
    from sundial.data.eastmoney_api import fetch_yesterday_pool, fetch_limit_up_pool
    yday = await fetch_yesterday_pool(target_date)
    today = await fetch_limit_up_pool(target_date)
    today_codes = {item["code"] for item in today}

    if not yday:
        return {"count": 0, "continued": 0, "message": "无昨日数据"}

    continued = sum(1 for item in yday if item["code"] in today_codes)
    return {
        "count": len(yday),
        "continued": continued,
        "rate": round(continued / len(yday) * 100, 1),
    }


async def compute_eliminated(target_date: str) -> list[dict]:
    """淘汰区：昨日涨停但今日未涨停的股票（破板/断板）。"""
    from sundial.data.eastmoney_api import fetch_yesterday_pool, fetch_limit_up_pool

    yday_pool = await fetch_yesterday_pool(target_date)
    today_pool = await fetch_limit_up_pool(target_date)
    today_codes = {item["code"] for item in today_pool}

    eliminated = []
    for item in yday_pool:
        code = item["code"]
        if code not in today_codes:
            eliminated.append({
                "code": code,
                "name": item["name"],
                "sector": item.get("sector", ""),
                "changePct": item.get("change_pct", 0),
            })

    return eliminated
