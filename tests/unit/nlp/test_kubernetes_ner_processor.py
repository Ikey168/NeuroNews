"""Tests for src/nlp/kubernetes/ner_processor.py (mocked NER/DB)."""

import json
import os
import sys
from unittest.mock import MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("torch")

from nlp.kubernetes.ner_processor import KubernetesNERProcessor  # noqa: E402


@pytest.fixture
def proc(tmp_path):
    return KubernetesNERProcessor(
        batch_size=10, use_gpu=False,
        output_dir=str(tmp_path / "out"), model_cache_dir=str(tmp_path / "models"),
    )


def article(**over):
    base = dict(
        article_id="a1", title="Google news", content="Google announced something",
        url="https://x/1", source="bbc", published_date="2026-01-01",
        scraped_at="2026-01-02",
    )
    base.update(over)
    return base


def entity(**over):
    base = dict(text="Google", type="ORG", confidence=0.95,
                start_position=0, end_position=6)
    base.update(over)
    return base


class TestInit:
    def test_defaults(self, proc):
        assert proc.confidence_threshold == 0.7
        assert proc.use_gpu is False
        assert proc.stats["entities_extracted"] == 0


class TestProcessBatch:
    def test_extracts_entities(self, proc):
        ner = MagicMock()
        ner.extract_entities.return_value = [entity(), entity(text="Meta")]
        proc.ner_processor = ner
        results = proc.process_article_batch([article()])
        assert len(results) == 2
        assert results[0]["entity_text"] == "Google"
        assert results[0]["entity_type"] == "ORG"
        assert proc.stats["entities_extracted"] == 2
        assert proc.stats["articles_processed"] == 1

    def test_per_article_error(self, proc):
        ner = MagicMock()
        ner.extract_entities.side_effect = RuntimeError("ner failed")
        proc.ner_processor = ner
        results = proc.process_article_batch([article()])
        assert results == []
        assert proc.stats["articles_failed"] == 1

    def test_empty_entities(self, proc):
        ner = MagicMock()
        ner.extract_entities.return_value = []
        proc.ner_processor = ner
        results = proc.process_article_batch([article()])
        assert results == []
        assert proc.stats["articles_processed"] == 1


class TestSaveStats:
    def test_save_stats(self, proc):
        proc.stats["articles_processed"] = 3
        proc.stats["entities_extracted"] = 7
        proc.save_processing_stats()
        files = [f for f in os.listdir(proc.output_dir) if f.endswith(".json")]
        assert len(files) == 1
        data = json.loads(open(os.path.join(proc.output_dir, files[0])).read())
        assert data["entities_extracted"] == 7
