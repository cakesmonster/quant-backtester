"""
单元测试 — SQLite 数据层: 建表、热榜 CRUD、账户快照。
"""
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_db(monkeypatch):
    """每个测试用独立临时 SQLite 文件"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)

    # 确保父目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Patch 两处：config 和 db 模块（db.py 在 import 时已绑定 DB_PATH）
    import sundial.config as cfg
    orig_cfg = cfg.DB_PATH
    monkeypatch.setattr(cfg, "DB_PATH", db_path)
    monkeypatch.setattr("sundial.db.DB_PATH", db_path, raising=False)

    yield str(db_path)

    monkeypatch.undo()
    try:
        os.unlink(path)
    except OSError:
        pass


class TestInitDB:
    """建表"""

    def test_creates_both_tables(self, temp_db):
        from sundial.db import init_db, get_db
        init_db()
        conn = get_db()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        conn.close()
        names = [r[0] for r in tables]
        assert "account_snapshot" in names
        assert "hot_rank_snapshot" in names

    def test_idempotent(self, temp_db):
        from sundial.db import init_db
        init_db()
        init_db()  # 第二次不报错
        init_db()  # 第三次也不报错


class TestHotRankCRUD:
    """热榜快照增删查"""

    def test_save_and_query(self, temp_db):
        from sundial.db import init_db, save_hot_rank, get_hot_rank
        from datetime import date
        init_db()
        today = date.today().isoformat()
        items = [
            {"rank": 1, "code": "000001", "name": "平安银行", "heat_value": 99.5,
             "concept_tag": "银行", "is_limit_up": False, "change_pct": 3.2},
            {"rank": 2, "code": "600519", "name": "贵州茅台", "heat_value": 95.0,
             "concept_tag": "白酒", "is_limit_up": True, "change_pct": 5.0},
        ]
        save_hot_rank("1130", items)

        results = get_hot_rank(today, "1130")
        assert len(results) == 2
        assert results[0]["code"] == "000001"
        assert results[0]["rank"] == 1
        assert results[1]["name"] == "贵州茅台"

    def test_overwrite_same_slot(self, temp_db):
        from sundial.db import init_db, save_hot_rank, get_hot_rank
        from datetime import date
        init_db()
        today = date.today().isoformat()

        save_hot_rank("1500", [{"rank": 1, "code": "000001", "name": "X",
            "heat_value": 50, "concept_tag": "", "is_limit_up": False, "change_pct": 1.0}])
        save_hot_rank("1500", [{"rank": 1, "code": "000002", "name": "Y",
            "heat_value": 60, "concept_tag": "", "is_limit_up": True, "change_pct": 2.0}])

        results = get_hot_rank(today, "1500")
        assert len(results) == 1
        assert results[0]["code"] == "000002"

    def test_empty_query(self, temp_db):
        from sundial.db import init_db, get_hot_rank
        init_db()
        results = get_hot_rank("2099-01-01", "1130")
        assert results == []

    def test_bool_to_int(self, temp_db):
        from sundial.db import init_db, save_hot_rank, get_hot_rank
        from datetime import date
        init_db()
        today = date.today().isoformat()
        save_hot_rank("2100", [
            {"rank": 1, "code": "000001", "name": "A", "heat_value": 80,
             "concept_tag": "AI", "is_limit_up": True, "change_pct": 10.0},
        ])
        results = get_hot_rank(today, "2100")
        assert results[0]["is_limit_up"] == 1

    def test_missing_optional_fields(self, temp_db):
        from sundial.db import init_db, save_hot_rank, get_hot_rank
        from datetime import date
        init_db()
        today = date.today().isoformat()
        save_hot_rank("1500", [{"rank": 1, "code": "000001", "name": "X",
            "heat_value": 50, "is_limit_up": False, "change_pct": 1.0}])
        results = get_hot_rank(today, "1500")
        assert len(results) == 1
        # concept_tag 未传，应为 None 或空字符串
        assert results[0]["concept_tag"] in (None, "")


class TestAccountSnapshot:
    """模拟账户快照"""

    def test_save_and_get(self, temp_db):
        from sundial.db import init_db, db_session
        init_db()
        with db_session() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO account_snapshot"
                " (date, total_asset, available_cash, position_value, daily_pnl, holdings)"
                " VALUES (?,?,?,?,?,?)",
                ("2026-05-24", 100000.0, 50000.0, 50000.0, 2000.0, '[]'),
            )

        with db_session() as conn:
            row = conn.execute(
                "SELECT total_asset, available_cash, position_value, daily_pnl, holdings"
                " FROM account_snapshot WHERE date=?",
                ("2026-05-24",),
            ).fetchone()

        assert row is not None
        assert row[0] == 100000.0
        assert row[1] == 50000.0
        assert row[3] == 2000.0

    def test_update_existing(self, temp_db):
        from sundial.db import init_db, db_session
        init_db()
        with db_session() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO account_snapshot"
                " (date, total_asset, available_cash, position_value, daily_pnl, holdings)"
                " VALUES (?,?,?,?,?,?)",
                ("2026-05-24", 100000.0, 0, 0, 0, '[]'),
            )
            conn.execute(
                "INSERT OR REPLACE INTO account_snapshot"
                " (date, total_asset, available_cash, position_value, daily_pnl, holdings)"
                " VALUES (?,?,?,?,?,?)",
                ("2026-05-24", 105000.0, 0, 0, 5000.0, '[]'),
            )

        with db_session() as conn:
            row = conn.execute(
                "SELECT total_asset, daily_pnl FROM account_snapshot WHERE date=?",
                ("2026-05-24",),
            ).fetchone()

        assert row[0] == 105000.0
        assert row[1] == 5000.0


class TestDbSession:
    """上下文管理器行为"""

    def test_commit_on_success(self, temp_db):
        from sundial.db import db_session
        with db_session() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS _test (id INTEGER PRIMARY KEY, val TEXT)")
            conn.execute("INSERT OR REPLACE INTO _test VALUES (1, 'hello')")

        with db_session() as conn:
            row = conn.execute("SELECT val FROM _test WHERE id=1").fetchone()
        assert row[0] == "hello"


class TestBigOrderSnapshot:
    """大单异动快照"""

    def test_creates_big_order_table(self, temp_db):
        from sundial.db import init_db, get_db
        init_db()
        conn = get_db()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        conn.close()
        names = [r[0] for r in tables]
        assert "big_order_snapshot" in names

    def test_save_and_query(self, temp_db):
        from sundial.db import init_db, save_big_orders, get_big_orders
        from datetime import date
        init_db()
        today = date.today().isoformat()
        orders = [
            {"time": "10:05:30", "price": 12.00, "vol": 1500, "amount": 18000000.0, "side": "卖出", "buyorsell": 1},
            {"time": "10:06:15", "price": 12.05, "vol": 2000, "amount": 24100000.0, "side": "买入", "buyorsell": 0},
        ]
        save_big_orders("600578", orders)

        results = get_big_orders(today, "600578")
        assert len(results) == 2
        assert results[0]["time"] == "10:05:30"
        assert results[0]["side"] == "卖出"
        assert results[0]["vol"] == 1500
        assert results[1]["price"] == 12.05

    def test_dedup_same_pk(self, temp_db):
        from sundial.db import init_db, save_big_orders, get_big_orders
        from datetime import date
        init_db()
        today = date.today().isoformat()
        orders = [
            {"time": "10:05:30", "price": 12.00, "vol": 1500, "amount": 18000000.0, "side": "卖出", "buyorsell": 1},
        ]
        save_big_orders("600578", orders)
        save_big_orders("600578", orders)  # 重复插入，应被忽略
        results = get_big_orders(today, "600578")
        assert len(results) == 1

    def test_empty_query(self, temp_db):
        from sundial.db import init_db, get_big_orders
        init_db()
        results = get_big_orders("2099-01-01", "600578")
        assert results == []

    def test_filter_by_code(self, temp_db):
        from sundial.db import init_db, save_big_orders, get_big_orders
        from datetime import date
        init_db()
        today = date.today().isoformat()
        save_big_orders("600578", [
            {"time": "10:05:30", "price": 12.00, "vol": 1500, "amount": 18000000.0, "side": "卖出", "buyorsell": 1},
        ])
        save_big_orders("000001", [
            {"time": "10:06:00", "price": 15.00, "vol": 1000, "amount": 15000000.0, "side": "买入", "buyorsell": 0},
        ])
        results_a = get_big_orders(today, "600578")
        results_b = get_big_orders(today, "000001")
        assert len(results_a) == 1
        assert len(results_b) == 1
        assert results_a[0]["code"] == "600578"
        assert results_b[0]["code"] == "000001"
