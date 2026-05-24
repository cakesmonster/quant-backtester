"""
单元测试 — 连板天梯: 分组、排序、昨日涨停表现。
"""
import pytest
from unittest.mock import AsyncMock, patch

from tests.sundial.conftest import make_limit_up_item


@pytest.mark.asyncio
class TestLadderComputation:
    """连板天梯核心逻辑"""

    async def test_groups_by_board_count(self):
        """按连板数分组"""
        pool = [
            make_limit_up_item(code="000001", name="龙头", board_count=5, change_pct=10.0),
            make_limit_up_item(code="000002", name="二板A", board_count=2, change_pct=9.8),
            make_limit_up_item(code="000003", name="二板B", board_count=2, change_pct=10.0),
            make_limit_up_item(code="000004", name="三板A", board_count=3, change_pct=8.5),
            make_limit_up_item(code="000005", name="一板A", board_count=1),
        ]

        with patch("sundial.services.ladder.fetch_limit_up_pool", AsyncMock(return_value=pool)):
            from sundial.services.ladder import compute_ladder
            result = await compute_ladder("20260522")

        ladder = result["ladder"]
        assert "5" in ladder
        assert "3" in ladder
        assert "2" in ladder
        assert "1" not in ladder

        assert len(ladder["5"]) == 1
        assert ladder["5"][0]["name"] == "龙头"
        assert len(ladder["2"]) == 2

    async def test_sorted_desc_by_board_count(self):
        """天梯从高板到低板排序"""
        pool = [
            make_limit_up_item(code="000001", board_count=2),
            make_limit_up_item(code="000002", board_count=4),
            make_limit_up_item(code="000003", board_count=3),
        ]

        with patch("sundial.services.ladder.fetch_limit_up_pool", AsyncMock(return_value=pool)):
            from sundial.services.ladder import compute_ladder
            result = await compute_ladder("20260522")

        keys = list(result["ladder"].keys())
        assert keys == ["4", "3", "2"]

    async def test_within_group_sorted_by_change_pct(self):
        """组内按涨幅降序"""
        pool = [
            make_limit_up_item(code="000001", board_count=2, change_pct=5.0),
            make_limit_up_item(code="000002", board_count=2, change_pct=10.0),
            make_limit_up_item(code="000003", board_count=2, change_pct=3.0),
        ]

        with patch("sundial.services.ladder.fetch_limit_up_pool", AsyncMock(return_value=pool)):
            from sundial.services.ladder import compute_ladder
            result = await compute_ladder("20260522")

        group = result["ladder"]["2"]
        assert group[0]["change_pct"] == 10.0
        assert group[1]["change_pct"] == 5.0
        assert group[2]["change_pct"] == 3.0

    async def test_empty_pool(self):
        """空涨停池"""
        with patch("sundial.services.ladder.fetch_limit_up_pool", AsyncMock(return_value=[])):
            from sundial.services.ladder import compute_ladder
            result = await compute_ladder("20260522")

        assert result["total_limit_up"] == 0
        assert result["ladder"] == {}

    async def test_no_multi_board(self):
        """全是首板，天梯为空"""
        pool = [make_limit_up_item(code=f"0000{i:02d}", board_count=1) for i in range(10)]

        with patch("sundial.services.ladder.fetch_limit_up_pool", AsyncMock(return_value=pool)):
            from sundial.services.ladder import compute_ladder
            result = await compute_ladder("20260522")

        assert result["total_limit_up"] == 10
        assert result["ladder"] == {}

    async def test_missing_board_count_defaults_to_1(self):
        """board_count 缺失视为首板"""
        item = make_limit_up_item(code="000001")
        del item["board_count"]

        with patch("sundial.services.ladder.fetch_limit_up_pool", AsyncMock(return_value=[item])):
            from sundial.services.ladder import compute_ladder
            result = await compute_ladder("20260522")

        assert result["total_limit_up"] == 1
        assert result["ladder"] == {}


@pytest.mark.asyncio
class TestYesterdayPerformance:
    """昨日涨停今日表现 — compute_yesterday_performance 在函数内 import，需 patch 源模块"""

    async def test_half_continued(self):
        """昨天4家涨停，今天2家继续"""
        yesterday = [
            make_limit_up_item(code="000001"),
            make_limit_up_item(code="000002"),
            make_limit_up_item(code="000003"),
            make_limit_up_item(code="000004"),
        ]
        today = [
            make_limit_up_item(code="000001"),
            make_limit_up_item(code="000002"),
        ]

        with patch("sundial.data.eastmoney_api.fetch_yesterday_pool", AsyncMock(return_value=yesterday)),              patch("sundial.data.eastmoney_api.fetch_limit_up_pool", AsyncMock(return_value=today)):
            from sundial.services.ladder import compute_yesterday_performance
            result = await compute_yesterday_performance("20260522")

        assert result["count"] == 4
        assert result["continued"] == 2
        assert result["rate"] == 50.0

    async def test_none_continued(self):
        """昨天涨停全部断板"""
        yesterday = [make_limit_up_item(code=f"0000{i:02d}") for i in range(5)]
        today = []

        with patch("sundial.data.eastmoney_api.fetch_yesterday_pool", AsyncMock(return_value=yesterday)),              patch("sundial.data.eastmoney_api.fetch_limit_up_pool", AsyncMock(return_value=today)):
            from sundial.services.ladder import compute_yesterday_performance
            result = await compute_yesterday_performance("20260522")

        assert result["continued"] == 0
        assert result["rate"] == 0.0

    async def test_empty_yesterday(self):
        """无昨日数据"""
        with patch("sundial.data.eastmoney_api.fetch_yesterday_pool", AsyncMock(return_value=[])),              patch("sundial.data.eastmoney_api.fetch_limit_up_pool", AsyncMock(return_value=[])):
            from sundial.services.ladder import compute_yesterday_performance
            result = await compute_yesterday_performance("20260522")

        assert result["count"] == 0
        assert "message" in result
