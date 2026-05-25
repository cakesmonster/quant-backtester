"""日晷 FastAPI 入口 — SPA 前端 + REST API + 内部定时器"""
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

# 加入项目根目录，以便导入 quant_backtester
_PROJ = Path(__file__).resolve().parent.parent
if str(_PROJ) not in sys.path:
    sys.path.insert(0, str(_PROJ))

from .config import HOST, PORT
from .db import init_db, get_hot_rank, db_session

app = FastAPI(title="日晷 Sundial", version="0.5.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DASHBOARD = Path(__file__).parent / "dashboard"
STATIC = DASHBOARD / "static"


# ═══════════════════════════════════════════════════════════════
# 内部定时器：每小时采集热榜，不依赖 hermes cron
# ═══════════════════════════════════════════════════════════════

_scheduler_started = False


def _start_scheduler():
    """启动 APScheduler，每小时采集一次热榜"""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    from apscheduler.schedulers.background import BackgroundScheduler
    from datetime import datetime

    def collect():
        """采集热榜并写入 SQLite"""
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            from .data.ths_api import fetch_hot_rank
            items = loop.run_until_complete(fetch_hot_rank())
            hour = datetime.now().strftime("%H:%M")
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
            print(f"[scheduler] {hour} 热榜采集完成: {len(items)} 条", flush=True)
        except Exception as e:
            print(f"[scheduler] 热榜采集失败: {e}", flush=True)
        finally:
            loop.close()

    scheduler = BackgroundScheduler()
    scheduler.add_job(collect, "cron", minute=0, id="hot_rank_hourly")
    # 盘后同步账户（交易日 15:05）
    scheduler.add_job(_sync_account, "cron", hour=15, minute=5, day_of_week="mon-fri", id="account_sync_daily")
    scheduler.start()
    print("[scheduler] 热榜采集定时器已启动（每小时整点）+ 账户同步（工作日15:05）", flush=True)


def _sync_account():
    """盘后同步模拟账户到 SQLite"""
    try:
        from .data.ths_trade_api import sync_to_db
        sync_to_db()
        print("[scheduler] 账户同步完成", flush=True)
    except Exception as e:
        print(f"[scheduler] 账户同步失败: {e}", flush=True)


@app.on_event("startup")
async def startup():
    init_db()
    _start_scheduler()
    # 启动时同步一次模拟账户
    try:
        from .data.ths_trade_api import sync_to_db
        sync_to_db()
    except Exception as e:
        print(f"[startup] 账户同步失败: {e}", flush=True)


# ── 静态资源 ──

app.mount("/static/css", StaticFiles(directory=str(STATIC / "css")), name="css")
app.mount("/static/js", StaticFiles(directory=str(STATIC / "js")), name="js")
app.mount("/static/pages", StaticFiles(directory=str(STATIC / "pages")), name="pages")


# ── SPA 入口 ──

def _render_index() -> str:
    return (DASHBOARD / "index.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
async def index():
    return _render_index()


for route in ["/review", "/hotrank", "/stock", "/backtest", "/account"]:
    app.get(route, response_class=HTMLResponse)(lambda: _render_index())


# ── API 路由 ──

@app.get("/health")
async def health():
    return {"status": "ok", "name": "sundial", "scheduler": _scheduler_started}


@app.get("/api/dashboard")
async def api_dashboard(date: str = Query(None), code: str = Query(None)):
    from .services.dashboard import build_dashboard
    data = await build_dashboard(date, stock_code=code)
    return Response(content=json.dumps(data, ensure_ascii=False), media_type="application/json; charset=utf-8")


@app.get("/api/review")
async def api_review(date: str = Query(None)):
    from .services.sentiment import compute_sentiment
    from .services.ladder import compute_ladder, compute_yesterday_performance
    import asyncio
    d = date or _today_ymd()
    sentiment, ladder, yday_perf = await asyncio.gather(
        compute_sentiment(d), compute_ladder(d), compute_yesterday_performance(d),
    )
    return {"sentiment": sentiment, "ladder": ladder, "yesterday_performance": yday_perf}


@app.get("/api/hotrank")
async def api_hotrank(date: str = Query(None), slot: str = Query("15:00")):
    d = date or _today_iso()
    return {"date": d, "slot": slot, "items": get_hot_rank(d, slot)}


@app.get("/api/stock/{code}")
async def api_stock(code: str):
    """个股日K — 统一走通达信 mootdx（与回测引擎同源）"""
    from quant_backtester.data.cache import get_daily
    try:
        df = get_daily(code)
        if len(df) == 0:
            return {"code": code, "klines": [], "intraday": []}
        recent = df.tail(30)
        klines = []
        for idx, row in recent.iterrows():
            klines.append({
                "date": idx.strftime("%Y-%m-%d") if hasattr(idx, 'strftime') else str(idx)[:10],
                "open": float(row["open"]),
                "close": float(row["close"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "volume": int(row["volume"]),
            })
        # 分时图 — 通达信 mootdx 1分钟K线
        intraday = await _fetch_intraday(code)
        return {"code": code, "klines": klines, "intraday": intraday}
    except Exception as e:
        return {"code": code, "klines": [], "intraday": [], "error": str(e)}


async def _fetch_intraday(code: str) -> list:
    """通达信 mootdx 1分钟K线 → 分时图数据"""
    from mootdx.quotes import Quotes
    try:
        client = Quotes.factory(market="std")
        df = client.bars(symbol=code, frequency=7, start=0, offset=240)
    except Exception:
        return []
    if df is None or len(df) < 2:
        return []
    result = []
    for ts, row in df.iterrows():
        result.append({
            "time": ts.strftime("%Y-%m-%d %H:%M") if hasattr(ts, "strftime") else str(ts),
            "open": float(row.get("open", 0)),
            "close": float(row.get("close", 0)),
            "high": float(row.get("high", 0)),
            "low": float(row.get("low", 0)),
            "volume": int(float(row.get("vol", 0) or 0)),
        })
    return result


@app.post("/api/account/save")
async def api_account_save(
    date: str = Query(...), total_asset: float = Query(...),
    available_cash: float = Query(...), position_value: float = Query(...),
    daily_pnl: float = Query(0), holdings: str = Query("[]"),
):
    with db_session() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO account_snapshot (date, total_asset, available_cash, position_value, daily_pnl, holdings) VALUES (?,?,?,?,?,?)",
            (date, total_asset, available_cash, position_value, daily_pnl, holdings),
        )
    return {"status": "ok", "date": date}


@app.get("/api/account/sync")
async def api_account_sync():
    """手动触发账户同步（从同花顺模拟炒股API拉取最新数据）"""
    from .data.ths_trade_api import sync_to_db
    result = sync_to_db()
    return result

@app.get("/api/account")
async def api_account(date: str = Query(None)):
    d = date or _today_iso()
    with db_session() as conn:
        row = conn.execute(
            "SELECT total_asset, available_cash, position_value, daily_pnl, holdings FROM account_snapshot WHERE date=?",
            (d,),
        ).fetchone()
    if row:
        return {"date": d, "total_asset": row[0], "available_cash": row[1], "position_value": row[2], "daily_pnl": row[3], "holdings": json.loads(row[4]) if row[4] else []}
    return {"date": d, "total_asset": 0}


# ── 策略回测（进程内直接调用引擎） ──

@app.get("/api/backtest/strategies")
async def api_backtest_strategies():
    from quant_backtester.strategies.registry import discover_strategies
    strats = discover_strategies()
    return {
        "strategies": sorted(strats.keys()),
        "details": {
            name: {"name": name, "description": cls.description}
            for name, cls in strats.items()
        },
    }


@app.post("/api/backtest/run")
async def api_backtest_run(data: dict):
    from quant_backtester.strategies.registry import discover_strategies
    from quant_backtester.engine.backtest import run_one
    from quant_backtester.engine.metrics import compute_metrics
    from quant_backtester.data.stock_pool import random_sample

    strategy_name = data.get("strategy", "")
    stock_count = data.get("stock_count", 5)
    window_days = data.get("window_days", 180)
    runs_per_stock = data.get("runs_per_stock", 2)
    initial_capital = data.get("initial_capital", 100000)

    strats = discover_strategies()
    if strategy_name not in strats:
        return {"error": f"策略 '{strategy_name}' 不存在，可用: {sorted(strats.keys())}"}

    strategy_cls = strats[strategy_name]
    codes = random_sample(stock_count)

    t0 = time.time()
    results = []
    for idx, code in enumerate(codes):
        for run_idx in range(runs_per_stock):
            seed = run_idx * 1000 + idx
            r = run_one(
                code=code, strategy_cls=strategy_cls,
                window_days=window_days, initial_capital=initial_capital, seed=seed,
            )
            if r.get("success"):
                m = compute_metrics(r["equity_curve"], r["trades"], r["initial_capital"], r["window_days"])
                r["metrics"] = m
            results.append(r)

    elapsed = round(time.time() - t0, 1)

    success_results = [r for r in results if r.get("success")]
    if success_results:
        sharpes = [r.get("metrics", {}).get("sharpe_ratio", 0) for r in success_results]
        max_dds = [r.get("metrics", {}).get("max_drawdown_pct", 0) for r in success_results]
        win_rates = [r.get("metrics", {}).get("win_rate_pct", 0) for r in success_results]
        total_trades = sum(len(r.get("trades", [])) for r in success_results)
        avg_sharpe = round(sum(sharpes) / len(sharpes), 2) if sharpes else 0
        avg_max_dd = round(sum(max_dds) / len(max_dds), 2) if max_dds else 0
        avg_win_rate = round(sum(win_rates) / len(win_rates), 1) if win_rates else 0
    else:
        avg_sharpe = avg_max_dd = avg_win_rate = total_trades = 0

    curves = []
    for r in success_results:
        eq = r.get("equity_curve", [])
        if eq:
            curves.append({
                "label": r.get("code", ""),
                "data": [{"time": e["date"], "value": e["total_value"]} for e in eq],
            })

    details = []
    for r in success_results:
        m = r.get("metrics", {})
        details.append({
            "stock": r.get("code", ""),
            "window": f"{r.get('window_start','')}~{r.get('window_end','')}",
            "ret": r.get("total_return_pct", 0),
            "sharpe": m.get("sharpe_ratio", 0),
            "maxDd": m.get("max_drawdown_pct", 0),
            "winRate": m.get("win_rate_pct", 0),
            "trades": len(r.get("trades", [])),
        })

    return {
        "strategy": strategy_name,
        "elapsed_seconds": elapsed,
        "stock_count": stock_count,
        "total_runs": len(results),
        "success_runs": len(success_results),
        "curves": curves,
        "metrics": [
            {"label": "平均收益", "value": round(sum(r.get("total_return_pct", 0) for r in success_results) / len(success_results), 2) if success_results else 0, "suffix": "%", "hint": ""},
            {"label": "夏普比率", "value": avg_sharpe, "suffix": "", "hint": ""},
            {"label": "最大回撤", "value": avg_max_dd, "suffix": "%", "hint": ""},
            {"label": "胜率", "value": avg_win_rate, "suffix": "%", "hint": ""},
            {"label": "交易次数", "value": total_trades, "suffix": "", "hint": ""},
        ],
        "details": details,
    }


# ── helpers ──

def _today_ymd(): return date.today().strftime("%Y%m%d")
def _today_iso(): return date.today().isoformat()
def _days_ago(n: int): return (date.today() - timedelta(days=n)).isoformat()
def main(): uvicorn.run("sundial.main:app", host=HOST, port=PORT, reload=False)

if __name__ == "__main__":
    main()
