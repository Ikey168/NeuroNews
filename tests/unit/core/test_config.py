"""Tests for src/config.py."""

from src.config import get_db_config


class TestGetDbConfig:
    def test_testing_defaults(self, monkeypatch):
        for var in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"):
            monkeypatch.delenv(var, raising=False)
        config = get_db_config(testing=True)
        assert config == {
            "host": "localhost",
            "port": 5432,
            "database": "neuronews_test",
            "user": "test_user",
            "password": "test_password",
        }

    def test_production_defaults(self, monkeypatch):
        for var in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"):
            monkeypatch.delenv(var, raising=False)
        config = get_db_config(testing=False)
        assert config == {
            "host": "localhost",
            "port": 5432,
            "database": "neuronews",
            "user": "neuronews",
            "password": "password",
        }

    def test_environment_overrides(self, monkeypatch):
        monkeypatch.setenv("DB_HOST", "db.example.com")
        monkeypatch.setenv("DB_PORT", "6543")
        monkeypatch.setenv("DB_NAME", "custom")
        monkeypatch.setenv("DB_USER", "alice")
        monkeypatch.setenv("DB_PASSWORD", "secret")
        config = get_db_config()
        assert config["host"] == "db.example.com"
        assert config["port"] == 6543
        assert config["database"] == "custom"
        assert config["user"] == "alice"
        assert config["password"] == "secret"
