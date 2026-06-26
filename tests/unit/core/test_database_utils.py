"""Tests for src/utils/database_utils.py."""

import pytest

from src.utils.database_utils import (
    DatabaseConfig,
    build_where_clause,
    create_database_config,
    format_connection_string,
    get_duckdb_path,
    get_postgres_connection_params,
    sanitize_table_name,
    validate_connection_params,
)


class TestConnectionParams:
    def test_postgres_defaults(self, monkeypatch):
        for var in ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_SSL_MODE"):
            monkeypatch.delenv(var, raising=False)
        params = get_postgres_connection_params()
        assert params["port"] == 5432
        assert params["username"] == "postgres"
        assert params["ssl_mode"] == "prefer"

    def test_duckdb_path_default(self, monkeypatch):
        monkeypatch.delenv("NEURONEWS_DB_PATH", raising=False)
        assert get_duckdb_path() == "data/neuronews.duckdb"

    def test_duckdb_path_env_override(self, monkeypatch):
        monkeypatch.setenv("NEURONEWS_DB_PATH", "/tmp/test.duckdb")
        assert get_duckdb_path() == "/tmp/test.duckdb"


class TestFormatConnectionString:
    def test_postgresql(self):
        params = {
            "username": "u",
            "password": "p",
            "host": "h",
            "port": 5432,
            "database": "d",
            "ssl_mode": "require",
        }
        conn = format_connection_string(params, "postgresql")
        assert conn == "postgresql://u:p@h:5432/d?sslmode=require"

    def test_duckdb(self, monkeypatch):
        monkeypatch.setenv("NEURONEWS_DB_PATH", "/tmp/test.duckdb")
        conn = format_connection_string({}, "duckdb")
        assert conn == "/tmp/test.duckdb"

    def test_unsupported_type_raises(self):
        with pytest.raises(ValueError):
            format_connection_string({}, "mysql")


class TestValidateConnectionParams:
    def test_all_present(self):
        assert validate_connection_params({"a": 1, "b": "x"}, ["a", "b"]) is True

    def test_missing_key(self):
        assert validate_connection_params({"a": 1}, ["a", "b"]) is False

    def test_empty_value(self):
        assert validate_connection_params({"a": ""}, ["a"]) is False


class TestCreateDatabaseConfig:
    def test_postgres(self):
        config = create_database_config("postgres")
        assert isinstance(config, DatabaseConfig)
        assert config.port == 5432

    def test_unsupported_returns_none(self):
        assert create_database_config("oracle") is None

    def test_error_returns_none(self, monkeypatch):
        monkeypatch.setenv("POSTGRES_PORT", "not-a-number")
        assert create_database_config("postgres") is None


class TestSanitizeTableName:
    def test_clean_name_unchanged(self):
        assert sanitize_table_name("articles") == "articles"

    def test_removes_injection_characters(self):
        assert sanitize_table_name("articles; DROP TABLE x--") == "articlesDROPTABLEx"

    def test_allows_schema_qualified(self):
        assert sanitize_table_name("public.articles") == "public.articles"

    def test_leading_digit_prefixed(self):
        assert sanitize_table_name("1table") == "t_1table"

    def test_empty_string(self):
        assert sanitize_table_name("") == ""


class TestBuildWhereClause:
    def test_empty_conditions(self):
        assert build_where_clause({}) == ""

    def test_string_condition(self):
        assert build_where_clause({"source": "bbc"}) == "source = 'bbc'"

    def test_numeric_conditions(self):
        clause = build_where_clause({"score": 5, "weight": 0.5})
        assert "score = 5" in clause
        assert "weight = 0.5" in clause
        assert " AND " in clause

    def test_list_condition(self):
        clause = build_where_clause({"category": ["tech", "ai"]})
        assert clause == "category IN ('tech', 'ai')"

    def test_key_is_sanitized(self):
        clause = build_where_clause({"name; DROP": "x"})
        assert clause == "nameDROP = 'x'"
