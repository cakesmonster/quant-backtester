"""
单元测试 — FastAPI 端点: 页面路由、API 路由（mock 外部服务）。
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def mock_init_db():
    """所有 API 测试跳过 init_db"""
    with patch("sundial.main.init_db", MagicMock()):
        yield


@pytest.fixture
def client():
    from sundial.main import app
    return TestClient(app)


class TestHealth:
    """健康检查"""

    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["name"] == "sundial"


class TestPageRoutes:
    """页面路由返回 HTML"""

    def test_index(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_review(self, client):
        r = client.get("/review")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_hotrank(self, client):
        r = client.get("/hotrank")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_stock(self, client):
        r = client.get("/stock")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_backtest(self, client):
        r = client.get("/backtest")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_account(self, client):
        r = client.get("/account")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]


class TestAPIRoutes:
    """API 路由"""

    def test_api_review_mocked(self, client):
        """mock sentiment 和 ladder 服务 — 注意它们在 api_review 内 import，需 patch 源模块"""
        mock_sentiment = {
            "sentiment_temp": 50, "sentiment_stage": "正常",
            "limit": {"up_count": 30, "down_count": 5, "broken_count": 3, "broken_rate": 10.0},
            "promotion_rate": 40.0,
            "indices": {}, "amount": {"total": 8000, "sh": 3000, "sz": 5000},
        }
        mock_ladder = {"total_limit_up": 30, "ladder": {}}
        mock_yday = {"count": 20, "continued": 10, "rate": 50.0}

        with patch("sundial.services.sentiment.compute_sentiment", AsyncMock(return_value=mock_sentiment)),              patch("sundial.services.ladder.compute_ladder", AsyncMock(return_value=mock_ladder)),              patch("sundial.services.ladder.compute_yesterday_performance", AsyncMock(return_value=mock_yday)):
            r = client.get("/api/review", params={"date": "20260522"})
            assert r.status_code == 200
            data = r.json()
            assert data["sentiment"]["sentiment_stage"] == "正常"
            assert data["ladder"]["total_limit_up"] == 30
            assert data["yesterday_performance"]["rate"] == 50.0

    def test_api_hotrank_empty(self, client):
        """热榜无数据"""
        with patch("sundial.main.get_hot_rank", MagicMock(return_value=[])):
            r = client.get("/api/hotrank", params={"date": "2026-05-24", "slot": "1500"})
            assert r.status_code == 200
            data = r.json()
            assert data["items"] == []

    def test_api_hotrank_with_data(self, client):
        """热榜有数据"""
        items = [
            {"rank": 1, "code": "000001", "name": "平安银行", "heat_value": 99.0,
             "concept_tag": "银行", "is_limit_up": 0, "change_pct": 3.0},
        ]
        with patch("sundial.main.get_hot_rank", MagicMock(return_value=items)):
            r = client.get("/api/hotrank", params={"slot": "1130"})
            assert r.status_code == 200
            data = r.json()
            assert len(data["items"]) == 1
            assert data["items"][0]["name"] == "平安银行"

    def test_api_account_save_and_get(self, client):
        """账户保存与查询"""
        from sundial.db import init_db
        init_db()

        r = client.post("/api/account/save", params={
            "date": "2026-05-24",
            "total_asset": 100000,
            "available_cash": 50000,
            "position_value": 50000,
            "daily_pnl": 2000,
            "holdings": '[{"code":"000001","name":"平安银行","shares":1000}]',
        })
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

        r = client.get("/api/account", params={"date": "2026-05-24"})
        assert r.status_code == 200
        data = r.json()
        assert data["total_asset"] == 100000
        assert data["available_cash"] == 50000
        assert data["daily_pnl"] == 2000
        assert len(data["holdings"]) == 1
        assert data["holdings"][0]["code"] == "000001"

    def test_api_account_not_found(self, client):
        """查询不存在的日期"""
        r = client.get("/api/account", params={"date": "2099-01-01"})
        assert r.status_code == 200
        data = r.json()
        assert data["total_asset"] == 0


class TestStockTeammates:
    """非热榜票动态计算队友"""

    def test_api_stock_includes_teammates(self, client):
        """api/stock/{code} 返回 teammates 字段"""
        with patch("sundial.main._fetch_intraday", AsyncMock(return_value=[])), \
             patch("sundial.main._fetch_teammates_for_stock", AsyncMock(return_value=[])), \
             patch("sundial.main._fetch_big_orders", AsyncMock(return_value=[])), \
             patch("quant_backtester.data.cache.get_daily", MagicMock(return_value=__import__("pandas").DataFrame({"open":[1400],"close":[1405],"high":[1410],"low":[1395],"volume":[10000]}, index=[__import__("pandas").Timestamp("2026-05-26")]))):
            r = client.get("/api/stock/600519")
            assert r.status_code == 200
            data = r.json()
            assert "teammates" in data
            assert isinstance(data["teammates"], list)

    def test_api_stock_includes_big_orders(self, client):
        """api/stock/{code} 返回 bigOrders 字段"""
        mock_big = [
            {"time": "10:05:30", "side": "卖出", "volume": 1500, "amount": "1800万", "price": 12.00},
            {"time": "10:06:15", "side": "买入", "volume": 2000, "amount": "2400万", "price": 12.05},
        ]
        with patch("sundial.main._fetch_intraday", AsyncMock(return_value=[])), \
             patch("sundial.main._fetch_teammates_for_stock", AsyncMock(return_value=[])), \
             patch("sundial.main._fetch_big_orders", AsyncMock(return_value=mock_big)), \
             patch("quant_backtester.data.cache.get_daily", MagicMock(return_value=__import__("pandas").DataFrame({"open":[1400],"close":[1405],"high":[1410],"low":[1395],"volume":[10000]}, index=[__import__("pandas").Timestamp("2026-05-26")]))):
            r = client.get("/api/stock/600519")
            assert r.status_code == 200
            data = r.json()
            assert "bigOrders" in data
            assert isinstance(data["bigOrders"], list)
            assert len(data["bigOrders"]) == 2
            assert data["bigOrders"][0]["side"] == "卖出"
            assert data["bigOrders"][0]["amount"] == "1800万"
            assert data["bigOrders"][1]["side"] == "买入"


class TestBigOrderCollection:
    """大单采集（mootdx 逐笔 → SQLite）"""

    def test_filters_by_amount_threshold(self):
        """仅大于等于1000万的成交被保存"""
        import pandas as pd
        from unittest.mock import MagicMock, patch

        # 两条：一条达标（10000手×10×100=1000万），一条不达标
        mock_txn = pd.DataFrame({
            "time": ["100530", "100615"],
            "price": [10.00, 10.00],
            "vol": [10000, 500],
            "buyorsell": [1, 0],
            "num": [1, 2],
        })

        mock_client = MagicMock()
        mock_client.transaction.return_value = mock_txn

        with patch("mootdx.quotes.Quotes.factory", return_value=mock_client), \
             patch("sundial.db.save_big_orders") as mock_save:
            from sundial.main import _collect_big_orders_from_pool
            _collect_big_orders_from_pool({"600578": {}})

            assert mock_save.call_count == 1
            code, orders = mock_save.call_args[0]
            assert code == "600578"
            assert len(orders) == 1
            assert orders[0]["vol"] == 10000
            assert orders[0]["side"] == "卖出"

