"""
News domain pack.

Bundles the enrichers and API routes that only make sense for
``source_type = "news"`` documents: fake-news detection, sentiment analysis,
event clustering, and influence-network analysis.

Importing this module registers ``NewsDomainPack`` in the domain registry.
The pack is *enabled* only when ``"news"`` appears in ``config/domain_packs.json``
(or the ``NEURONEWS_ENABLED_PACKS`` env var). It is registered regardless so
the registry always knows the pack exists.
"""

from src.domains.news.pack import NewsDomainPack
from src.domains.registry import register_pack

register_pack(NewsDomainPack)

__all__ = ["NewsDomainPack"]
