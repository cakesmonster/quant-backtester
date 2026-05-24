"""
单元测试 — 情绪仪表盘: 温度计计算、阶段判断、各权重因子。
所有测试 mock 外部 API，纯逻辑验证。
"""
import pytest
from unittest.mock import AsyncMock, patch

from tests.sundial.conftest import (
    make_limit_up_item, make_limit_down_item, make_broken_item, make_index_data,
)


def _mock_fetch_all_limit_data(up_items, broken_items, down_items, yesterday_items):
    """构造 fetch_all_limit_data 返回值"""
    return {
        "limit_up": up_items,
        "strong": [],
        "broken": broken_items,
        "limit_down": down_items,
        "yesterday": yesterday_items,
    }


@pytest.mark.asyncio
class TestSentimentComputation:
    """情绪温度计核心逻辑"""

    async def test_normal_market(self):
        """正常市场：50家涨停 + 5家炸板 + 3家跌停，晋级率 50%"""
        up = [make_limit_up_item(code=f"0000{i:02d}", board_count=1) for i in range(15, 65)]
        broken = [make_broken_item(code=f"0000{i:02d}") for i in range(5)]
        down = [make_limit_down_item(code=f"6000{i:02d}") for i in range(3)]
        # 昨天30家(码000000~000029)，今天50家(码000015~000064)，重叠15家 → 晋级率50%
        yesterday = [make_limit_up_item(code=f"0000{i:02d}") for i in range(30)]
        limit_data = _mock_fetch_all_limit_data(up, broken, down, yesterday)
        index_data = make_index_data(sh_pct=0.5)

        with patch("sundial.services.sentiment.fetch_all_limit_data", AsyncMock(return_value=limit_data)),              patch("sundial.services.sentiment.fetch_index", AsyncMock(return_value=index_data)):
            from sundial.services.sentiment import compute_sentiment
            result = await compute_sentiment("20260522")

        assert result["limit"]["up_count"] == 50
        assert result["limit"]["down_count"] == 3
        assert result["limit"]["broken_count"] == 5
        assert result["limit"]["broken_rate"] == 10.0  # 5/50
        # 昨天30家(码000000~000029)，今天涨停池码000000~000049，前15家重叠
        assert result["promotion_rate"] == 50.0  # 15/30
        assert 40 <= result["sentiment_temp"] <= 75
        assert result["sentiment_stage"] in ("偏冷", "正常", "偏热")

    async def test_ice_point_market(self):
        """冰点市场：极少涨停 + 大面积跌停"""
        up = [make_limit_up_item(code="000001")] * 3
        down = [make_limit_down_item(code=f"6000{i:02d}") for i in range(300)]
        broken = [make_broken_item(code="000002")] * 10
        yesterday = [make_limit_up_item(code="000001")] * 10
        limit_data = _mock_fetch_all_limit_data(up, broken, down, yesterday)
        index_data = make_index_data(sh_pct=-3.0, sh_amount=3000, sz_amount=4000)

        with patch("sundial.services.sentiment.fetch_all_limit_data", AsyncMock(return_value=limit_data)),              patch("sundial.services.sentiment.fetch_index", AsyncMock(return_value=index_data)):
            from sundial.services.sentiment import compute_sentiment
            result = await compute_sentiment("20260522")

        assert result["limit"]["up_count"] == 3
        assert result["limit"]["down_count"] == 300
        assert result["sentiment_temp"] <= 30
        assert result["sentiment_stage"] == "冰点"

    async def test_overheated_market(self):
        """过热市场：百股涨停 + 高晋级率 + 指数大涨"""
        # 昨天80家(码 000000~000079)，今天120家(码 000000~000119)，前80重叠 → 晋级率 100%
        up = [make_limit_up_item(code=f"0000{i:02d}") for i in range(120)]
        down = [make_limit_down_item(code=f"6000{i:02d}") for i in range(2)]
        broken = [make_broken_item(code=f"0000{i:02d}") for i in range(3)]
        yesterday = [make_limit_up_item(code=f"0000{i:02d}") for i in range(80)]
        limit_data = _mock_fetch_all_limit_data(up, broken, down, yesterday)
        index_data = make_index_data(sh_pct=2.5, sh_amount=8000, sz_amount=10000)

        with patch("sundial.services.sentiment.fetch_all_limit_data", AsyncMock(return_value=limit_data)),              patch("sundial.services.sentiment.fetch_index", AsyncMock(return_value=index_data)):
            from sundial.services.sentiment import compute_sentiment
            result = await compute_sentiment("20260522")

        assert result["limit"]["up_count"] == 120
        assert result["promotion_rate"] > 50
        assert result["sentiment_temp"] > 70
        assert result["sentiment_stage"] in ("偏热", "过热")

    async def test_empty_pools(self):
        """全部空池（比如非交易日）— 没有涨停时炸板率满分20分 + 指数底分7.5"""
        limit_data = _mock_fetch_all_limit_data([], [], [], [])
        index_data = make_index_data(sh_close=0, sh_pct=0, sh_amount=0, sz_amount=0)

        with patch("sundial.services.sentiment.fetch_all_limit_data", AsyncMock(return_value=limit_data)),              patch("sundial.services.sentiment.fetch_index", AsyncMock(return_value=index_data)):
            from sundial.services.sentiment import compute_sentiment
            result = await compute_sentiment("20260522")

        assert result["limit"]["up_count"] == 0
        assert result["limit"]["broken_rate"] == 0
        assert result["promotion_rate"] == 0
        # 空池不代表0度：炸板率0（无炸板→满分20）+ 指数中性（7.5）= 27.5 → 28
        assert result["sentiment_temp"] == 28


@pytest.mark.asyncio
class TestSentimentStages:
    """阶段判断边界"""

    async def test_ice_point_stage(self):
        """冰点：无涨停 + 指数大跌"""
        from sundial.services.sentiment import compute_sentiment
        limit_data = _mock_fetch_all_limit_data([], [], [], [])
        index_data = make_index_data(sh_pct=-5.0, sh_amount=2000, sz_amount=2000)
        with patch("sundial.services.sentiment.fetch_all_limit_data", AsyncMock(return_value=limit_data)),              patch("sundial.services.sentiment.fetch_index", AsyncMock(return_value=index_data)):
            r = await compute_sentiment("20260522")
            assert r["sentiment_stage"] == "冰点"
            assert r["sentiment_temp"] <= 30

    async def test_cold_stage(self):
        """偏冷：极少涨停 + 无晋级 + 指数小跌"""
        from sundial.services.sentiment import compute_sentiment
        up = [make_limit_up_item(code=f"0000{i:02d}") for i in range(5)]
        # yesterday 用不同码段，无重叠 → 晋级率 0%
        yesterday = [make_limit_up_item(code=f"0000{i:02d}") for i in range(10, 20)]
        limit_data = _mock_fetch_all_limit_data(up, [], [], yesterday)
        index_data = make_index_data(sh_pct=-0.5, sh_amount=3000, sz_amount=4000)
        with patch("sundial.services.sentiment.fetch_all_limit_data", AsyncMock(return_value=limit_data)),              patch("sundial.services.sentiment.fetch_index", AsyncMock(return_value=index_data)):
            r = await compute_sentiment("20260522")
            assert r["sentiment_stage"] == "偏冷"

    async def test_overheat_stage(self):
        """过热：200家涨停 + 指数暴涨"""
        from sundial.services.sentiment import compute_sentiment
        up = [make_limit_up_item(code=f"0000{i:02d}") for i in range(200)]
        yesterday = [make_limit_up_item(code=f"0000{i:02d}") for i in range(150)]
        limit_data = _mock_fetch_all_limit_data(up, [], [], yesterday)
        index_data = make_index_data(sh_pct=4.0, sh_amount=10000, sz_amount=15000)
        with patch("sundial.services.sentiment.fetch_all_limit_data", AsyncMock(return_value=limit_data)),              patch("sundial.services.sentiment.fetch_index", AsyncMock(return_value=index_data)):
            r = await compute_sentiment("20260522")
            assert r["sentiment_stage"] == "过热"
            assert r["sentiment_temp"] >= 85


@pytest.mark.asyncio
class TestSentimentAmount:
    """成交额指标"""

    async def test_amount_sum(self):
        """成交额 total = 上证+深证之和"""
        limit_data = _mock_fetch_all_limit_data([], [], [], [])
        index_data = make_index_data(sh_amount=3500, sz_amount=5200)

        with patch("sundial.services.sentiment.fetch_all_limit_data", AsyncMock(return_value=limit_data)),              patch("sundial.services.sentiment.fetch_index", AsyncMock(return_value=index_data)):
            from sundial.services.sentiment import compute_sentiment
            result = await compute_sentiment("20260522")

        assert result["amount"]["total"] == 8700
        assert result["amount"]["sh"] == 3500
        assert result["amount"]["sz"] == 5200
