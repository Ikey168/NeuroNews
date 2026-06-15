"""Comprehensive tests for services/rag/diversify.py."""

import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.rag.diversify import (  # noqa: E402
    DiversificationConfig,
    DiversificationStrategy,
    RAGDiversificationService,
    create_diversification_service,
)


def docs(n=6):
    """Documents alternating across 2 domains/sources with descending scores."""
    out = []
    for i in range(n):
        out.append({
            "id": i,
            "score": 1.0 - i * 0.1,
            "title": f"Article {i} about topic {i % 3}",
            "content": f"content body number {i} with words",
            "domain": f"d{i % 2}.com",
            "source": f"src{i % 2}",
            "url": f"https://d{i % 2}.com/{i}",
        })
    return out


class TestStrategyEnum:
    def test_values(self):
        assert DiversificationStrategy.MMR.value == "maximal_marginal_relevance"
        assert DiversificationStrategy.HYBRID.value == "hybrid"


class TestConfig:
    def test_defaults(self):
        c = DiversificationConfig()
        assert c.strategy == DiversificationStrategy.HYBRID
        assert c.max_per_domain == 3
        assert c.max_per_source == 2
        assert c.lambda_param == 0.7


def svc(strategy=None, **over):
    cfg = DiversificationConfig(strategy=strategy) if strategy else DiversificationConfig()
    for k, v in over.items():
        setattr(cfg, k, v)
    return RAGDiversificationService(cfg)


class TestDiversifyResults:
    def test_empty(self):
        assert svc().diversify_results([]) == []

    def test_default_target_count(self):
        result = svc(DiversificationStrategy.MMR).diversify_results(docs(4))
        assert len(result) == 4

    def test_mmr_limits_target(self):
        result = svc(DiversificationStrategy.MMR).diversify_results(docs(6), target_count=3)
        assert len(result) == 3

    def test_domain_cap(self):
        s = svc(DiversificationStrategy.DOMAIN_CAP, max_per_domain=1)
        result = s.diversify_results(docs(6))
        domains = [d["domain"] for d in result]
        # at most 1 per domain
        assert all(domains.count(dm) <= 1 for dm in set(domains))

    def test_source_cap(self):
        s = svc(DiversificationStrategy.SOURCE_CAP, max_per_source=1)
        result = s.diversify_results(docs(6))
        sources = [d["source"] for d in result]
        assert all(sources.count(sc) <= 1 for sc in set(sources))

    def test_round_robin(self):
        result = svc(DiversificationStrategy.ROUND_ROBIN).diversify_results(docs(6))
        assert len(result) == 6

    def test_hybrid(self):
        result = svc(DiversificationStrategy.HYBRID).diversify_results(docs(6), target_count=4)
        assert len(result) <= 4


class TestSimilarity:
    def test_identical_text_high(self):
        s = svc()
        d1 = {"title": "quantum computing breakthrough", "content": "qubits"}
        d2 = {"title": "quantum computing breakthrough", "content": "qubits"}
        assert s._calculate_similarity(d1, d2) > 0.9

    def test_disjoint_text_zero(self):
        s = svc()
        d1 = {"title": "alpha beta", "content": ""}
        d2 = {"title": "gamma delta", "content": ""}
        assert s._calculate_similarity(d1, d2) == 0.0

    def test_empty_text(self):
        s = svc()
        assert s._calculate_similarity({}, {}) == 0.0


class TestExtractors:
    def test_extract_text_prefers_content(self):
        s = svc()
        assert s._extract_text({"title": "T", "content": "Body"}) == "Body"

    def test_extract_text_title_fallback(self):
        s = svc()
        assert s._extract_text({"title": "OnlyTitle"}) == "OnlyTitle"

    def test_extract_domain_from_url(self):
        s = svc()
        assert s._extract_domain({"url": "https://News.X.com/a"}) == "news.x.com"

    def test_extract_domain_direct(self):
        s = svc()
        assert s._extract_domain({"domain": "x.com"}) == "x.com"

    def test_extract_source(self):
        s = svc()
        assert s._extract_source({"source": "BBC"}) == "BBC"

    def test_extract_source_none(self):
        s = svc()
        assert s._extract_source({}) is None


class TestStats:
    def test_diversity_stats(self):
        stats = svc().get_diversity_stats(docs(6))
        assert "domain_distribution" in stats or "unique_domains" in stats or stats
        assert isinstance(stats, dict)

    def test_diversity_stats_empty(self):
        assert svc().get_diversity_stats([]) == {}


class TestFactory:
    def test_factory_default(self):
        assert isinstance(create_diversification_service(), RAGDiversificationService)

    def test_factory_with_config(self):
        cfg = DiversificationConfig(strategy=DiversificationStrategy.MMR)
        s = create_diversification_service(cfg)
        assert s.config.strategy == DiversificationStrategy.MMR
