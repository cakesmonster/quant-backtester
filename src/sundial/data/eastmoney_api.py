"""东方财富 push2ex 专题池 — 涨停/跌停/炸板/强势"""

import httpx
from datetime import date
from typing import Optional

BASE = "https://push2ex.eastmoney.com"
UT = "7eea3edcaed734bea9cbfc24409ed989"
DPT = "wz.ztzt"


def _normalize(pool: list[dict], pool_type: str) -> list[dict]:
    """统一字段命名"""
    result = []
    for item in pool:
        row = {
            "code": item.get("c", ""),
            "name": item.get("n", ""),
            "price": item.get("p", 0),
            "change_pct": item.get("zdp", 0),
            "amount": item.get("amount", 0),
            "turnover": item.get("hs", 0),
            "sector": item.get("hybk", ""),
        }
        if pool_type in ("limit_up", "strong", "broken"):
            row.update({
                "board_count": item.get("lbc", 1),       # 连板数
                "first_time": item.get("fbt", ""),       # 首次封板时间
                "last_time": item.get("lbt", ""),        # 最后封板时间
                "broken_count": item.get("zbc", 0),      # 炸板次数
                "seal_amount": item.get("fund", 0),      # 封板资金
            })
        if pool_type == "strong":
            row["is_new_high"] = item.get("isNewHigh", False)
            row["reason"] = item.get("reason", "")
        if pool_type == "limit_down":
            row.update({
                "continuous_limit_down": item.get("lbd", 0),
                "open_count": item.get("open", 0),
            })
        result.append(row)
    return result


async def _get_pool(endpoint: str, target_date: str, sort: str = "fbt:asc") -> list:
    """通用请求"""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{BASE}{endpoint}", params={
            "ut": UT, "dpt": DPT,
            "Pageindex": "0", "pagesize": "5000",
            "sort": sort, "date": target_date,
        })
        r.raise_for_status()
        return r.json().get("data", {}).get("pool", [])


async def fetch_limit_up_pool(target_date: Optional[str] = None) -> list[dict]:
    d = target_date or date.today().isoformat().replace("-", "")
    return _normalize(await _get_pool("/getTopicZTPool", d), "limit_up")


async def fetch_strong_pool(target_date: Optional[str] = None) -> list[dict]:
    d = target_date or date.today().isoformat().replace("-", "")
    return _normalize(await _get_pool("/getTopicQSPool", d, sort="zdp:desc"), "strong")


async def fetch_broken_pool(target_date: Optional[str] = None) -> list[dict]:
    d = target_date or date.today().isoformat().replace("-", "")
    return _normalize(await _get_pool("/getTopicZBPool", d), "broken")


async def fetch_limit_down_pool(target_date: Optional[str] = None) -> list[dict]:
    d = target_date or date.today().isoformat().replace("-", "")
    return _normalize(await _get_pool("/getTopicDTPool", d, sort="fund:asc"), "limit_down")


async def fetch_yesterday_pool(target_date: Optional[str] = None) -> list[dict]:
    d = target_date or date.today().isoformat().replace("-", "")
    return _normalize(await _get_pool("/getYesterdayZTPool", d, sort="zs:desc"), "limit_up")


async def fetch_all_limit_data(target_date: Optional[str] = None) -> dict:
    """一次性并发获取全部涨停相关数据"""
    d = target_date or date.today().isoformat().replace("-", "")

    async with httpx.AsyncClient(timeout=15) as client:
        async def get(ep, sort):
            r = await client.get(f"{BASE}{ep}", params={
                "ut": UT, "dpt": DPT, "Pageindex": "0", "pagesize": "5000",
                "sort": sort, "date": d,
            })
            return r.json().get("data", {}).get("pool", [])

        import asyncio
        pool_up, pool_qs, pool_zb, pool_dt, pool_yd = await asyncio.gather(
            get("/getTopicZTPool", "fbt:asc"),
            get("/getTopicQSPool", "zdp:desc"),
            get("/getTopicZBPool", "fbt:asc"),
            get("/getTopicDTPool", "fund:asc"),
            get("/getYesterdayZTPool", "zs:desc"),
        )

    return {
        "limit_up": _normalize(pool_up, "limit_up"),
        "strong": _normalize(pool_qs, "strong"),
        "broken": _normalize(pool_zb, "broken"),
        "limit_down": _normalize(pool_dt, "limit_down"),
        "yesterday": _normalize(pool_yd, "limit_up"),
    }
