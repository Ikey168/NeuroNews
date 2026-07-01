"""
Coverage tests for src/scraper/extensions/connectors/base.py.

Targets the REMAINING uncovered lines when the base connector suite runs in
isolation: line 137 (``test_connection`` returning False because ``connect``
returned False without raising) plus the ``authenticate`` exception path and
the async-context-manager / status branches, all via a minimal concrete
subclass of the abstract ``BaseConnector``.

Note on lines 122-124: the ``except Exception`` block in ``BaseConnector.
authenticate`` is unreachable through the base method as written -- its ``try``
body is a bare ``return True`` that cannot raise -- so it is genuine (benign)
dead code in the source. It is documented here rather than covered.
"""

import asyncio

import pytest

from src.scraper.extensions.connectors.base import (
    AuthenticationError,
    BaseConnector,
    ConnectionError,
    ConnectorError,
    DataFormatError,
)


class MinimalConnector(BaseConnector):
    """Smallest concrete implementation to instantiate the abstract base."""

    def __init__(self, config, auth_config=None, connect_result=True):
        super().__init__(config, auth_config)
        self._connect_result = connect_result
        self.disconnect_calls = 0

    async def connect(self):
        # Reflect the caller-provided result and mirror it into _connected
        # only when the connection actually succeeds.
        if self._connect_result:
            self._connected = True
        return self._connect_result

    async def disconnect(self):
        self.disconnect_calls += 1
        self._connected = False

    async def fetch_data(self, **kwargs):
        return [{"ok": True}]

    def validate_config(self):
        return "url" in self.config

    def validate_data_format(self, data):
        return isinstance(data, dict)


class TestTestConnectionFalseBranch:
    """Cover line 137: connect() returns False (no exception) -> False."""

    def test_test_connection_returns_false_when_connect_false(self):
        connector = MinimalConnector({"url": "x"}, connect_result=False)

        result = asyncio.run(connector.test_connection())

        assert result is False
        # No exception occurred, so no error was recorded.
        assert connector.last_error is None
        # disconnect() must NOT be called when connect() reports failure.
        assert connector.disconnect_calls == 0

    def test_test_connection_success_disconnects(self):
        connector = MinimalConnector({"url": "x"}, connect_result=True)

        result = asyncio.run(connector.test_connection())

        assert result is True
        assert connector.disconnect_calls == 1


class TestTestConnectionExceptionBranch:
    """Cover lines 138-140: connect() raises -> caught, error stored, False."""

    def test_test_connection_records_error_on_raise(self):
        connector = MinimalConnector({"url": "x"})

        async def boom():
            raise RuntimeError("network down")

        connector.connect = boom  # type: ignore[assignment]

        result = asyncio.run(connector.test_connection())

        assert result is False
        assert isinstance(connector.last_error, ConnectionError)
        assert "Connection test failed" in str(connector.last_error)
        assert "network down" in str(connector.last_error)


class TestAuthenticate:
    """Cover the authenticate() true branches (116-121)."""

    def test_authenticate_true_without_auth_config(self):
        connector = MinimalConnector({"url": "x"})
        assert asyncio.run(connector.authenticate()) is True

    def test_authenticate_true_with_auth_config(self):
        connector = MinimalConnector({"url": "x"}, auth_config={"token": "abc"})
        assert asyncio.run(connector.authenticate()) is True
        # Success path leaves last_error untouched.
        assert connector.last_error is None


class TestGetStatus:
    """Cover get_status() rendering both with and without a stored error."""

    def test_get_status_reports_invalid_config(self):
        # config lacks "url" so validate_config() -> False (exercises 153).
        connector = MinimalConnector({})
        status = connector.get_status()

        assert status["connector_type"] == "MinimalConnector"
        assert status["connected"] is False
        assert status["config_valid"] is False
        assert status["last_error"] is None
        assert isinstance(status["last_check"], str)

    def test_get_status_serializes_last_error(self):
        connector = MinimalConnector({"url": "x"})
        connector._last_error = DataFormatError("bad shape")
        status = connector.get_status()

        assert status["last_error"] == "bad shape"
        assert status["config_valid"] is True


class TestAsyncContextManager:
    """Cover __aenter__ / __aexit__ (157-165), including the failure path."""

    def test_context_manager_yields_self_and_disconnects(self):
        connector = MinimalConnector({"url": "x"})

        async def run():
            async with connector as conn:
                assert conn is connector
                assert connector.is_connected
            return connector.disconnect_calls

        calls = asyncio.run(run())
        assert calls == 1
        assert not connector.is_connected

    def test_context_manager_raises_when_connect_false(self):
        connector = MinimalConnector({"url": "x"}, connect_result=False)

        async def run():
            async with connector:
                pass

        with pytest.raises(ConnectionError, match="Failed to establish connection"):
            asyncio.run(run())
        # Never connected, so __aexit__ never ran and disconnect stayed at 0.
        assert connector.disconnect_calls == 0

    def test_context_manager_disconnects_on_exception_in_body(self):
        connector = MinimalConnector({"url": "x"})

        async def run():
            with pytest.raises(ValueError):
                async with connector:
                    raise ValueError("boom in body")

        asyncio.run(run())
        assert connector.disconnect_calls == 1
        assert not connector.is_connected


class AbstractBodyConnector(BaseConnector):
    """Delegates each abstract method to the base implementation body.

    Invoking ``BaseConnector.<method>`` directly runs the ``pass`` bodies of the
    abstract methods, which are otherwise never executed by concrete overrides.
    """

    async def connect(self):
        return await BaseConnector.connect(self)

    async def disconnect(self):
        return await BaseConnector.disconnect(self)

    async def fetch_data(self, **kwargs):
        return await BaseConnector.fetch_data(self, **kwargs)

    def validate_config(self):
        return BaseConnector.validate_config(self)

    def validate_data_format(self, data):
        return BaseConnector.validate_data_format(self, data)


class TestAbstractMethodBodies:
    """Cover the abstract-method ``pass`` bodies (lines 69, 74, 84, 94, 107)."""

    def test_base_abstract_bodies_return_none(self):
        connector = AbstractBodyConnector({"url": "x"})

        assert asyncio.run(connector.connect()) is None
        assert asyncio.run(connector.disconnect()) is None
        assert asyncio.run(connector.fetch_data()) is None
        assert connector.validate_config() is None
        assert connector.validate_data_format({"any": "thing"}) is None


class TestExceptionHierarchy:
    """Confirm the connector exception classes and their inheritance."""

    def test_all_inherit_from_connector_error(self):
        assert issubclass(AuthenticationError, ConnectorError)
        assert issubclass(ConnectionError, ConnectorError)
        assert issubclass(DataFormatError, ConnectorError)

    def test_authentication_error_is_not_connection_error(self):
        # Distinct leaf classes, only sharing the ConnectorError base.
        assert not issubclass(AuthenticationError, ConnectionError)
        assert str(AuthenticationError("nope")) == "nope"
