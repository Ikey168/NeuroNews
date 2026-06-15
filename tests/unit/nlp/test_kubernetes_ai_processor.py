"""Tests for src/nlp/kubernetes/ai_processor.py (deps mocked where heavy)."""

import json
import os
import sys
from unittest.mock import MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("torch")
pytest.importorskip("umap")
np = pytest.importorskip("numpy")

from nlp.kubernetes.ai_processor import KubernetesAIProcessor  # noqa: E402


@pytest.fixture
def proc(tmp_path):
    return KubernetesAIProcessor(
        batch_size=10, use_gpu=False, num_topics=2,
        output_dir=str(tmp_path / "out"), model_cache_dir=str(tmp_path / "m"),
        gpu_cache_dir=str(tmp_path / "g"),
    )


def article(**over):
    base = dict(article_id="a1", title="AI news", content="machine learning models")
    base.update(over)
    return base


class TestInit:
    def test_defaults(self, proc):
        assert proc.num_topics == 2
        assert proc.use_gpu is False
        assert proc.stats["topics_extracted"] == 0
        assert os.path.isdir(proc.output_dir)


class TestPreprocess:
    def test_combines_and_strips(self, proc):
        out = proc.preprocess_texts([article(title="T", content="a   b\n\nc")])
        assert out == ["T. a b c"]

    def test_truncates_long(self, proc, monkeypatch):
        monkeypatch.setenv("ARTICLE_TEXT_MAX_LENGTH", "20")
        out = proc.preprocess_texts([article(content="word " * 50)])
        assert len(out[0]) <= 60  # truncated near boundary

    def test_empty_list(self, proc):
        assert proc.preprocess_texts([]) == []


class TestProcessBatch:
    def test_batch_with_mocked_pipeline(self, proc, monkeypatch):
        monkeypatch.setattr(proc, "generate_embeddings",
                            lambda texts: np.ones((len(texts), 3)))
        monkeypatch.setattr(
            proc, "perform_topic_modeling",
            lambda texts, emb: ([0], [{"topic_id": 0, "words": ["ai"], "label": "Tech"}]),
        )
        results = proc.process_article_batch([article()])
        assert isinstance(results, list)
        assert proc.stats["batches_processed"] == 1

    def test_batch_empty_embeddings(self, proc, monkeypatch):
        monkeypatch.setattr(proc, "generate_embeddings", lambda texts: np.array([]))
        assert proc.process_article_batch([article()]) == []


class TestSaveStats:
    def test_save_stats(self, proc):
        proc.stats["articles_processed"] = 4
        proc.stats["topics_extracted"] = 2
        proc.save_processing_stats()
        files = [f for f in os.listdir(proc.output_dir) if f.endswith(".json")]
        assert len(files) == 1
        data = json.loads(open(os.path.join(proc.output_dir, files[0])).read())
        assert data["articles_processed"] == 4
