"""同花顺一小时热股榜"""

import httpx

THS_URL = "https://eq.10jqka.com.cn/open/api/hot_list/v1/hot_stock/a/hour/data.txt"


async def fetch_hot_rank() -> list[dict]:
    """获取 A 股一小时热榜"""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(THS_URL)
        r.raise_for_status()
        raw = r.json()

    items = raw.get("data", {}).get("stock_list", [])
    result = []
    for item in items:
        tag = item.get("tag", {}) or {}
        result.append({
            "rank": item.get("order", 0),
            "code": item.get("code", ""),
            "name": item.get("name", ""),
            "heat_value": float(item.get("rate", 0)),
            "change_pct": None,  # 热榜 API 不含涨跌幅
            "concept_tag": ";".join(tag.get("concept_tag", []) or []),
            "is_limit_up": _is_limit_up(tag.get("popularity_tag", "")),
        })
    return result


def _is_limit_up(pop_tag: str) -> bool:
    if not pop_tag:
        return False
    return any(kw in str(pop_tag) for kw in ["板", "涨停"])
