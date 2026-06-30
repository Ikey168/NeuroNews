#!/usr/bin/env python3
"""
Force the optional-import branches in ``src.api.app`` to execute.

``src/api/app.py`` no longer imports its optional routers at module load time.
Instead it exposes one ``try_import_*`` helper per optional feature; each helper
wraps a real import in ``try/except ImportError`` and sets the matching
``*_AVAILABLE`` module-level flag to ``True`` on success or ``False`` on
``ImportError``. These tests drive both branches of those helpers against the
*real* module, rather than a synthetic copy:

* the failure test patches ``builtins.__import__`` so the helper's underlying
  import raises ``ImportError``, then asserts the flag (and return value)
  flips to ``False``;
* the success test runs the helper with the real (importable) modules and
  asserts the flag flips to ``True``.
"""

import builtins
import importlib

import pytest
from unittest.mock import patch


# Each entry: (try_import helper name, flag name, fromlist submodule that the
# helper imports). The submodule name is matched against the ``fromlist`` passed
# to ``__import__`` so we can force exactly that import to fail. Only features
# whose modules import cleanly in this environment are listed, so the success
# branch is deterministic.
IMPORT_FEATURES = [
    ("try_import_error_handlers", "ERROR_HANDLERS_AVAILABLE", "configure_error_handlers"),
    ("try_import_enhanced_kg_routes", "ENHANCED_KG_AVAILABLE", "enhanced_kg_routes"),
    ("try_import_auth_routes", "AUTH_AVAILABLE", "auth_routes"),
    ("try_import_search_routes", "SEARCH_AVAILABLE", "search_routes"),
    ("try_import_document_routes", "DOCUMENT_ROUTES_AVAILABLE", "document_routes"),
    ("try_import_metrics_routes", "METRICS_ROUTES_AVAILABLE", "metrics_routes"),
    ("try_import_privacy_routes", "PRIVACY_ROUTES_AVAILABLE", "privacy_routes"),
    ("try_import_security_routes", "SECURITY_ROUTES_AVAILABLE", "security_routes"),
]


@pytest.fixture
def app_module():
    """The real ``src.api.app`` module under test (freshly imported)."""
    return importlib.import_module("src.api.app")


def _blocking_import(blocked_fromlist):
    """Return a ``__import__`` replacement that fails for one fromlist target."""
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        # ``from src.api.error_handlers import configure_error_handlers`` and
        # ``from src.api.routes import <submodule>`` both surface the target
        # name in ``fromlist``; ``from src.api.error_handlers import X`` also
        # surfaces it via the dotted module name.
        if fromlist and blocked_fromlist in fromlist:
            raise ImportError(f"forced failure for {blocked_fromlist}")
        if name.endswith("." + blocked_fromlist) or name == blocked_fromlist:
            raise ImportError(f"forced failure for {blocked_fromlist}")
        return real_import(name, globals, locals, fromlist, level)

    return fake_import


@pytest.mark.parametrize("func_name,flag_name,blocked", IMPORT_FEATURES)
def test_try_import_handles_import_error(app_module, func_name, flag_name, blocked):
    """The except-ImportError branch sets the feature flag to False."""
    func = getattr(app_module, func_name)

    # Pre-set the flag True so a False result proves the failure branch ran.
    setattr(app_module, flag_name, True)

    with patch("builtins.__import__", side_effect=_blocking_import(blocked)):
        result = func()

    assert result is False
    assert getattr(app_module, flag_name) is False


@pytest.mark.parametrize("func_name,flag_name,blocked", IMPORT_FEATURES)
def test_try_import_success_paths(app_module, func_name, flag_name, blocked):
    """The success branch sets the feature flag to True when imports work."""
    func = getattr(app_module, func_name)

    # Pre-set the flag False so a True result proves the success branch ran.
    setattr(app_module, flag_name, False)

    result = func()

    assert result is True
    assert getattr(app_module, flag_name) is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
