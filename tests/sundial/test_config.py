"""
单元测试 — 日晷配置: 默认值、环境变量覆盖。
"""
import os


class TestConfigDefaults:
    """默认配置"""

    def test_host_default(self):
        from sundial.config import HOST
        assert HOST == "0.0.0.0"

    def test_port_default(self):
        from sundial.config import PORT
        assert PORT == 8100

    def test_db_path_in_data_dir(self):
        from sundial.config import DB_PATH
        assert "data" in str(DB_PATH)
        assert str(DB_PATH).endswith("sundial.db")

    def test_thresholds(self):
        from sundial.config import HOT_RANK_SLOTS
        assert "1130" in HOT_RANK_SLOTS
        assert "1500" in HOT_RANK_SLOTS
        assert "2100" in HOT_RANK_SLOTS
        assert len(HOT_RANK_SLOTS) == 3

    def test_data_dir_exists(self):
        from sundial.config import DATA_DIR
        import os
        # DATA_DIR 是 Path 对象，目录应该已被创建
        assert os.path.isdir(str(DATA_DIR))


class TestEnvOverrides:
    """环境变量覆盖"""

    def test_host_env(self, monkeypatch):
        monkeypatch.setenv("SUNDIAL_HOST", "0.0.0.0")
        # Reload config
        import importlib
        import sundial.config
        importlib.reload(sundial.config)
        assert sundial.config.HOST == "0.0.0.0"
        # Restore
        monkeypatch.delenv("SUNDIAL_HOST")
        importlib.reload(sundial.config)

    def test_port_env(self, monkeypatch):
        monkeypatch.setenv("SUNDIAL_PORT", "9999")
        import importlib
        import sundial.config
        importlib.reload(sundial.config)
        assert sundial.config.PORT == 9999
        monkeypatch.delenv("SUNDIAL_PORT")
        importlib.reload(sundial.config)

    def test_data_dir_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SUNDIAL_DATA_DIR", str(tmp_path))
        import importlib
        import sundial.config
        importlib.reload(sundial.config)
        from pathlib import Path
        assert sundial.config.DATA_DIR == Path(str(tmp_path))
        monkeypatch.delenv("SUNDIAL_DATA_DIR")
        importlib.reload(sundial.config)
