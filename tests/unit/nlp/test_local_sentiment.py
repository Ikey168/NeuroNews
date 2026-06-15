"""Unit tests for the local lexicon-based sentiment analyzer.

These tests verify that ``LocalSentimentAnalyzer`` runs with no AWS account
and no boto3, while preserving the output shape of the former AWS Comprehend
implementation.
"""

import importlib

import pytest

from src.nlp.aws_sentiment import LocalSentimentAnalyzer


def test_no_boto3_import_in_module():
    """The module must not import boto3 / botocore anymore."""
    module = importlib.import_module("src.nlp.aws_sentiment")
    source = importlib.util.find_spec("src.nlp.aws_sentiment").origin
    with open(source, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "import boto3" not in text
    assert "botocore" not in text
    # Old AWS-named class should be gone (no backward-compat alias).
    assert not hasattr(module, "AWSComprehendSentimentAnalyzer")


def test_instantiates_without_aws():
    analyzer = LocalSentimentAnalyzer()
    assert analyzer is not None


def test_positive_sentiment():
    analyzer = LocalSentimentAnalyzer()
    result = analyzer.analyze("This is a great and wonderful success")
    assert result["label"] == "POSITIVE"
    assert result["score"] > 0.0
    assert result["provider"] == "local_lexicon"


def test_negative_sentiment():
    analyzer = LocalSentimentAnalyzer()
    result = analyzer.analyze("This is a terrible and awful failure")
    assert result["label"] == "NEGATIVE"
    assert result["score"] > 0.0


def test_neutral_sentiment():
    analyzer = LocalSentimentAnalyzer()
    result = analyzer.analyze("The meeting is scheduled for tomorrow afternoon")
    assert result["label"] == "NEUTRAL"


def test_mixed_sentiment_has_mixed_score():
    analyzer = LocalSentimentAnalyzer()
    result = analyzer.analyze("great success but also terrible failure")
    assert result["all_scores"]["mixed"] > 0.0


def test_output_shape_matches_contract():
    analyzer = LocalSentimentAnalyzer()
    result = analyzer.analyze("good news", language_code="en")
    for key in ("label", "score", "text", "all_scores", "provider", "language_code"):
        assert key in result
    for sub in ("positive", "negative", "neutral", "mixed"):
        assert sub in result["all_scores"]
    assert result["language_code"] == "en"
    assert isinstance(result["score"], float)


def test_empty_text_returns_error():
    analyzer = LocalSentimentAnalyzer()
    result = analyzer.analyze("   ")
    assert result["label"] == "ERROR"
    assert result["score"] == 0.0


def test_analyze_batch():
    analyzer = LocalSentimentAnalyzer()
    results = analyzer.analyze_batch(["great win", "terrible loss", ""])
    assert len(results) == 3
    assert results[0]["label"] == "POSITIVE"
    assert results[1]["label"] == "NEGATIVE"
    assert results[2]["label"] == "ERROR"


def test_batch_analyze_alias():
    analyzer = LocalSentimentAnalyzer()
    assert analyzer.batch_analyze(["good"]) == analyzer.analyze_batch(["good"])


def test_empty_batch_returns_empty_list():
    analyzer = LocalSentimentAnalyzer()
    assert analyzer.analyze_batch([]) == []


def test_create_analyzer_local_provider():
    from src.nlp.sentiment_analysis import create_analyzer

    analyzer = create_analyzer(provider="local")
    assert isinstance(analyzer, LocalSentimentAnalyzer)


def test_create_analyzer_aws_provider_returns_local():
    """Legacy 'aws' provider keyword now yields the local analyzer."""
    from src.nlp.sentiment_analysis import create_analyzer

    analyzer = create_analyzer(provider="aws")
    assert isinstance(analyzer, LocalSentimentAnalyzer)


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
