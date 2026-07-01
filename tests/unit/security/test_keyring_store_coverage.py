"""Coverage tests for src/security/keyring_store.py.

Targets the OS-keyring branches (lines 41-49, 80-86, 105-111, 129-135) that the
existing env-var-only tests never exercise, because the real ``keyring`` library
is not installed in this environment. We inject a controllable fake ``keyring``
module into ``sys.modules`` and reset the one-shot ``_KEYRING_AVAILABLE`` cache
so the module takes its keyring-available code paths.
"""
from __future__ import annotations

import sys
import types

import pytest

from src.security import keyring_store


class _FakeKeyringErrors(types.ModuleType):
    """Stand-in for the ``keyring.errors`` submodule."""

    class NoKeyringError(Exception):
        pass

    class KeyringLocked(Exception):
        pass


def _install_fake_keyring(monkeypatch, *, backend):
    """Install a fake ``keyring`` package backed by *backend* and reset cache."""
    kr = types.ModuleType("keyring")
    kr.get_password = backend.get_password
    kr.set_password = backend.set_password
    kr.delete_password = backend.delete_password

    errors_mod = _FakeKeyringErrors("keyring.errors")
    kr.errors = errors_mod

    monkeypatch.setitem(sys.modules, "keyring", kr)
    monkeypatch.setitem(sys.modules, "keyring.errors", errors_mod)
    # Force re-detection of keyring availability.
    monkeypatch.setattr(keyring_store, "_KEYRING_AVAILABLE", None)
    return kr


class _MemoryBackend:
    """In-memory keyring backend that records calls."""

    def __init__(self):
        self.store = {}
        self.get_calls = []
        self.set_calls = []
        self.delete_calls = []

    def get_password(self, service, key):
        self.get_calls.append((service, key))
        return self.store.get((service, key))

    def set_password(self, service, key, value):
        self.set_calls.append((service, key, value))
        self.store[(service, key)] = value

    def delete_password(self, service, key):
        self.delete_calls.append((service, key))
        if (service, key) not in self.store:
            raise KeyError("missing")
        del self.store[(service, key)]


class _RaisingBackend:
    """Backend whose every operation raises, to exercise fallback paths."""

    def get_password(self, service, key):
        raise RuntimeError("keyring locked")

    def set_password(self, service, key, value):
        raise RuntimeError("keyring locked")

    def delete_password(self, service, key):
        raise RuntimeError("keyring locked")


@pytest.fixture(autouse=True)
def _reset_cache():
    """Ensure the availability cache is reset before and after each test."""
    keyring_store._KEYRING_AVAILABLE = None
    yield
    keyring_store._KEYRING_AVAILABLE = None


def test_try_keyring_detects_available(monkeypatch):
    """Lines 41-46: successful import path sets _KEYRING_AVAILABLE True."""
    _install_fake_keyring(monkeypatch, backend=_MemoryBackend())
    assert keyring_store._try_keyring() is True
    # Cached: a second call returns the same value without re-importing.
    assert keyring_store._KEYRING_AVAILABLE is True
    assert keyring_store._try_keyring() is True


def test_try_keyring_unavailable_when_import_fails(monkeypatch):
    """Lines 47-52: ImportError -> availability False (env fallback)."""
    # Remove any keyring module and block re-import.
    monkeypatch.setitem(sys.modules, "keyring", None)
    assert keyring_store._try_keyring() is False
    assert keyring_store._KEYRING_AVAILABLE is False


def test_get_secret_returns_value_from_keyring(monkeypatch):
    """Lines 80-84: keyring returns a non-None value that is used directly."""
    backend = _MemoryBackend()
    backend.store[("neuronews", "BACKUP_KEY")] = "from-keyring"
    _install_fake_keyring(monkeypatch, backend=backend)
    # Make sure env var does NOT shadow, and would differ if used.
    monkeypatch.setenv("NEURONEWS_BACKUP_KEY", "from-env")

    result = keyring_store.get_secret("neuronews", "BACKUP_KEY")
    assert result == "from-keyring"
    assert ("neuronews", "BACKUP_KEY") in backend.get_calls


def test_get_secret_falls_back_to_env_when_keyring_none(monkeypatch):
    """Line 83 false branch: keyring returns None -> env var used."""
    backend = _MemoryBackend()  # empty -> get_password returns None
    _install_fake_keyring(monkeypatch, backend=backend)
    monkeypatch.setenv("NEURONEWS_DB_KEY", "env-value")

    result = keyring_store.get_secret("neuronews", "DB_KEY")
    assert result == "env-value"


def test_get_secret_keyring_exception_falls_back_to_env(monkeypatch):
    """Lines 85-88: keyring.get_password raises -> env var fallback."""
    _install_fake_keyring(monkeypatch, backend=_RaisingBackend())
    monkeypatch.setenv("NEURONEWS_DB_KEY", "recovered-from-env")

    result = keyring_store.get_secret("neuronews", "DB_KEY")
    assert result == "recovered-from-env"


def test_get_secret_keyring_exception_no_env_returns_none(monkeypatch):
    """Lines 85-88: keyring raises and no env var -> None."""
    _install_fake_keyring(monkeypatch, backend=_RaisingBackend())
    monkeypatch.delenv("NEURONEWS_MISSING_KEY", raising=False)

    assert keyring_store.get_secret("neuronews", "MISSING_KEY") is None


def test_set_secret_stores_in_keyring(monkeypatch):
    """Lines 105-109: keyring.set_password succeeds -> returns True."""
    backend = _MemoryBackend()
    _install_fake_keyring(monkeypatch, backend=backend)

    result = keyring_store.set_secret("neuronews", "BACKUP_KEY", "s3cr3t")
    assert result is True
    assert backend.store[("neuronews", "BACKUP_KEY")] == "s3cr3t"
    assert backend.set_calls == [("neuronews", "BACKUP_KEY", "s3cr3t")]


def test_set_secret_keyring_failure_falls_back_to_env(monkeypatch):
    """Lines 110-118: set_password raises -> env var set, returns False."""
    _install_fake_keyring(monkeypatch, backend=_RaisingBackend())
    monkeypatch.delenv("NEURONEWS_BACKUP_KEY", raising=False)

    result = keyring_store.set_secret("neuronews", "BACKUP_KEY", "fallback-val")
    assert result is False
    # The env var was populated as the fallback store.
    import os

    assert os.environ["NEURONEWS_BACKUP_KEY"] == "fallback-val"


def test_delete_secret_success(monkeypatch):
    """Lines 129-133: keyring.delete_password succeeds -> returns True."""
    backend = _MemoryBackend()
    backend.store[("neuronews", "OLD_KEY")] = "to-delete"
    _install_fake_keyring(monkeypatch, backend=backend)

    result = keyring_store.delete_secret("neuronews", "OLD_KEY")
    assert result is True
    assert ("neuronews", "OLD_KEY") not in backend.store
    assert backend.delete_calls == [("neuronews", "OLD_KEY")]


def test_delete_secret_keyring_exception_returns_false(monkeypatch):
    """Lines 134-136: delete_password raises -> swallowed, returns False."""
    _install_fake_keyring(monkeypatch, backend=_RaisingBackend())

    assert keyring_store.delete_secret("neuronews", "ANY_KEY") is False


def test_delete_secret_unavailable_keyring_returns_false(monkeypatch):
    """Line 136: keyring unavailable -> delete is a no-op returning False."""
    monkeypatch.setitem(sys.modules, "keyring", None)
    keyring_store._KEYRING_AVAILABLE = None

    assert keyring_store.delete_secret("neuronews", "ANY_KEY") is False


def test_env_key_derivation_normalizes_hyphens():
    """Line 55-60: env-var name convention (also used by fallback paths)."""
    assert keyring_store._env_key("neuro-news", "backup-key") == "NEURO_NEWS_BACKUP_KEY"
    assert keyring_store._env_key("neuronews", "DB_KEY") == "NEURONEWS_DB_KEY"
