"""同花顺一小时热股榜 — dq.10jqka.com.cn 接口，含涨跌幅"""

import httpx

THS_URL = "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock"


async def fetch_hot_rank() -> list[dict]:
    """获取 A 股一小时热榜（含实时涨跌幅 rise_and_fall）"""
    params = {"stock_type": "a", "type": "hour", "list_type": "normal"}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    async with httpx.AsyncClient(timeout=10, headers=headers) as client:
        r = await client.get(THS_URL, params=params)
        r.raise_for_status()
        raw = r.json()

    items = raw.get("data", {}).get("stock_list", [])
    if not items:
        return []

    result = []
    for item in items:
        tag = item.get("tag", {}) or {}
        code = item.get("code", "")
        pct = float(item.get("rise_and_fall", 0) or 0)

        # 涨停判定：以实际涨跌幅为准（≥9.5% 主板 / ≥19.5% 科创创业）
        if code.startswith(("30", "68")):
            is_limit = pct >= 19.5
        else:
            is_limit = pct >= 9.5

        result.append({
            "rank": item.get("order", 0),
            "code": code,
            "name": item.get("name", ""),
            "heat_value": float(item.get("rate", 0)),
            "change_pct": round(pct, 2),
            "concept_tag": ";".join(tag.get("concept_tag", []) or []),
            "is_limit_up": is_limit,
        })

    return result
