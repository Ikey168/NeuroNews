"""
Connector registry: maps a document ``source_type`` to its connector.

Connectors register themselves (typically at import time) so callers can resolve
the right connector for a source type without importing it directly::

    from src.ingestion.connectors.registry import get_connector
    connector = get_connector("news")
    for document in connector.harvest():
        ...
"""

from __future__ import annotations

from typing import Callable, Dict, List, Type, Union

from src.ingestion.connectors.base import Connector

# source_type -> connector class (instantiated lazily on first get).
_REGISTRY: Dict[str, Type[Connector]] = {}
_INSTANCES: Dict[str, Connector] = {}


def register_connector(
    connector_cls: Type[Connector] = None,
) -> Union[Type[Connector], Callable[[Type[Connector]], Type[Connector]]]:
    """Register a connector class under its ``source_type``.

    Usable as a plain call or a class decorator::

        @register_connector
        class NewsConnector(Connector):
            source_type = "news"
    """

    def _do_register(cls: Type[Connector]) -> Type[Connector]:
        source_type = getattr(cls, "source_type", "")
        if not source_type:
            raise ValueError(f"{cls.__name__} must set a non-empty source_type to register")
        _REGISTRY[source_type] = cls
        _INSTANCES.pop(source_type, None)  # drop any stale cached instance
        return cls

    if connector_cls is not None:
        return _do_register(connector_cls)
    return _do_register


def get_connector(source_type: str) -> Connector:
    """Return a (cached) connector instance for ``source_type``."""
    if source_type not in _REGISTRY:
        raise KeyError(
            f"No connector registered for source_type {source_type!r}; "
            f"available: {available_source_types()}"
        )
    if source_type not in _INSTANCES:
        _INSTANCES[source_type] = _REGISTRY[source_type]()
    return _INSTANCES[source_type]


def available_source_types() -> List[str]:
    """List the source types that currently have a registered connector."""
    return sorted(_REGISTRY)


def is_registered(source_type: str) -> bool:
    return source_type in _REGISTRY
