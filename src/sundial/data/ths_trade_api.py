"""
同花顺模拟炒股 API — 账户查询 + 持仓。
裸调用 http://trade.10jqka.com.cn:8088，不依赖 board_monitor。
"""

import json
import urllib.request
from datetime import date

API_BASE = "http://trade.10jqka.com.cn:8088"
USRID = "116365878"
DEPARTMENT_ID = "997376"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _api_get(endpoint: str, params: dict) -> dict:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{API_BASE}{endpoint}?{query}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def fetch_account() -> dict:
    """获取账户总览（总资产/可用资金/盈亏）

    Returns:
        {
            total_asset: float,      # 总资产
            available_cash: float,   # 可用资金
            position_value: float,   # 持仓市值
            daily_pnl: float,        # 当日盈亏（元）
            daily_return_pct: float, # 当日收益率
            total_pnl: float,        # 总盈亏
            initial_capital: float,  # 初始资金
            last_trade_date: str,    # 最后交易日
        }
    """
    r = _api_get("/pt_qry_gainstat", {"usrid": USRID})
    d = r.get("data", {})
    if not d:
        return {}

    zzc = float(d.get("zzc", 0))        # 总资产
    zjye = float(d.get("zjye", 0))      # 资金余额
    zsz = float(d.get("zsz", 0))        # 持仓市值

    # 当日盈亏：从总资产变动推算（如果跨天，用 syl0 估算）
    syl0 = float(d.get("syl0", 0))
    fare = float(d.get("fare", 0))
    daily_pnl = round(syl0 * fare, 2)   # 日收益率 × 初始资金

    return {
        "total_asset": zzc,
        "available_cash": zjye,
        "position_value": zsz,
        "daily_pnl": daily_pnl,
        "daily_return_pct": round(syl0 * 100, 4),
        "total_pnl": float(d.get("zyk", 0)),
        "initial_capital": fare,
        "last_trade_date": d.get("jyrq", ""),
    }


def fetch_positions() -> list[dict]:
    """获取持仓明细

    Returns:
        [{code, name, shares, cost, price, pnl, pnl_pct}]
    """
    r = _api_get("/pt_web_qry_stock", {
        "name": USRID, "yybid": DEPARTMENT_ID, "type": "1", "datatype": "json",
    })
    positions = r.get("data", []) or r.get("result", []) or r.get("list", [])
    result = []
    for p in positions:
        code = p.get("zqdm", "")
        if not code:
            continue
        try:
            shares = int(float(p.get("gpsl", 0)))
            cost = float(p.get("gpcb", 0))
            price = float(p.get("xj", 0))
            pnl = float(p.get("fdyk", 0))
            pnl_pct_str = str(p.get("ykl", "0%")).replace("%", "")
            pnl_pct = float(pnl_pct_str)
        except (ValueError, TypeError):
            continue
        if shares <= 0:
            continue
        result.append({
            "code": code,
            "name": p.get("zqmc", code),
            "shares": shares,
            "cost": cost,
            "price": price,
            "pnl": pnl,
            "pnlPct": pnl_pct,
        })
    return result


def sync_to_db():
    """同步账户数据到 sundial SQLite。合并 THS API + monitor state。"""
    import sys, os
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
    from sundial.db import db_session, init_db

    init_db()
    acct = fetch_account()
    ths_positions = fetch_positions()
    today = date.today().isoformat()

    # 合并 monitor state 中的当日买入（THS 可能未结算）
    state_path = os.path.expanduser(f"~/.hermes/data/trading/logs/{today.replace('-', '')}/state.json")
    monitor_held = {}
    try:
        with open(state_path) as f:
            state = json.load(f)
        monitor_held = state.get("holdings", {})
    except Exception:
        pass

    # 合并：THS 持仓优先，monitor 补当日新买入
    positions = {p["code"]: p for p in ths_positions}
    for code, h in monitor_held.items():
        if code not in positions:
            positions[code] = {
                "code": code, "name": code, "shares": h.get("shares", 0),
                "cost": h.get("cost", 0), "price": h.get("cost", 0),
                "pnl": 0, "pnlPct": 0,
            }

    pos_value = sum(p["price"] * p["shares"] for p in positions.values())
    pos_list = list(positions.values())

    with db_session() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO account_snapshot (date, total_asset, available_cash, position_value, daily_pnl, holdings) VALUES (?,?,?,?,?,?)",
            (today,
             acct.get("total_asset", 0),
             acct.get("available_cash", 0),
             pos_value,
             acct.get("daily_pnl", 0),
             json.dumps(pos_list, ensure_ascii=False)),
        )
    return {"status": "ok", "account": acct, "positions": pos_list}
