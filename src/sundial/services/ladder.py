"""连板天梯 — 按连板数分组"""

from collections import defaultdict
from sundial.data.eastmoney_api import fetch_limit_up_pool


async def compute_ladder(target_date: str) -> dict:
    """返回连板天梯：{2: [...], 3: [...], ...}"""
    pool = await fetch_limit_up_pool(target_date)
    ladder = defaultdict(list)
    for item in pool:
        bc = item.get("board_count", 1)
        if bc >= 2:
            ladder[bc].append({
                "code": item["code"],
                "name": item["name"],
                "change_pct": item.get("change_pct", 0),
                "sector": item.get("sector", ""),
                "first_time": item.get("first_time", ""),
                "broken_count": item.get("broken_count", 0),
            })
    return {
        "date": target_date,
        "total_limit_up": len(pool),
        "ladder": {str(k): sorted(v, key=lambda x: x["change_pct"] or 0, reverse=True)
                    for k, v in sorted(ladder.items(), reverse=True)},
    }


async def compute_yesterday_performance(target_date: str) -> dict:
    """昨日涨停今日表现 — 需要昨日池 + 今日行情"""
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
