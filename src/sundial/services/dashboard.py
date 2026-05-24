"""
仪表盘聚合服务 — 将 sundial 各服务数据按前端 data.json shape 打包。
"""
import asyncio
from datetime import date, timedelta


async def build_dashboard(target_date: str = None) -> dict:
    """构建完整仪表盘数据，shape 匹配 front/data.json"""
    d = target_date or date.today().strftime("%Y%m%d")
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
    iso = f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    # 并发获取核心数据
    from .sentiment import compute_sentiment
    from .ladder import compute_ladder, compute_yesterday_performance
    from ..db import get_hot_rank, db_session

    sentiment, ladder, yday_perf = await asyncio.gather(
        compute_sentiment(d),
        compute_ladder(d),
        compute_yesterday_performance(d),
    )

    # 热榜（三时段）
    hot_slots = {}
    for slot in ["1130", "1500", "2100"]:
        items = get_hot_rank(iso, slot)
        if items:
            hot_slots[slot] = items

    # 市场行情带 — 从 sentiment 的 indices 提取
    indices = sentiment.get("indices", {})
    market_tape = []
    for key, label in [("sh", "上证"), ("sz", "深成"), ("cyb", "创业板"), ("kcb", "科创50")]:
        idx = indices.get(key, {})
        market_tape.append({
            "symbol": label,
            "price": idx.get("close", 0),
            "changePct": idx.get("change_pct", 0),
        })

    # 模拟账户
    account_snap = {}
    with db_session() as conn:
        rows = conn.execute(
            "SELECT date, total_asset, available_cash, position_value, daily_pnl, holdings"
            " FROM account_snapshot ORDER BY date DESC LIMIT 5"
        ).fetchall()
    for row in rows:
        import json
        account_snap[row[0]] = {
            "totalAsset": row[1],
            "availableCash": row[2],
            "positionValue": row[3],
            "dailyPnl": row[4],
            "holdings": json.loads(row[5]) if row[5] else [],
            "assetCurve": [[row[0], row[1]]],
            "trades": [],
        }

    return {
        "meta": {
            "productName": "日晷",
            "productSubtitle": "Sundial",
            "updatedAt": f"{d[:4]}-{d[4:6]}-{d[6:8]} {date.today().strftime('%H:%M:%S')}",
            "today": iso,
            "historyRange": f"2024-01-01 ~ {iso}",
            "scope": "A股市场实时数据",
        },
        "dailyReplay": {
            "byDate": {
                d: {
                    "sentiment": sentiment,
                    "ladder": ladder,
                    "yesterdayPerformance": yday_perf,
                }
            }
        },
        "hotList": {
            "defaultPeriod": "1500",
            "byDate": {
                iso: hot_slots
            }
        },
        "stockAnalysis": {
            "defaultCode": "600519",
            "intraday": {},
            "intradayFallback": [],
            "blockTrades": {},
            "blockTradesFallback": [],
            "dayK": {},
            "dayKFallback": [],
        },
        "strategyBacktest": {
            "defaultStrategy": "open-breakout",
            "strategies": [
                {"id": "open-breakout", "name": "开盘突破", "description": "开盘价突破前高买入"},
                {"id": "limitup-relay", "name": "涨停接力", "description": "连板股次日追涨"},
                {"id": "sector-rotation", "name": "板块轮动", "description": "热门板块龙头轮动"},
            ],
            "results": {
                "open-breakout": {"curves": [], "metrics": {}},
                "limitup-relay": {"curves": [], "metrics": {}},
                "sector-rotation": {"curves": [], "metrics": {}},
                "default": {"curves": [], "metrics": {}},
            },
        },
        "paperAccount": {
            "byDate": account_snap,
        },
        "stockMeta": {},
        "marketTape": market_tape,
    }
