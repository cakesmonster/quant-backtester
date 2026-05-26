"""SQLite 数据层 — 2 张表"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import DB_PATH


def get_db() -> sqlite3.Connection:
    """获取 SQLite 连接（自动创建目录和表）"""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def db_session():
    """数据库会话上下文管理器"""
    conn = get_db()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """创建全部表（幂等）"""
    with db_session() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS hot_rank_snapshot (
                date TEXT, slot TEXT,
                rank INTEGER, code TEXT, name TEXT,
                heat_value REAL,
                concept_tag TEXT,
                is_limit_up INTEGER,
                change_pct REAL,
                PRIMARY KEY (date, slot, code)
            );

            CREATE TABLE IF NOT EXISTS account_snapshot (
                date TEXT PRIMARY KEY,
                total_asset REAL,
                available_cash REAL,
                position_value REAL,
                daily_pnl REAL,
                holdings TEXT
            );

            CREATE TABLE IF NOT EXISTS big_order_snapshot (
                date TEXT NOT NULL,
                code TEXT NOT NULL,
                time TEXT NOT NULL,
                price REAL,
                vol INTEGER,
                amount REAL,
                side TEXT,
                buyorsell INTEGER,
                PRIMARY KEY (date, code, time, vol, price)
            );
        """)


# ── 热榜操作 ──

def save_hot_rank(slot: str, items: list[dict]):
    """保存热榜快照。items: [{rank, code, name, heat_value, ...}]"""
    from datetime import date
    today = date.today().isoformat()
    with db_session() as conn:
        conn.execute("DELETE FROM hot_rank_snapshot WHERE date=? AND slot=?", (today, slot))
        for item in items:
            conn.execute(
                """INSERT OR REPLACE INTO hot_rank_snapshot
                   (date, slot, rank, code, name, heat_value, concept_tag, is_limit_up, change_pct)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (today, slot,
                 item.get("rank"), item.get("code"), item.get("name"),
                 item.get("heat_value"), item.get("concept_tag"),
                 1 if item.get("is_limit_up") else 0,
                 item.get("change_pct")),
            )


def get_hot_rank(target_date: str, slot: str) -> list[dict]:
    """查询某日某时段热榜"""
    with db_session() as conn:
        rows = conn.execute(
            "SELECT rank, code, name, heat_value, concept_tag, is_limit_up, change_pct "
            "FROM hot_rank_snapshot WHERE date=? AND slot=? ORDER BY rank",
            (target_date, slot),
        ).fetchall()
    return [dict(zip(["rank","code","name","heat_value","concept_tag","is_limit_up","change_pct"], r)) for r in rows]


# ── 大单异动 ──

def save_big_orders(code: str, orders: list[dict]):
    """保存大单到快照表。orders: [{time, price, vol, amount, side, buyorsell}]"""
    from datetime import date
    today = date.today().isoformat()
    with db_session() as conn:
        for o in orders:
            conn.execute(
                """INSERT OR IGNORE INTO big_order_snapshot
                   (date, code, time, price, vol, amount, side, buyorsell)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (today, code,
                 o["time"], o["price"], o["vol"], o["amount"],
                 o["side"], o.get("buyorsell")),
            )


def get_big_orders(target_date: str, code: str) -> list[dict]:
    """查询某日某股的大单，按时间正序"""
    with db_session() as conn:
        rows = conn.execute(
            "SELECT code, time, price, vol, amount, side FROM big_order_snapshot "
            "WHERE date=? AND code=? ORDER BY time",
            (target_date, code),
        ).fetchall()
    cols = ["code", "time", "price", "vol", "amount", "side"]
    return [dict(zip(cols, r)) for r in rows]
