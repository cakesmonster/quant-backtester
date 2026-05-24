"""日晷 FastAPI 入口"""

from pathlib import Path

import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .config import HOST, PORT
from .db import init_db, get_hot_rank

app = FastAPI(title="日晷 Sundial", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

TEMPLATE_DIR = Path(__file__).parent / "dashboard" / "templates"


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/health")
async def health():
    return {"status": "ok", "name": "sundial"}


# ── 页面路由 ──

@app.get("/", response_class=HTMLResponse)
async def index():
    return (TEMPLATE_DIR / "review.html").read_text(encoding="utf-8")


@app.get("/review", response_class=HTMLResponse)
async def review_page():
    return (TEMPLATE_DIR / "review.html").read_text(encoding="utf-8")


@app.get("/hotrank", response_class=HTMLResponse)
async def hotrank_page():
    return (TEMPLATE_DIR / "hotrank.html").read_text(encoding="utf-8")


@app.get("/stock", response_class=HTMLResponse)
async def stock_page():
    return (TEMPLATE_DIR / "stock.html").read_text(encoding="utf-8")


@app.get("/backtest", response_class=HTMLResponse)
async def backtest_page():
    return (TEMPLATE_DIR / "backtest.html").read_text(encoding="utf-8")


@app.get("/account", response_class=HTMLResponse)
async def account_page():
    return (TEMPLATE_DIR / "account.html").read_text(encoding="utf-8")


# ── API 路由 ──

@app.get("/api/review")
async def api_review(date: str = Query(None)):
    from .services.sentiment import compute_sentiment
    from .services.ladder import compute_ladder, compute_yesterday_performance
    import asyncio

    d = date or _today_ymd()
    sentiment, ladder, yday_perf = await asyncio.gather(
        compute_sentiment(d),
        compute_ladder(d),
        compute_yesterday_performance(d),
    )
    return {
        "sentiment": sentiment,
        "ladder": ladder,
        "yesterday_performance": yday_perf,
    }


@app.get("/api/hotrank")
async def api_hotrank(date: str = Query(None), slot: str = Query("1500")):
    d = date or _today_iso()
    return {"date": d, "slot": slot, "items": get_hot_rank(d, slot)}


@app.get("/api/stock/{code}")
async def api_stock(code: str):
    from .data.baostock_api import fetch_stock_kline
    klines = await fetch_stock_kline(code, _days_ago(30))
    return {"code": code, "klines": klines[-30:]}


@app.post("/api/account/save")
async def api_account_save(
    date: str = Query(...), total_asset: float = Query(...),
    available_cash: float = Query(...), position_value: float = Query(...),
    daily_pnl: float = Query(0), holdings: str = Query("[]"),
):
    from .db import db_session
    with db_session() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO account_snapshot"
            " (date, total_asset, available_cash, position_value, daily_pnl, holdings)"
            " VALUES (?,?,?,?,?,?)",
            (date, total_asset, available_cash, position_value, daily_pnl, holdings),
        )
    return {"status": "ok", "date": date}


@app.get("/api/account")
async def api_account(date: str = Query(None)):
    from .db import db_session
    d = date or _today_iso()
    with db_session() as conn:
        row = conn.execute(
            "SELECT total_asset, available_cash, position_value, daily_pnl, holdings"
            " FROM account_snapshot WHERE date=?",
            (d,),
        ).fetchone()
    if row:
        import json
        return {
            "date": d, "total_asset": row[0], "available_cash": row[1],
            "position_value": row[2], "daily_pnl": row[3],
            "holdings": json.loads(row[4]) if row[4] else [],
        }
    return {"date": d, "total_asset": 0}


# ── helpers ──

def _today_ymd():
    from datetime import date
    return date.today().strftime("%Y%m%d")


def _today_iso():
    from datetime import date
    return date.today().isoformat()


def _days_ago(n: int):
    from datetime import date, timedelta
    return (date.today() - timedelta(days=n)).isoformat()


def main():
    uvicorn.run("sundial.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
