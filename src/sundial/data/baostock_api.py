"""Baostock + AkShare 混合指数 — 支持 date 查历史"""

import asyncio
from datetime import date, timedelta
from typing import Optional

import baostock as bs
import pandas as pd

# 四大指数：前三个 Baostock，科创50 走 AkShare（Baostock 不支持 000688）
INDICES = {
    "sh": "sh.000001",    # 上证指数
    "sz": "sz.399001",    # 深证成指
    "cyb": "sz.399006",   # 创业板指
}
KCB_CODE = "sh000688"     # 科创50 → AkShare

# 个股日K字段
STOCK_FIELDS = "date,code,open,high,low,close,volume,amount,turn,pctChg"


def _ensure_login():
    if not hasattr(_ensure_login, "_logged"):
        bs.login()
        _ensure_login._logged = True


def _to_iso(d: Optional[str]) -> str:
    if d is None:
        return date.today().isoformat()
    return d if len(d) == 10 else f"{d[:4]}-{d[4:6]}-{d[6:8]}"


async def _run_sync(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def _query_baostock_index(code: str, target: str) -> dict | None:
    """查单个指数 Baostock 数据"""
    _ensure_login()
    prev = (date.fromisoformat(target) - timedelta(days=7)).isoformat()
    rs = bs.query_history_k_data_plus(code, "date,close,amount",
        start_date=prev, end_date=target)
    rows = []
    while (rs.error_code == '0') & rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return None
    today = rows[-1]
    close = float(today[1])
    amount = float(today[2]) if today[2] else 0
    change_pct = 0.0
    if len(rows) >= 2:
        prev_close = float(rows[-2][1])
        if prev_close > 0:
            change_pct = round((close - prev_close) / prev_close * 100, 2)
    return {"close": close, "change_pct": change_pct, "amount": round(amount / 1e8, 2)}


def _query_kcb(target_iso: str) -> dict | None:
    """AkShare 查科创50"""
    import akshare as ak
    from datetime import datetime
    target_dt = datetime.strptime(target_iso, "%Y-%m-%d").date()
    df = ak.stock_zh_index_daily(symbol=KCB_CODE)
    df["date_dt"] = pd.to_datetime(df["date"]).dt.date
    df = df[df["date_dt"] <= target_dt]
    if df.empty:
        return None
    today = df.iloc[-1]
    close = float(today["close"])
    change_pct = 0.0
    if len(df) >= 2:
        prev_close = float(df.iloc[-2]["close"])
        if prev_close > 0:
            change_pct = round((close - prev_close) / prev_close * 100, 2)
    return {"close": close, "change_pct": change_pct, "amount": 0}  # 新浪源无成交额


async def fetch_index(target_date: Optional[str] = None) -> dict:
    """获取四大指数行情

    Returns: {sh/sz/cyb/kcb: {close, change_pct, amount}}
    """
    d = _to_iso(target_date)
    result = {}

    # Baostock 查三大指数
    def _query_all():
        return {k: _query_baostock_index(v, d) or {"close":0,"change_pct":0,"amount":0}
                for k, v in INDICES.items()}

    baostock_data = await _run_sync(_query_all)
    result.update(baostock_data)

    # AkShare 补科创50
    result["kcb"] = await _run_sync(_query_kcb, d) or {"close": 0, "change_pct": 0, "amount": 0}

    return result


async def fetch_stock_kline(code: str, start_date: str, end_date: Optional[str] = None) -> list[dict]:
    """获取个股日K线

    code: 'sh.600519' 或 'sz.000001' 或纯数字自动补前缀
    """
    if not code.startswith(("sh.", "sz.", "bj.")):
        if code.startswith(("6", "5")):
            code = f"sh.{code}"
        else:
            code = f"sz.{code}"

    end = _to_iso(end_date)
    start = _to_iso(start_date)

    def _query():
        _ensure_login()
        rs = bs.query_history_k_data_plus(code, STOCK_FIELDS,
            start_date=start, end_date=end)
        rows = []
        while (rs.error_code == '0') & rs.next():
            vals = rs.get_row_data()
            rows.append({
                "date": vals[0], "code": vals[1],
                "open": float(vals[2]), "high": float(vals[3]),
                "low": float(vals[4]), "close": float(vals[5]),
                "volume": int(vals[6]), "amount": float(vals[7]),
                "turnover": float(vals[8]) if vals[8] else 0,
                "change_pct": float(vals[9]) if vals[9] else 0,
            })
        return rows

    return await _run_sync(_query)
