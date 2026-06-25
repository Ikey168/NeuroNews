"""
Domain-pack system for NeuroNews.

A domain pack bundles enrichers, API routes, and UI feature flags for one
knowledge domain (e.g. news). Packs are opt-in via ``config/domain_packs.json``;
the ``news`` pack ships enabled by default so nothing regresses.

Usage::

    from src.domains.registry import is_pack_enabled, load_config

    load_config()                 # reads config/domain_packs.json once at startup
    if is_pack_enabled("news"):
        app.include_router(news_router)
"""

from src.domains.base import DomainPack, Enricher
from src.domains.registry import (
    get_enabled_packs,
    get_pack,
    is_pack_enabled,
    load_config,
    register_pack,
)

__all__ = [
    "DomainPack",
    "Enricher",
    "get_enabled_packs",
    "get_pack",
    "is_pack_enabled",
    "load_config",
    "register_pack",
]
