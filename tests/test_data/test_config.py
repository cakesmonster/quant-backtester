"""Tests for sundial config."""
import os
import tempfile
from pathlib import Path


def test_config_default_db_path():
    """Default DB path is under user data dir."""
    from sundial.config import Config

    cfg = Config()
    assert "sundial.db" in str(cfg.db_path)


def test_config_custom_db_path():
    """Custom db_path overrides default."""
    from sundial.config import Config

    cfg = Config(db_path="/tmp/test.db")
    assert cfg.db_path == Path("/tmp/test.db")


def test_config_hot_rank_slots():
    """Default hot rank cron slots are 1130, 1500, 2100."""
    from sundial.config import Config

    cfg = Config()
    assert cfg.hot_rank_slots == ["1130", "1500", "2100"]


def test_config_push2ex_base_url():
    """push2ex base URL is correct."""
    from sundial.config import Config

    cfg = Config()
    assert cfg.push2ex_base_url == "https://push2ex.eastmoney.com"


def test_config_index_symbols():
    """Index symbols cover the 4 major indices."""
    from sundial.config import Config

    cfg = Config()
    assert cfg.index_symbols == {
        "sh": "sh.000001",
        "sz": "sz.399001",
        "cyb": "sz.399006",
        "kcb": "sh.000688",
    }
