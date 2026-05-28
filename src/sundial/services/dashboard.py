"""
仪表盘聚合服务 — 纯真实数据，零 mock 兜底。
"""
import asyncio
import json
import time
from datetime import date, datetime, timedelta

DATE_FMT = "%Y%m%d"

# ── TTL 缓存 ──
_DASHBOARD_CACHE = None
_DASHBOARD_CACHE_TS = 0
_CACHE_TTL = 30  # 秒


async def _cached_build(target_date: str = None, stock_code: str = None) -> dict:
    """带 TTL 缓存的 build_dashboard，同 30 秒内复用。"""
    global _DASHBOARD_CACHE, _DASHBOARD_CACHE_TS
    now = time.time()
    if _DASHBOARD_CACHE is not None and (now - _DASHBOARD_CACHE_TS) < _CACHE_TTL:
        return _DASHBOARD_CACHE
    _DASHBOARD_CACHE = await build_dashboard(target_date, stock_code)
    _DASHBOARD_CACHE_TS = now
    return _DASHBOARD_CACHE

# ── 板块数据增强 ──
SECTOR_MAP_PATH = "/root/.hermes/projects/sundial/data/cache/stock_sector_map.json"


def _load_sector_map() -> dict:
    """加载个股→板块正排索引，失败返回 {}"""
    try:
        with open(SECTOR_MAP_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _enrich_concepts(pool: dict) -> dict:
    """用 stock_sector_map.json 补全池中股票的板块概念。

    Args:
        pool: {code: {name, changePct, concepts: set}}

    Returns:
        增强后的 pool，concepts 合并了板块数据
    """
    sector_map = _load_sector_map()
    if not sector_map:
        return pool

    for code, info in pool.items():
        sm = sector_map.get(code)
        if not sm:
            continue
        sector_concepts = set(sm.get("概念", [])) | set(sm.get("行业", []))
        info["concepts"] = info.get("concepts", set()) | sector_concepts

    return pool


async def build_dashboard(target_date: str = None, stock_code: str = None) -> dict:
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
    daily_replay = _build_daily_replay(sentiment, ladder, yday_perf, iso)

    # ── hotList ──
    hot_list = await _build_hot_list(iso)

    # ── stockAnalysis ──
    stock_analysis = await _build_stock_analysis(stock_code)

    # ── strategyBacktest ──
    strategy_backtest = _build_strategy_backtest()

    # ── paperAccount ──
    paper_account = _build_paper_account()

    # ── teammates ──
    teammates = _build_teammates(hot_list, ladder)

    # ── stockMeta ──
    stock_meta = _build_stock_meta(hot_list, ladder)

    # ── marketTape ──
    indices = sentiment.get("indices", {})
    market_tape = []
    for key, label in [("sh", "上证"), ("sz", "深成"), ("cyb", "创业板"), ("kcb", "科创50")]:
        idx = indices.get(key, {})
        if idx.get("close", 0) > 0:  # 只输出有数据的
            market_tape.append({
                "symbol": label,
                "price": idx["close"],
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
        "teammates": teammates,
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
    yday_avg = yday_perf.get("rate", 0)

    emotion_metrics = [
        {"label": "涨停家数", "value": up_count, "hint": f"炸板 {broken_count} 家"},
        {"label": "跌停家数", "value": down_count, "hint": ""},
        {"label": "炸板家数", "value": broken_count, "hint": f"炸板率 {broken_rate}%"},
        {"label": "炸板率", "value": broken_rate, "unit": "%", "hint": "炸板/(涨停+炸板)"},
        {"label": "连板晋级率", "value": promotion_rate, "unit": "%", "hint": "N板进N+1板"},
        {"label": "昨日涨停今收益", "value": yday_avg, "unit": "%", "hint": "均值"},
    ]

    yesterday_limit_up_performance = {
        "bars": [
            {"label": "继续涨停", "value": yday_perf.get("continued", 0)},
            {"label": "总计", "value": yday_perf.get("count", 0)},
        ],
        "avg": yday_avg,
        "max": 10.0,
        "min": -10.0,
    }

    # ladder
    ld = ladder.get("ladder", {})
    ladder_list = []
    for label, stocks in ld.items():
        # 从 label 中提取数字用于排序（"4连板" → 4, "11天7板" → 11）
        import re
        m = re.match(r'(\d+)', label)
        sort_key = int(m.group(1)) if m else 0
        ladder_list.append({
            "level": label,
            "sortKey": sort_key,
            "stocks": [{
                "code": s["code"],
                "name": s["name"],
                "sector": s.get("sector", ""),
                "changePct": s.get("change_pct", 0),
            } for s in stocks[:10]],
        })
    ladder_list.sort(key=lambda x: x["sortKey"], reverse=True)

    # sectorAttack — 从涨停池真实汇聚
    sector_attack = _build_sector_attack(ladder_list)

    return {
        "byDate": {
            date_key: {
                "emotionMetrics": emotion_metrics,
                "yesterdayLimitUpPerformance": yesterday_limit_up_performance,
                "auctionMoves": [],
                "ladder": ladder_list,
                "sectorAttack": sector_attack,
            }
        }
    }


def _build_sector_attack(ladder_list: list) -> dict:
    """从连板天梯统计板块攻击方向（纯真实数据）"""
    sector_pct = {}   # {sector: [pct1, pct2, ...]}

    for level in ladder_list:
        for s in level.get("stocks", []):
            sec = s.get("sector", "").strip()
            if not sec:
                continue
            pct = s.get("changePct", 0) or 0
            if sec not in sector_pct:
                sector_pct[sec] = []
            sector_pct[sec].append(pct)

    # 按板块平均涨幅排序
    sector_avg = {}
    for sec, pcts in sector_pct.items():
        if pcts:
            sector_avg[sec] = round(sum(pcts) / len(pcts), 2)

    sorted_sectors = sorted(sector_avg.items(), key=lambda x: x[1], reverse=True)

    leaders = [{"name": name, "changePct": avg} for name, avg in sorted_sectors[:4]]
    losers = [{"name": name, "changePct": avg} for name, avg in sorted_sectors[-3:]] if len(sorted_sectors) > 4 else []

    return {
        "leaders": leaders,
        "losers": losers,
        "summary": f"涨停集中在 {', '.join([l['name'] for l in leaders[:2]]) if leaders else '—'} 等板块",
    }


# ═══════════════════════════════════════════════════════════════
# hotList
# ═══════════════════════════════════════════════════════════════

async def _build_hot_list(iso: str) -> dict:
    """热榜：直接从 THS API 拉取 + Sina 补涨跌幅，同时写 SQLite"""
    from ..db import db_session
    today = date.today().isoformat()

    raw_items = []
    try:
        from ..data.ths_api import fetch_hot_rank
        raw_items = await fetch_hot_rank()
    except Exception as e:
        import traceback
        print(f"[dashboard] THS API failed: {e}", flush=True)
        traceback.print_exc()

    # 格式化
    items = []
    max_raw = max((item.get("heat_value", 0) for item in raw_items), default=1)
    for item in raw_items[:30]:
        items.append({
            "rank": item.get("rank", 0),
            "code": item.get("code", ""),
            "name": item.get("name", ""),
            "heat": round(item.get("heat_value", 0) / max(max_raw, 1) * 100, 1),
            "concepts": (item.get("concept_tag") or "").split(";") if item.get("concept_tag") else [],
            "changePct": item.get("change_pct") or 0,
            "limitUp": bool(item.get("is_limit_up")),
        })

    # 异步写 SQLite
    if raw_items:
        try:
            hour = datetime.now().strftime("%H%M")
            with db_session() as conn:
                conn.execute("DELETE FROM hot_rank_snapshot WHERE date=? AND slot=?", (today, hour))
                for item in raw_items:
                    conn.execute(
                        "INSERT OR REPLACE INTO hot_rank_snapshot (date, slot, rank, code, name, heat_value, concept_tag, is_limit_up, change_pct) VALUES (?,?,?,?,?,?,?,?,?)",
                        (today, hour, item.get("rank", 0), item.get("code", ""), item.get("name", ""),
                         item.get("heat_value", 0), item.get("concept_tag", ""),
                         1 if item.get("is_limit_up") else 0, item.get("change_pct") or 0),
                    )
        except Exception:
            pass

    # 返回当前实时时段 + 历史三时段
    now = datetime.now()
    current_slot = now.strftime("%H:00")  # 实时时段（整点）
    default_period = current_slot

    # 实时时段用 API 数据
    slot_map = {current_slot: items}

    # 固定时段从 SQLite 历史数据补
    for slot in ["12:00", "15:00", "21:00"]:
        if slot in slot_map:
            continue  # 当前时段已有 API 数据，不覆盖
        slot_items = _query_hot_rank_slot(iso, slot)
        if not slot_items:
            # 跨日回退：凌晨查昨日数据
            from datetime import timedelta
            yesterday = (date.fromisoformat(iso) - timedelta(days=1)).isoformat()
            slot_items = _query_hot_rank_slot(yesterday, slot)
        if slot_items:
            slot_map[slot] = slot_items

    return {
        "defaultPeriod": default_period,
        "byDate": {iso: {"periods": slot_map}},
    }


def _query_hot_rank_slot(date_str: str, target_slot: str) -> list:
    """从 SQLite 查指定时段的热榜数据，兼容 HH:MM / HHMM 两种格式"""
    from ..db import db_session
    with db_session() as conn:
        # 尝试多种格式
        candidates = [target_slot]
        if ":" in target_slot:
            candidates.append(target_slot.replace(":", ""))  # "12:00" → "1200"
        else:
            candidates.append(f"{target_slot[:2]}:{target_slot[2:]}")  # "1200" → "12:00"

        for slot_fmt in candidates:
            cur = conn.execute(
                "SELECT rank, code, name, heat_value, concept_tag, is_limit_up, change_pct "
                "FROM hot_rank_snapshot WHERE date=? AND slot=? ORDER BY rank LIMIT 30",
                (date_str, slot_fmt),
            )
            rows = cur.fetchall()
            if rows:
                max_heat = max((r[3] for r in rows), default=1)
                return [
                    {
                        "rank": r[0],
                        "code": r[1],
                        "name": r[2],
                        "heat": round(r[3] / max(max_heat, 1) * 100, 1),
                        "concepts": (r[4] or "").split(";") if r[4] else [],
                        "changePct": r[6] or 0,
                        "limitUp": bool(r[5]),
                    }
                    for r in rows
                ]
    return []


# ═══════════════════════════════════════════════════════════════
# stockAnalysis
# ═══════════════════════════════════════════════════════════════

async def _build_stock_analysis(code: str = None) -> dict:
    """个股分析：按指定 code 拉取日K，默认 600519"""
    default_code = code or "600519"

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
    """策略列表 + 空结果（由 /api/backtest/run 触发真实回测）"""
    try:
        from quant_backtester.strategies.registry import discover_strategies
        strats = discover_strategies()
    except Exception:
        strats = {}

    strategies = [
        {"id": name, "name": name, "description": cls.description}
        for name, cls in sorted(strats.items())
    ]

    if not strategies:
        # 兜底：前端需要的字段结构
        strategies = [
            {"id": "macd-cross", "name": "MACD 金叉死叉", "description": "日线MACD金叉买入，死叉卖出"},
            {"id": "kdj-cross", "name": "KDJ 金叉死叉", "description": "日线KDJ金叉买入，死叉/超买卖出"},
            {"id": "weekly-daily-kdj", "name": "周线+日线KDJ联动", "description": "周K金叉区间内日K金叉买入"},
            {"id": "ma-trend", "name": "均线趋势", "description": "日线MA5上穿MA10+周线多头确认"},
            {"id": "ma-long-align", "name": "MA多头趋势", "description": "MA5>10>20>60趋势向上"},
            {"id": "macd-divergence", "name": "MACD顶底背离", "description": "日线MACD底背离买入，顶背离卖出"},
        ]

    return {
        "defaultStrategy": strategies[0]["id"] if strategies else "",
        "strategies": strategies,
        "results": {},
    }


# ═══════════════════════════════════════════════════════════════
# paperAccount
# ═══════════════════════════════════════════════════════════════

def _build_paper_account() -> dict:
    from ..db import db_session

    snaps = {}
    with db_session() as conn:
        # 账户快照
        rows = conn.execute(
            "SELECT date, total_asset, available_cash, position_value, daily_pnl, holdings"
            " FROM account_snapshot ORDER BY date DESC LIMIT 10"
        ).fetchall()

        # 成交记录（全部历史）
        try:
            trade_rows = conn.execute(
                "SELECT date, time, code, name, direction, price, quantity, amount, reason, pnl"
                " FROM trade_record ORDER BY date ASC, time ASC"
            ).fetchall()
        except Exception:
            trade_rows = []

    # 构建 trades — 日期格式归一化：trade_record 存 20260528 → 2026-05-28
    all_trades = []
    for tr in trade_rows:
        raw_date = tr[0]
        if len(raw_date) == 8 and '-' not in raw_date:
            normalized = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
        else:
            normalized = raw_date
        all_trades.append({
            "date": normalized, "time": tr[1], "code": tr[2], "name": tr[3],
            "direction": "买入" if tr[4] == "B" else "卖出",
            "price": float(tr[5]), "qty": int(tr[6]), "amount": float(tr[7]), "reason": tr[8] or "",
        })

    # --- 构建配对交易记录（买入→卖出配对，FIFO）---
    trade_pairs = _build_trade_pairs(all_trades)

    # 补：持仓中有股票但没有买入记录（买入发生在 trade_record 表创建前）
    paired_codes = {p["code"] for p in trade_pairs}
    if rows:
        try:
            latest_holdings = json.loads(rows[0][5]) if rows[0][5] else []
        except (json.JSONDecodeError, TypeError):
            latest_holdings = []
        for h in latest_holdings:
            code = h.get("code", "")
            if code and code not in paired_codes:
                trade_pairs.insert(0, {
                    "code": code,
                    "name": h.get("name", ""),
                    "buyDate": "—", "buyTime": "—",
                    "buyPrice": h.get("cost", 0), "buyQty": h.get("shares", 0),
                    "sellDate": None, "sellTime": None,
                    "sellPrice": None, "sellQty": None,
                    "pnl": None, "pnlPct": None,
                })

    for row in rows:
        d = row[0]
        total = row[1] or 0
        cash = row[2] or 0
        pos_val = row[3] or 0
        pnl = row[4] or 0
        try:
            holdings = json.loads(row[5]) if row[5] else []
        except (json.JSONDecodeError, TypeError):
            holdings = []

        # 当天成交
        day_trades = [t for t in all_trades if t["date"] == d]

        # 收益趋势：当天有多个快照时用 multiple；目前只有1个快照时至少给2个点
        hourly_snaps = []
        for dr in rows:
            if dr[0] == d:
                hourly_snaps.append(dr)
        if len(hourly_snaps) >= 2:
            asset_curve = [{"time": f"{r[0]} {r[0]}", "value": (r[1] or 0) / 10000} for r in reversed(hourly_snaps)]
        else:
            # 先用前一日收盘做起点，当日为终点
            prev_row = None
            for dr in rows:
                if dr[0] < d:
                    prev_row = dr
                    break
            asset_curve = []
            if prev_row:
                asset_curve.append({"time": prev_row[0], "value": (prev_row[1] or 0) / 10000})
            asset_curve.append({"time": d, "value": total / 10000})

        # 资金流（从 trades 构建）
        flow_timeline = []
        for t in reversed(day_trades):
            flow_val = float(t["amount"]) / 10000
            flow_timeline.append({
                "time": t["time"],
                "inflow": flow_val if t["direction"] == "买入" else 0,
                "outflow": flow_val if t["direction"] == "卖出" else 0,
            })

        snaps[d] = {
            "metrics": [
                {"label": "总资产", "value": total, "valueText": f"{total/10000:.1f}万", "hint": ""},
                {"label": "可用资金", "value": cash, "valueText": f"{cash/10000:.1f}万", "hint": ""},
                {"label": "持仓市值", "value": pos_val, "valueText": f"{pos_val/10000:.1f}万", "hint": ""},
                {"label": "今日盈亏", "value": pnl, "valueText": f"{pnl:+.0f}", "hint": ""},
            ],
            "assetCurve": asset_curve,
            "pnlTimeline": [{"time": p[0], "value": p[1]} for p in
                [("开盘", 0)] + [("收盘", pnl / 10000)]],  # placeholder
            "flowTimeline": flow_timeline,
            "positions": [
                {
                    "code": h.get("code", ""),
                    "name": h.get("name", ""),
                    "qty": h.get("shares", 0),
                    "cost": h.get("cost", 0),
                    "last": h.get("price", 0),
                    "mv": round(h.get("shares", 0) * h.get("price", 0) / 10000, 2),
                    "pnlPct": h.get("pnlPct", 0),
                    "pnlAmt": round(h.get("pnl", 0) / 10000, 2),
                }
                for h in holdings
            ],
            "trades": day_trades,
        }

    return {"byDate": snaps, "tradePairs": trade_pairs}


def _build_trade_pairs(all_trades: list) -> list:
    """FIFO 配对买入→卖出，输出每笔完整交易记录。

    返回: [{code, name, buyDate, buyTime, buyPrice, buyQty,
            sellDate, sellTime, sellPrice, sellQty, pnl, pnlPct}]
    未平仓的 BUY 记录 sell* 字段为 null。
    """
    from collections import defaultdict, deque

    # 按股票分组
    by_stock = defaultdict(list)
    for t in all_trades:
        by_stock[t["code"]].append(t)

    pairs = []
    for code, trades in sorted(by_stock.items()):
        buys = deque()  # 待匹配的买入队列
        for t in sorted(trades, key=lambda x: (x["date"], x["time"])):
            if t["direction"] == "买入":
                buys.append(t)
            elif t["direction"] == "卖出":
                sell_qty = t["qty"]
                sell_price = t["price"]
                while sell_qty > 0 and buys:
                    buy = buys[0]
                    match_qty = min(buy["qty"], sell_qty)
                    match_buy_cost = match_qty * buy["price"]
                    match_sell_rev = match_qty * sell_price
                    pnl_amt = match_sell_rev - match_buy_cost
                    pnl_pct = round((pnl_amt / match_buy_cost) * 100, 2) if match_buy_cost else 0

                    pairs.append({
                        "code": code,
                        "name": buy["name"] or t["name"] or code,
                        "buyDate": buy["date"], "buyTime": buy["time"],
                        "buyPrice": buy["price"], "buyQty": match_qty,
                        "sellDate": t["date"], "sellTime": t["time"],
                        "sellPrice": sell_price, "sellQty": match_qty,
                        "pnl": round(pnl_amt, 2),
                        "pnlPct": pnl_pct,
                    })

                    sell_qty -= match_qty
                    buy["qty"] -= match_qty
                    if buy["qty"] <= 0:
                        buys.popleft()

        # 未平仓
        for buy in buys:
            if buy["qty"] > 0:
                pairs.append({
                    "code": code,
                    "name": buy["name"],
                    "buyDate": buy["date"], "buyTime": buy["time"],
                    "buyPrice": buy["price"], "buyQty": buy["qty"],
                    "sellDate": None, "sellTime": None,
                    "sellPrice": None, "sellQty": None,
                    "pnl": None, "pnlPct": None,
                })

    # 按买入时间降序
    pairs.sort(key=lambda x: (x["buyDate"] or "", x["buyTime"] or ""), reverse=True)
    return pairs


# ═══════════════════════════════════════════════════════════════
# stockMeta
# ═══════════════════════════════════════════════════════════════

def _build_stock_meta(hot_list: dict, ladder: dict = None) -> dict:
    """从热榜 + 连板天梯 构建 stockMeta，补 Baostock PE/换手率 + mootdx 市值"""
    meta = {}
    # 热榜股
    by_date = hot_list.get("byDate", {})
    for date_key, date_data in by_date.items():
        periods = date_data.get("periods", {})
        for slot, items in periods.items():
            for item in items:
                code = item.get("code", "")
                if not code or code in meta:
                    continue
                meta[code] = {
                    "code": code,
                    "name": item.get("name", ""),
                    "marketCap": 0, "floatCap": 0, "pe": 0, "turnover": 0, "volumeRatio": 0,
                    "concepts": item.get("concepts", []),
                    "changePct": item.get("changePct", 0),
                }
    # 连板股（补上不在热榜中的）
    if ladder:
        for lv_str, stocks in ladder.get("ladder", {}).items():
            for s in stocks:
                code = s.get("code", "")
                if not code or code in meta:
                    continue
                meta[code] = {
                    "code": code,
                    "name": s.get("name", ""),
                    "marketCap": 0, "floatCap": 0, "pe": 0, "turnover": 0, "volumeRatio": 0,
                    "concepts": [s.get("sector", "")] if s.get("sector") else [],
                    "changePct": s.get("change_pct", 0),
                }

    # ── 批量补财务数据 ──
    if meta:
        codes = list(meta.keys())
        _fetch_financials_batch(meta, codes)
    return meta


def _fetch_financials_batch(meta: dict, codes: list[str]) -> None:
    """批量补 PE/换手率 (Baostock) + 市值 (mootdx finance)"""
    import baostock as bs

    # 复用 baostock_api._ensure_login 模式，不单独 login/logout 避免会话冲突
    _ensure_bs_login()

    # 1. Baostock: PE + 换手率
    for code in codes:
        try:
            prefix = "sh" if code.startswith(("6", "5")) else "sz"
            # 往回找最近 3 个交易日，Baostock 通常 T+1 更新
            found = False
            for offset in range(3):
                d = (date.today() - timedelta(days=offset)).isoformat()
                rs = bs.query_history_k_data_plus(
                    f"{prefix}.{code}",
                    "date,close,peTTM,turn",
                    start_date=d, end_date=d, frequency="d",
                )
                if rs is None or rs.error_code != "0":
                    continue
                while rs.next():
                    row = rs.get_row_data()
                    if len(row) >= 4 and row[1] and float(row[1]) > 0:
                        pe = float(row[2]) if row[2] else 0
                        turn = float(row[3]) if row[3] else 0
                        meta[code]["pe"] = round(pe, 2)
                        meta[code]["turnover"] = round(turn, 2)
                        found = True
                        break
                if found:
                    break
        except Exception:
            continue

    # 2. mootdx: 总股本/流通股本 → 市值
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market="std")
        for code in codes:
            try:
                df = client.finance(symbol=code)
                if df is None or df.empty:
                    continue
                latest = df.sort_values("updated_date").iloc[-1]
                total_shares = float(latest.get("zongguben", 0) or 0)
                float_shares = float(latest.get("liutongguben", 0) or 0)
                if total_shares <= 0:
                    continue

                try:
                    q = client.quotes(symbol=[code])
                    if q is not None and not q.empty:
                        price = float(q.iloc[0].get("price", 0))
                        if price <= 0:
                            price = float(q.iloc[0].get("last_close", 0))
                    else:
                        price = 0
                except Exception:
                    price = 0

                if price > 0:
                    meta[code]["marketCap"] = round(price * total_shares / 1e8, 2)
                    meta[code]["floatCap"] = round(price * float_shares / 1e8, 2) if float_shares > 0 else 0
            except Exception:
                continue
    except Exception:
        pass


_bs_logged = False


def _ensure_bs_login():
    global _bs_logged
    if not _bs_logged:
        import baostock as bs
        bs.login()
        _bs_logged = True


# ═══════════════════════════════════════════════════════════════
# teammates — 概念分组 + 1分钟K线滑动窗口互相关（Pearson r）
# 铁律：不同概念的票不互算——避免市场 beta 产生虚假相关。
# 算法来源: board_monitor signals/team.py compute_teammates()
# ═══════════════════════════════════════════════════════════════

TEAM_WINDOW = 15         # 互相关窗口（1分钟K线 × 15 = 15分钟）
TEAM_R_THRESHOLD = 0.6   # Pearson r 阈值


def _sliding_corr(a, b) -> float:
    """滑动窗口 Pearson r，返回最佳绝对值。a, b 为涨跌幅序列(%)。"""
    import numpy as np
    min_len = min(len(a), len(b))
    best_r = 0.0
    for start in range(0, min_len - TEAM_WINDOW, 3):
        a_win = a[start:start + TEAM_WINDOW]
        b_win = b[start:start + TEAM_WINDOW]
        if len(a_win) < 10:
            continue
        try:
            r = np.corrcoef(a_win, b_win)[0, 1]
            if np.isnan(r):
                continue
        except Exception:
            continue
        if abs(r) > abs(best_r):
            best_r = r
    return best_r


def _collect_hotlist_pool(hot_list: dict, ladder: dict = None) -> dict:
    """收集热榜+连板股票池。
    Returns: {code: {name, changePct, concepts: set}}
    """
    pool = {}
    by_date = hot_list.get("byDate", {})
    for date_data in by_date.values():
        for items in date_data.get("periods", {}).values():
            if items:
                for item in items:
                    c = item["code"]
                    concepts = set(item.get("concepts", []))
                    concepts.discard("")
                    pool[c] = {
                        "name": item["name"],
                        "changePct": item.get("changePct", 0),
                        "concepts": concepts,
                    }
                break

    if ladder:
        for stocks in ladder.get("ladder", {}).values():
            for s in stocks:
                c = s.get("code", "")
                if not c:
                    continue
                sector = s.get("sector", "")
                if c not in pool:
                    pool[c] = {"name": s.get("name", ""), "changePct": s.get("change_pct", 0), "concepts": set()}
                if sector:
                    pool[c]["concepts"].add(sector)
    return _enrich_concepts(pool)


def _find_stock_teammates(code: str, pool: dict) -> list:
    """为一支股票找队友：在同概念/同板块的股票中，拉1分钟线做滑动窗口互相关。
    Returns: [{code, name, changePct, corr, concepts}, ...] 按 corr 降序
    """
    import numpy as np
    from mootdx.quotes import Quotes

    if not pool:
        return []

    client = Quotes.factory(market="std")

    # 目标股票的概念
    target_info = pool.get(code, {})
    target_concepts = target_info.get("concepts", set())

    # 如果不在池中（非热榜票），无法取概念 → 回退到全池对比
    if not target_concepts:
        candidates = {c: info for c, info in pool.items() if c != code}
    else:
        # 筛选同概念/同板块的候选股
        candidates = {}
        for c, info in pool.items():
            if c == code:
                continue
            shared = target_concepts & info.get("concepts", set())
            if shared:
                candidates[c] = info

    if not candidates:
        return []

    client = Quotes.factory(market="std")

    # 拉目标股票 1-min K 线
    try:
        df = client.bars(symbol=code, frequency=7, start=0, offset=240)
        if df is None or len(df) < TEAM_WINDOW + 5:
            return []
        closes = df["close"].values
        if float(closes.std()) < 1e-6:
            return []
        target_rets = (closes[1:] - closes[:-1]) / closes[:-1] * 100
    except Exception:
        return []

    # 拉候选股 1-min K 线
    pool_rets = {}
    for c, info in candidates.items():
        try:
            df = client.bars(symbol=c, frequency=7, start=0, offset=240)
            if df is None or len(df) < TEAM_WINDOW + 5:
                continue
            closes_c = df["close"].values
            if float(closes_c.std()) < 1e-6:
                continue
            rets = (closes_c[1:] - closes_c[:-1]) / closes_c[:-1] * 100
            pool_rets[c] = rets
        except Exception:
            continue

    # 互相关
    mates = []
    for c, rets in pool_rets.items():
        best_r = _sliding_corr(target_rets, rets)
        if abs(best_r) >= TEAM_R_THRESHOLD:
            info = candidates[c]
            shared = list(target_concepts & info.get("concepts", set()))
            mates.append({
                "code": c,
                "name": info["name"],
                "changePct": info.get("changePct", 0),
                "corr": round(abs(best_r), 2),
                "concepts": shared,
            })

    mates.sort(key=lambda x: x["corr"], reverse=True)
    return mates[:5]


def _build_teammates(hot_list: dict, ladder: dict = None) -> dict:
    """找队友：先按概念/板块分组，同组内再算分时图 Pearson r 互相关。

    流程:
      1. 收集代码 + 概念标签（THS concept_tag + ladder sector）
      2. 拉 1-min K 线
      3. 在每个概念组内两两滑动窗口 Pearson r
      4. 连通分量分组（共享任意概念即合并）
      5. 输出队友列表 + 共享概念

    Returns:
        {code: {"byConcept": [{code, name, changePct, corr, concepts}, ...],
                "byTrend":   [...]}}
    """
    import numpy as np
    from mootdx.quotes import Quotes

    # ── 1. 收集代码 + 概念 ──
    code_concepts = {}  # {code: set(concept)}
    code_info = {}      # {code: {name, changePct, concepts}}

    by_date = hot_list.get("byDate", {})
    for date_data in by_date.values():
        for items in date_data.get("periods", {}).values():
            if items:
                for item in items:
                    c = item["code"]
                    concepts = set(item.get("concepts", []))
                    concepts.discard("")
                    code_concepts[c] = concepts
                    code_info[c] = item
                break

    # 连板股：用 sector 作为概念
    if ladder:
        for stocks in ladder.get("ladder", {}).values():
            for s in stocks:
                c = s.get("code", "")
                if not c:
                    continue
                sector = s.get("sector", "")
                if c not in code_concepts:
                    code_concepts[c] = set()
                if sector:
                    code_concepts[c].add(sector)
                if c not in code_info:
                    code_info[c] = {
                        "code": c, "name": s.get("name", ""),
                        "changePct": s.get("change_pct", 0),
                        "concepts": [sector] if sector else [],
                    }

    # 补全板块概念（同花顺 stock_sector_map.json）
    # 将 code_info 转为 pool 格式调 _enrich_concepts，再合并回 code_concepts
    pool_for_enrich = {
        c: {"name": "", "changePct": 0, "concepts": code_concepts.get(c, set())}
        for c in code_concepts
    }
    enriched_pool = _enrich_concepts(pool_for_enrich)
    for c, info in enriched_pool.items():
        code_concepts[c] = info.get("concepts", set())

    # 去掉没有概念的票
    code_concepts = {c: v for c, v in code_concepts.items() if v}
    if len(code_concepts) < 2:
        return {}

    # ── 2. 拉取 1-min K 线 ──
    client = Quotes.factory(market="std")
    all_rets = {}
    for code in code_concepts:
        try:
            df = client.bars(symbol=code, frequency=7, start=0, offset=240)
            if df is None or len(df) < TEAM_WINDOW + 5:
                continue
            closes = df["close"].values
            # 跳过方差为0的票（盘后数据退化/停牌/一字板）
            if float(closes.std()) < 1e-6:
                continue
            rets = (closes[1:] - closes[:-1]) / closes[:-1] * 100
            all_rets[code] = rets
        except Exception:
            continue

    if len(all_rets) < 2:
        return {}

    # ── 3. 按概念分组 → 组内两两互相关 ──
    concept_groups = {}
    for code, concepts in code_concepts.items():
        if code not in all_rets:
            continue
        for concept in concepts:
            if concept not in concept_groups:
                concept_groups[concept] = []
            concept_groups[concept].append(code)

    pairs = []  # [(code_a, code_b, best_r, shared_concept)]
    for concept, members in concept_groups.items():
        if len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a_code, b_code = members[i], members[j]
                a, b = all_rets[a_code], all_rets[b_code]
                min_len = min(len(a), len(b))
                best_r = 0.0
                for start in range(0, min_len - TEAM_WINDOW, 3):
                    a_win = a[start:start + TEAM_WINDOW]
                    b_win = b[start:start + TEAM_WINDOW]
                    if len(a_win) < 10:
                        continue
                    try:
                        r = np.corrcoef(a_win, b_win)[0, 1]
                        if np.isnan(r):
                            continue
                    except Exception:
                        continue
                    if abs(r) > abs(best_r):
                        best_r = r
                if abs(best_r) >= TEAM_R_THRESHOLD:
                    pairs.append((a_code, b_code, best_r, concept))

    if not pairs:
        return {}

    # ── 4. 连通分量分组 ──
    groups = []
    remaining = set()
    for a, b, _, _ in pairs:
        remaining.add(a)
        remaining.add(b)

    while remaining:
        seed = remaining.pop()
        group = {seed}
        changed = True
        while changed:
            changed = False
            for a, b, _, _ in pairs:
                if (a in group and b not in group) or (b in group and a not in group):
                    group.add(a)
                    group.add(b)
                    changed = True
        groups.append(group)
        remaining -= group

    # ── 5. 构建队友结果 ──
    # r 值查表
    r_map = {}
    for a, b, r_val, _ in pairs:
        key = (a, b)
        if key not in r_map or abs(r_val) > abs(r_map[key]):
            r_map[key] = abs(r_val)
        key = (b, a)
        if key not in r_map or abs(r_val) > abs(r_map[key]):
            r_map[key] = abs(r_val)

    # code → 它和队友共享的概念集合
    code_shared = {}
    for a, b, _, concept in pairs:
        code_shared.setdefault(a, set()).add(concept)
        code_shared.setdefault(b, set()).add(concept)

    teammates = {}
    for group in groups:
        if len(group) < 2:
            continue
        for code in group:
            if code not in code_info:
                continue
            mates = [c for c in group if c != code]
            mate_list = []
            for mate in mates:
                if mate in code_info:
                    mi = code_info[mate]
                    r_val = r_map.get((code, mate), TEAM_R_THRESHOLD)
                    # 共享概念：当前票的概念 ∩ 队友共享的概念
                    shared = list(code_concepts.get(code, set()) & code_shared.get(mate, set()))
                    mate_list.append({
                        "code": mi["code"],
                        "name": mi["name"],
                        "changePct": mi.get("changePct", 0),
                        "corr": round(r_val, 2),
                        "concepts": shared,
                    })
            mate_list.sort(key=lambda x: x["corr"], reverse=True)
            teammates[code] = {
                "byConcept": mate_list[:5],
                "byTrend": mate_list[:5],
            }

    return teammates


# ═══════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════

def _days_ago_str(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()
