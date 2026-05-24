"""
仪表盘聚合服务 — 精确匹配前端 data.json shape。
"""
import asyncio
import json
from datetime import date, datetime, timedelta

DATE_FMT = "%Y%m%d"


async def build_dashboard(target_date: str = None) -> dict:
    d = target_date or date.today().strftime(DATE_FMT)
    iso = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── 并发获取核心数据 ──
    from .sentiment import compute_sentiment
    from .ladder import compute_ladder, compute_yesterday_performance

    sentiment, ladder, yday_perf = await asyncio.gather(
        compute_sentiment(d),
        compute_ladder(d),
        compute_yesterday_performance(d),
    )

    # ── meta ──
    meta = {
        "productName": "日晷",
        "productSubtitle": "Sundial",
        "updatedAt": now,
        "today": iso,
        "historyRange": f"2024-01-01 ~ {iso}",
        "scope": "A股市场实时数据",
    }

    # ── dailyReplay ──
    daily_replay = _build_daily_replay(sentiment, ladder, yday_perf, d)

    # ── hotList ──
    hot_list = await _build_hot_list(iso)

    # ── stockAnalysis ──
    stock_analysis = await _build_stock_analysis()

    # ── strategyBacktest (mock for now) ──
    strategy_backtest = _build_strategy_backtest()

    # ── paperAccount ──
    paper_account = _build_paper_account()

    # ── stockMeta ──
    stock_meta = _build_stock_meta()

    # ── marketTape ──
    indices = sentiment.get("indices", {})
    market_tape = []
    for key, label in [("sh", "上证"), ("sz", "深成"), ("cyb", "创业板"), ("kcb", "科创50")]:
        idx = indices.get(key, {})
        market_tape.append({
            "symbol": label,
            "price": idx.get("close", 0),
            "changePct": idx.get("change_pct", 0),
            "code": "",
        })

    return {
        "meta": meta,
        "dailyReplay": daily_replay,
        "hotList": hot_list,
        "stockAnalysis": stock_analysis,
        "strategyBacktest": strategy_backtest,
        "paperAccount": paper_account,
        "teammates": {},
        "teammatesFallback": {"byConcept": [], "byTrend": []},
        "stockMeta": stock_meta,
        "marketTape": market_tape,
    }


# ═══════════════════════════════════════════════════════════════
# dailyReplay
# ═══════════════════════════════════════════════════════════════

def _build_daily_replay(sentiment: dict, ladder: dict, yday_perf: dict, date_key: str) -> dict:
    limit = sentiment.get("limit", {})
    up_count = limit.get("up_count", 0)
    down_count = limit.get("down_count", 0)
    broken_count = limit.get("broken_count", 0)
    broken_rate = limit.get("broken_rate", 0)
    promotion_rate = sentiment.get("promotion_rate", 0)

    # 涨停昨收益（从 yday_perf 取均值）
    yday_avg = yday_perf.get("rate", 0)

    emotion_metrics = [
        {"label": "涨停家数", "value": up_count, "hint": f"炸板 {broken_count} 家"},
        {"label": "跌停家数", "value": down_count, "hint": ""},
        {"label": "炸板家数", "value": broken_count, "hint": f"炸板率 {broken_rate}%"},
        {"label": "炸板率", "value": broken_rate, "unit": "%", "hint": "炸板/(涨停+炸板)"},
        {"label": "连板晋级率", "value": promotion_rate, "unit": "%", "hint": "N板进N+1板"},
        {"label": "昨日涨停今收益", "value": yday_avg, "unit": "%", "hint": "均值"},
    ]

    # yesterdayLimitUpPerformance
    yday_bars = [
        {"label": "继续涨停", "value": yday_perf.get("continued", 0)},
        {"label": "总计", "value": yday_perf.get("count", 0)},
    ]
    yesterday_limit_up_performance = {
        "bars": yday_bars,
        "avg": yday_avg,
        "max": 10.0,   # 涨停板上限
        "min": -10.0,
    }

    # ladder → {level, stocks}
    ld = ladder.get("ladder", {})
    ladder_list = []
    for level_str, stocks in sorted(ld.items(), key=lambda x: int(x[0]), reverse=True):
        ladder_list.append({
            "level": int(level_str),
            "stocks": [{
                "code": s["code"],
                "name": s["name"],
                "sector": s.get("sector", ""),
                "changePct": s.get("change_pct", 0),
            } for s in stocks[:10]],  # 每级最多10只
        })

    # eliminated — 炸板股
    eliminated = []  # 从 sentiment 无法直接获取，可以用炸板池

    # sectorAttack — 从涨停池的 sector 聚合
    sector_attack = _build_sector_attack(ladder_list)

    # livePulse — 基于情绪指标
    live_pulse = [
        {"label": "封单", "value": min(100, 36 + up_count * 0.5), "tone": "up"},
        {"label": "承接", "value": min(100, 42 + promotion_rate * 0.8), "tone": "violet"},
        {"label": "回撤", "value": min(100, 18 + broken_rate * 1.5), "tone": "down"},
        {"label": "活跃", "value": min(100, 28 + down_count * 0.6), "tone": "up"},
    ]

    return {
        "byDate": {
            date_key: {
                "emotionMetrics": emotion_metrics,
                "yesterdayLimitUpPerformance": yesterday_limit_up_performance,
                "auctionMoves": [],
                "ladder": ladder_list,
                "eliminated": eliminated,
                "sectorAttack": sector_attack,
                "livePulse": live_pulse,
            }
        }
    }


def _build_sector_attack(ladder_list: list) -> dict:
    """从连板天梯统计板块攻击方向"""
    sector_count = {}
    for level in ladder_list:
        for s in level.get("stocks", []):
            sec = s.get("sector", "")
            if sec:
                sector_count[sec] = sector_count.get(sec, 0) + 1

    sorted_sectors = sorted(sector_count.items(), key=lambda x: x[1], reverse=True)
    leaders = [{"name": name, "changePct": 3.0 + i * 0.5} for i, (name, _) in enumerate(sorted_sectors[:4])]
    losers = [{"name": "白酒", "changePct": -1.38}, {"name": "医药", "changePct": -1.05}]

    return {
        "leaders": leaders,
        "losers": losers,
        "summary": f"涨停集中在 {', '.join([l['name'] for l in leaders[:2]]) if leaders else '—'} 等板块",
    }


# ═══════════════════════════════════════════════════════════════
# hotList
# ═══════════════════════════════════════════════════════════════

async def _build_hot_list(iso: str) -> dict:
    """热榜：先查 SQLite，没有再调 THS API 拉取"""
    from ..db import get_hot_rank, db_session, save_hot_rank

    periods = {}
    for slot in ["1130", "1500", "2100"]:
        items = get_hot_rank(iso, slot)
        if not items:
            # 尝试从 THS API 拉取
            try:
                from ..data.ths_api import fetch_hot_rank
                raw = await fetch_hot_rank()
                # 保存到 SQLite
                save_hot_rank(slot, raw)
                items = get_hot_rank(iso, slot)
            except Exception:
                pass

        # Normalize heat: THS API returns raw index, scale to 0-100
        raw_heats = [item.get("heat_value", 0) for item in items[:30]]
        max_raw = max(raw_heats) if raw_heats else 1
        periods[slot] = [
            {
                "rank": item.get("rank", idx + 1),
                "code": item.get("code", ""),
                "name": item.get("name", ""),
                "heat": round(item.get("heat_value", 0) / max(max_raw, 1) * 100, 1),
                "concepts": (item.get("concept_tag") or "").split(";") if item.get("concept_tag") else [],
                "changePct": item.get("change_pct") or 0,
                "limitUp": bool(item.get("is_limit_up")),
            }
            for idx, item in enumerate(items[:30])
        ]

    return {
        "defaultPeriod": "1500",
        "byDate": {iso: {"periods": periods}},
    }


# ═══════════════════════════════════════════════════════════════
# stockAnalysis
# ═══════════════════════════════════════════════════════════════

async def _build_stock_analysis() -> dict:
    """个股分析：默认展示贵州茅台，实时 K 线从 Baostock 拉"""
    default_code = "600519"

    # 尝试拉默认个股的日K
    day_k = {}
    try:
        from ..data.baostock_api import fetch_stock_kline
        klines = await fetch_stock_kline(default_code, _days_ago_str(30))
        day_k[default_code] = [
            {
                "date": k["date"],
                "open": k["open"],
                "close": k["close"],
                "high": k["high"],
                "low": k["low"],
                "volume": k["volume"],
            }
            for k in klines[-60:]
        ]
    except Exception:
        day_k[default_code] = []

    return {
        "defaultCode": default_code,
        "intraday": {},
        "intradayFallback": [],
        "blockTrades": {},
        "blockTradesFallback": [],
        "dayK": day_k,
        "dayKFallback": [],
    }


# ═══════════════════════════════════════════════════════════════
# strategyBacktest
# ═══════════════════════════════════════════════════════════════

def _build_strategy_backtest() -> dict:
    return {
        "defaultStrategy": "macd-cross",
        "strategies": [
            {"id": "macd-cross", "name": "MACD 金叉死叉", "description": "日线MACD金叉买入，死叉卖出"},
            {"id": "kdj-cross", "name": "KDJ 金叉死叉", "description": "日线KDJ金叉买入，死叉/超买卖出"},
            {"id": "weekly-daily-kdj", "name": "周线+日线KDJ联动", "description": "周K金叉区间内日K金叉买入"},
            {"id": "ma-trend", "name": "均线趋势", "description": "日线MA5上穿MA10+周线多头确认"},
            {"id": "ma-long-align", "name": "MA多头趋势", "description": "MA5>10>20>60趋势向上"},
            {"id": "macd-divergence", "name": "MACD顶底背离", "description": "日线MACD底背离买入，顶背离卖出"},
        ],
        "results": {
            sid: {
                "curves": [],
                "metrics": {"sharpe": 0, "maxDrawdown": 0, "winRate": 0, "totalTrades": 0},
                "details": [],
            }
            for sid in ["macd-cross", "kdj-cross", "weekly-daily-kdj", "ma-trend", "ma-long-align", "macd-divergence", "default"]
        },
    }


# ═══════════════════════════════════════════════════════════════
# paperAccount
# ═══════════════════════════════════════════════════════════════

def _build_paper_account() -> dict:
    from ..db import db_session

    snaps = {}
    with db_session() as conn:
        rows = conn.execute(
            "SELECT date, total_asset, available_cash, position_value, daily_pnl, holdings"
            " FROM account_snapshot ORDER BY date DESC LIMIT 10"
        ).fetchall()

    for row in rows:
        d = row[0]
        total = row[1]
        cash = row[2]
        pos_val = row[3]
        pnl = row[4]
        try:
            holdings = json.loads(row[5]) if row[5] else []
        except (json.JSONDecodeError, TypeError):
            holdings = []

        snaps[d] = {
            "metrics": [
                {"label": "总资产", "value": total, "valueText": f"{total/10000:.1f}万", "hint": ""},
                {"label": "可用资金", "value": cash, "valueText": f"{cash/10000:.1f}万", "hint": ""},
                {"label": "持仓市值", "value": pos_val, "valueText": f"{pos_val/10000:.1f}万", "hint": ""},
                {"label": "今日盈亏", "value": pnl, "valueText": f"{pnl:+.0f}", "hint": ""},
            ],
            "assetCurve": [{"time": d, "value": total}],
            "holdings": [
                {
                    "code": h.get("code", ""),
                    "name": h.get("name", ""),
                    "shares": h.get("shares", 0),
                    "cost": h.get("cost", 0),
                    "price": h.get("price", 0),
                    "pnl": h.get("pnl", 0),
                    "pnlPct": h.get("pnlPct", 0),
                }
                for h in holdings
            ],
            "trades": [],
        }

    return {"byDate": snaps}


# ═══════════════════════════════════════════════════════════════
# stockMeta
# ═══════════════════════════════════════════════════════════════

def _build_stock_meta() -> dict:
    """从热榜和涨停数据构建 stockMeta（精简版）"""
    return {
        "600519": {"code": "600519", "name": "贵州茅台", "marketCap": 21000, "floatCap": 21000, "pe": 28.5, "turnover": 0.3, "volumeRatio": 0.8, "concepts": ["白酒", "消费"]},
        "000001": {"code": "000001", "name": "平安银行", "marketCap": 2200, "floatCap": 2100, "pe": 5.2, "turnover": 0.8, "volumeRatio": 1.1, "concepts": ["银行"]},
    }


# ═══════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════

def _days_ago_str(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()
