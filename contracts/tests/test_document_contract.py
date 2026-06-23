"""
Contract tests for document-ingest-v1 (M0 keystone of the knowledge-engine pivot).

Validates that:
1. Valid document fixtures pass schema validation.
2. Invalid document fixtures fail with DataContractViolation.
3. The Article <-> Document adapter round-trips news fields losslessly, so the
   legacy news pipeline stays green.
"""

import json
from pathlib import Path

import pytest

from services.ingest.common.contracts import DataContractViolation
from services.ingest.common.document_contracts import DocumentIngestValidator
from services.ingest.common.document_model import (
    Document,
    article_to_document,
    article_enrichments,
    document_to_article,
)

REPO_ROOT = Path(__file__).parent.parent.parent
EXAMPLES = REPO_ROOT / "contracts" / "examples" / "document-ingest-v1"
ARTICLE_EXAMPLES = REPO_ROOT / "contracts" / "examples"


def _load(path: Path) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def _fixtures(subdir: str):
    return sorted((EXAMPLES / subdir).glob("*.json"))


@pytest.fixture(scope="module")
def validator():
    return DocumentIngestValidator()


@pytest.mark.parametrize("fixture_path", _fixtures("valid"), ids=lambda p: p.name)
def test_valid_documents_pass(validator, fixture_path):
    """Every valid fixture validates cleanly against document-ingest-v1."""
    validator.validate_document(_load(fixture_path))


@pytest.mark.parametrize("fixture_path", _fixtures("invalid"), ids=lambda p: p.name)
def test_invalid_documents_rejected(validator, fixture_path):
    """Every invalid fixture is rejected with DataContractViolation."""
    with pytest.raises(DataContractViolation):
        validator.validate_document(_load(fixture_path))


def test_source_type_enum_enforced():
    """A bad source_type is rejected by the Document model."""
    with pytest.raises(ValueError):
        Document(
            document_id="x",
            source_type="tweet",
            language="en",
            ingested_at=1735371342000,
        )


def test_document_model_roundtrip():
    """Document.to_dict/from_dict is stable."""
    doc = Document(
        document_id="doc-1",
        source_type="paper",
        language="en",
        ingested_at=1735371342000,
        metadata={"doi": "10.1/x"},
    )
    assert Document.from_dict(doc.to_dict()) == doc


def test_article_to_document_produces_valid_document(validator):
    """An adapted article passes document-ingest-v1 validation as source_type=news."""
    article = _load(ARTICLE_EXAMPLES / "valid" / "valid-full-article.json")
    document = article_to_document(article)

    validator.validate_document(document)
    assert document["source_type"] == "news"
    assert document["document_id"] == article["article_id"]
    assert document["content"] == article["body"]
    assert document["created_at"] == article["published_at"]
    assert document["metadata"].get("country") == article.get("country")
    # Enrichments must not leak into the core record.
    assert "sentiment_score" not in document
    assert "topics" not in document


@pytest.mark.parametrize(
    "fixture_name",
    [
        "valid-full-article.json",
        "valid-minimal-fields.json",
        "valid-french-article.json",
        "valid-empty-content.json",
    ],
)
def test_article_document_roundtrip_lossless(fixture_name):
    """article -> (document + enrichments) -> article preserves all news fields."""
    original = _load(ARTICLE_EXAMPLES / "valid" / fixture_name)

    document = article_to_document(original)
    enrichments = article_enrichments(original)
    restored = document_to_article(document, enrichments)

    # Normalize optional fields that default rather than being absent.
    expected = dict(original)
    expected.setdefault("title", None)
    expected.setdefault("body", None)
    expected.setdefault("country", None)
    expected.setdefault("sentiment_score", None)
    expected.setdefault("topics", [])

    assert restored == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
