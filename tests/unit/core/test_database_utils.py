"""Tests for src/utils/database_utils.py."""

import pytest

from src.utils.database_utils import (
    DatabaseConfig,
    build_where_clause,
    create_database_config,
    format_connection_string,
    get_postgres_connection_params,
    get_redshift_connection_params,
    get_snowflake_connection_params,
    sanitize_table_name,
    validate_connection_params,
)


class TestConnectionParams:
    def test_redshift_defaults(self, monkeypatch):
        for var in (
            "REDSHIFT_HOST",
            "REDSHIFT_PORT",
            "REDSHIFT_DATABASE",
            "REDSHIFT_USERNAME",
            "REDSHIFT_PASSWORD",
            "REDSHIFT_SSL_MODE",
        ):
            monkeypatch.delenv(var, raising=False)
        params = get_redshift_connection_params()
        assert params["host"] == "localhost"
        assert params["port"] == 5439
        assert params["database"] == "neuronews"
        assert params["ssl_mode"] == "require"

    def test_redshift_env_overrides(self, monkeypatch):
        monkeypatch.setenv("REDSHIFT_HOST", "redshift.aws")
        monkeypatch.setenv("REDSHIFT_PORT", "5440")
        params = get_redshift_connection_params()
        assert params["host"] == "redshift.aws"
        assert params["port"] == 5440

    def test_postgres_defaults(self, monkeypatch):
        for var in ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_SSL_MODE"):
            monkeypatch.delenv(var, raising=False)
        params = get_postgres_connection_params()
        assert params["port"] == 5432
        assert params["username"] == "postgres"
        assert params["ssl_mode"] == "prefer"

    def test_snowflake_defaults(self, monkeypatch):
        for var in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_ROLE"):
            monkeypatch.delenv(var, raising=False)
        params = get_snowflake_connection_params()
        assert params["account"] == "mock_account"
        assert params["warehouse"] == "COMPUTE_WH"
        assert params["role"] == "SYSADMIN"


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

    def test_redshift(self):
        params = {
            "username": "u",
            "password": "p",
            "host": "h",
            "port": 5439,
            "database": "d",
        }
        conn = format_connection_string(params, "redshift")
        assert conn.startswith("redshift://u:p@h:5439/d")
        # default ssl mode applied when missing
        assert conn.endswith("?sslmode=prefer")

    def test_snowflake(self):
        params = {
            "user": "u",
            "password": "p",
            "account": "acct",
            "database": "d",
            "schema": "s",
            "warehouse": "wh",
            "role": "r",
        }
        conn = format_connection_string(params, "snowflake")
        assert conn == "snowflake://u:p@acct/d/s?warehouse=wh&role=r"

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
    def test_redshift(self, monkeypatch):
        monkeypatch.delenv("REDSHIFT_SSL_MODE", raising=False)
        config = create_database_config("redshift")
        assert isinstance(config, DatabaseConfig)
        assert config.port == 5439
        assert config.ssl_mode == "require"

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
