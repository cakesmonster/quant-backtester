"""TDD: sundial 板块数据补全 — 池子概念增强"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, "/root/.hermes/projects/sundial/src")
from sundial.services.dashboard import _enrich_concepts


# ── Fixtures ──

@pytest.fixture
def sample_sector_map():
    """模拟 stock_sector_map.json"""
    return {
        "000723": {"行业": ["煤炭开采加工"], "概念": ["煤化工概念", "氢能源"]},
        "600989": {"行业": ["煤炭开采加工"], "概念": ["煤化工概念"]},
        "002579": {"行业": ["元件"], "概念": ["5G", "AI PC", "PCB概念"]},
        "600519": {"行业": ["白酒"], "概念": []},
        "999999": {"行业": [], "概念": []},  # 空板块
    }


@pytest.fixture
def temp_sector_file(sample_sector_map, monkeypatch):
    tmp = tempfile.mktemp(suffix=".json")
    with open(tmp, "w") as f:
        json.dump(sample_sector_map, f)
    monkeypatch.setattr(
        "sundial.services.dashboard.SECTOR_MAP_PATH", tmp
    )
    yield tmp
    os.unlink(tmp)


# ── 测试 _enrich_concepts ──

class TestEnrichConcepts:
    def test_enriches_pool_concepts(self, temp_sector_file):
        """池子中已有热榜 concepts，补全后更多"""
        pool = {
            "000723": {
                "name": "美锦能源",
                "changePct": 5.0,
                "concepts": {"煤化工概念"},  # 热榜只给了1个
            },
            "002579": {
                "name": "中京电子",
                "changePct": 8.0,
                "concepts": {"PCB概念"},  # 热榜只有1个
            },
        }

        enriched = _enrich_concepts(pool)

        # 000723 应该补全了氢能源
        assert "氢能源" in enriched["000723"]["concepts"]
        assert "煤化工概念" in enriched["000723"]["concepts"]
        assert "煤炭开采加工" in enriched["000723"]["concepts"]

        # 002579 补全了 5G, AI PC
        assert "5G" in enriched["002579"]["concepts"]
        assert "AI PC" in enriched["002579"]["concepts"]

    def test_preserves_existing_concepts(self, temp_sector_file):
        """已有概念不丢失"""
        pool = {
            "000723": {
                "name": "美锦",
                "changePct": 3.0,
                "concepts": {"自定义概念"},  # 不在 sector_map 里
            },
        }
        enriched = _enrich_concepts(pool)
        assert "自定义概念" in enriched["000723"]["concepts"]
        assert "煤化工概念" in enriched["000723"]["concepts"]

    def test_stock_not_in_map(self, temp_sector_file):
        """不在板块数据中的股票保持原样"""
        pool = {
            "300750": {
                "name": "宁德时代",
                "changePct": 2.0,
                "concepts": {"锂电池概念"},
            },
        }
        enriched = _enrich_concepts(pool)
        assert enriched["300750"]["concepts"] == {"锂电池概念"}

    def test_empty_sectors_still_works(self, temp_sector_file):
        """没有板块归属的股票（如白酒行业只有行业无概念）"""
        pool = {
            "600519": {
                "name": "茅台",
                "changePct": 1.0,
                "concepts": set(),
            },
        }
        enriched = _enrich_concepts(pool)
        # 白酒是行业，sector_map 概念为空，但行业会被加入
        assert "白酒" in enriched["600519"]["concepts"]

    def test_empty_pool(self, temp_sector_file):
        assert _enrich_concepts({}) == {}
