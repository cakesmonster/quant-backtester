"""同花顺一小时热股榜 + 新浪行情补涨跌幅"""

import asyncio
import re
import httpx

THS_URL = "https://eq.10jqka.com.cn/open/api/hot_list/v1/hot_stock/a/hour/data.txt"
SINA_URL = "http://hq.sinajs.cn/list="


async def fetch_hot_rank() -> list[dict]:
    """获取 A 股一小时热榜（含实时涨跌幅）"""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(THS_URL)
        r.raise_for_status()
        raw = r.json()

    items = raw.get("data", {}).get("stock_list", [])
    if not items:
        return []

    # 解析热榜数据
    result = []
    codes = []
    for item in items:
        tag = item.get("tag", {}) or {}
        code = item.get("code", "")
        result.append({
            "rank": item.get("order", 0),
            "code": code,
            "name": item.get("name", ""),
            "heat_value": float(item.get("rate", 0)),
            "change_pct": 0.0,  # 下面批量补
            "concept_tag": ";".join(tag.get("concept_tag", []) or []),
            "is_limit_up": _is_limit_up(tag.get("popularity_tag", "")),
        })
        if code:
            codes.append(code)

    # 批量补涨跌幅
    if codes:
        pct_map = await _batch_fetch_change_pct(codes)
        for item in result:
            pct = pct_map.get(item["code"], 0.0)
            item["change_pct"] = pct
            # 以实际涨跌幅为准修正涨停标记（≥9.5% 主板 / ≥19.5% 科创创业）
            code = item["code"]
            if code.startswith(("30", "68")):
                item["is_limit_up"] = pct >= 19.5
            else:
                item["is_limit_up"] = pct >= 9.5

    return result


def _code_to_sina(code: str) -> str:
    """纯数字代码 → 新浪格式 (sh600519 / sz000001)"""
    if code.startswith(("6", "5")):
        return f"sh{code}"
    return f"sz{code}"


async def _batch_fetch_change_pct(codes: list[str]) -> dict[str, float]:
    """新浪批量行情 → {code: change_pct}"""
    sina_codes = [_code_to_sina(c) for c in codes]
    # 分批，每批最多 50 个
    batch_size = 50
    result = {}

    for i in range(0, len(sina_codes), batch_size):
        batch = sina_codes[i:i + batch_size]
        url = SINA_URL + ",".join(batch)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(url, headers={"Referer": "https://finance.sina.com.cn"})
                r.encoding = "gbk"
                text = r.text
        except Exception:
            continue

        # 解析每行: var hq_str_sh600519="name,open,prev,cur,high,low,..."
        for line in text.split("\n"):
            m = re.match(r'var hq_str_(s[hz]\d+)=\"(.+)\"', line.strip())
            if not m:
                continue
            sina_code = m.group(1)  # sh600519
            fields = m.group(2).split(",")
            if len(fields) < 4:
                continue
            try:
                prev_close = float(fields[2])  # 昨收
                cur_price = float(fields[3])   # 当前价
                if prev_close > 0:
                    pct = round((cur_price - prev_close) / prev_close * 100, 2)
                else:
                    pct = 0.0
            except (ValueError, IndexError):
                pct = 0.0

            # sina_code → 纯数字
            pure_code = sina_code[2:]
            if pure_code in codes:
                result[pure_code] = pct

    return result


def _is_limit_up(pop_tag: str) -> bool:
    if not pop_tag:
        return False
    return any(kw in str(pop_tag) for kw in ["板", "涨停"])
