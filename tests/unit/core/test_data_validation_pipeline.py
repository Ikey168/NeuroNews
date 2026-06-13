"""Tests for src/database/data_validation_pipeline.py."""

import json

import pytest

from src.database.data_validation_pipeline import (
    ContentValidator,
    DataValidationPipeline,
    DuplicateDetector,
    HTMLCleaner,
    SourceReputationAnalyzer,
    SourceReputationConfig,
    ValidationResult,
)


def make_article(**overrides):
    article = {
        "title": "Major Technology Breakthrough Announced Today",
        "url": "https://reuters.com/article/tech-breakthrough",
        "content": (
            "Scientists announced a significant breakthrough in technology today. "
            "The development promises to change the industry. " * 5
        ),
        "source": "reuters.com",
        "published_date": "2026-06-01T12:00:00",
    }
    article.update(overrides)
    return article


class TestSourceReputationConfig:
    def test_from_file(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "source_reputation": {
                        "trusted_domains": ["good.com"],
                        "questionable_domains": ["meh.com"],
                        "banned_domains": ["bad.com"],
                        "reputation_thresholds": {
                            "trusted": 0.9,
                            "reliable": 0.7,
                            "questionable": 0.4,
                            "unreliable": 0.2,
                        },
                    }
                }
            )
        )
        config = SourceReputationConfig.from_file(str(config_file))
        assert config.trusted_domains == ["good.com"]
        assert config.banned_domains == ["bad.com"]


class TestHTMLCleaner:
    def test_empty_content(self):
        assert HTMLCleaner().clean_content("") == ""

    def test_removes_tags_and_scripts(self):
        cleaner = HTMLCleaner()
        raw = (
            "<script>alert('x')</script><style>.a{}</style>"
            "<noscript>nope</noscript><!-- comment -->"
            "<p>Hello <b>world</b></p>"
        )
        assert cleaner.clean_content(raw) == "Hello world"

    def test_decodes_entities_and_normalizes_whitespace(self):
        cleaner = HTMLCleaner()
        assert cleaner.clean_content("Tom &amp;   Jerry") == "Tom & Jerry"

    def test_removes_metadata_patterns(self):
        cleaner = HTMLCleaner()
        cleaned = cleaner.clean_content("Real text Published: 3 hours ago more text")
        assert "Published" not in cleaned

    def test_clean_title_empty(self):
        assert HTMLCleaner().clean_title("") == ""

    def test_clean_title_strips_tags_and_suffix(self):
        cleaner = HTMLCleaner()
        assert (
            cleaner.clean_title("<b>Big News</b>  -  Reuters Top Stories")
            == "Big News"
        )


class TestDuplicateDetector:
    def test_first_article_not_duplicate(self):
        detector = DuplicateDetector()
        is_dup, reason = detector.is_duplicate(make_article())
        assert is_dup is False

    def test_duplicate_url(self):
        detector = DuplicateDetector()
        detector.is_duplicate(make_article())
        is_dup, reason = detector.is_duplicate(
            make_article(title="Different", content="Other content entirely")
        )
        assert (is_dup, reason) == (True, "duplicate_url")

    def test_duplicate_title(self):
        detector = DuplicateDetector()
        detector.is_duplicate(make_article())
        is_dup, reason = detector.is_duplicate(
            make_article(url="https://other.com/x", content="Other content")
        )
        assert (is_dup, reason) == (True, "duplicate_title")

    def test_duplicate_content(self):
        detector = DuplicateDetector()
        detector.is_duplicate(make_article())
        is_dup, reason = detector.is_duplicate(
            make_article(url="https://other.com/x", title="A Different Headline Here")
        )
        assert (is_dup, reason) == (True, "duplicate_content")

    def test_fuzzy_title_duplicate(self):
        detector = DuplicateDetector()
        detector.is_duplicate(make_article(title="Breaking News About The Economy Today"))
        is_dup, reason = detector.is_duplicate(
            make_article(
                url="https://other.com/x",
                title="The Breaking News About Economy Today!",
                content="Some completely different words in this one",
            )
        )
        assert (is_dup, reason) == (True, "similar_title")


class TestSourceReputationAnalyzer:
    def test_missing_url(self):
        result = SourceReputationAnalyzer().analyze_source({"title": "x"})
        assert result["credibility_level"] == "unknown"
        assert "missing_url" in result["flags"]

    def test_trusted_domain(self):
        result = SourceReputationAnalyzer().analyze_source(make_article())
        assert result["reputation_score"] == 0.95
        assert result["credibility_level"] == "trusted"
        assert result["domain"] == "reuters.com"

    def test_questionable_domain(self):
        article = make_article(url="https://dailymail.co.uk/story")
        result = SourceReputationAnalyzer().analyze_source(article)
        assert result["credibility_level"] == "questionable"
        assert "questionable_source" in result["flags"]

    def test_banned_domain(self):
        article = make_article(url="https://fakenews.com/story")
        result = SourceReputationAnalyzer().analyze_source(article)
        assert result["reputation_score"] == 0.1
        assert result["credibility_level"] == "unreliable"
        assert "banned_domain" in result["flags"]

    def test_edu_domain_bonus(self):
        article = make_article(url="https://research.university.edu/paper")
        result = SourceReputationAnalyzer().analyze_source(article)
        assert result["reputation_score"] == 0.7

    def test_org_domain_bonus(self):
        article = make_article(url="https://charity.org/news")
        result = SourceReputationAnalyzer().analyze_source(article)
        assert result["reputation_score"] == 0.6

    def test_clickbait_flag(self):
        article = make_article(title="You won't believe what happened next")
        result = SourceReputationAnalyzer().analyze_source(article)
        assert "clickbait_title" in result["flags"]

    def test_excessive_caps_flag(self):
        article = make_article(title="SHOCKING development in the news")
        result = SourceReputationAnalyzer().analyze_source(article)
        assert "excessive_caps" in result["flags"]

    def test_excessive_exclamation_flag(self):
        article = make_article(title="Wow!!! Amazing!!! News!!!")
        result = SourceReputationAnalyzer().analyze_source(article)
        assert "excessive_exclamation" in result["flags"]

    def test_thin_content_flag(self):
        article = make_article(content="Too short.")
        result = SourceReputationAnalyzer().analyze_source(article)
        assert "thin_content" in result["flags"]


class TestContentValidator:
    def test_valid_article(self):
        result = ContentValidator().validate_content(make_article())
        assert result["is_valid"] is True
        assert result["issues"] == []
        assert result["quality_metrics"]["word_count"] > 0

    def test_missing_title(self):
        result = ContentValidator().validate_content(make_article(title=""))
        assert "missing_title" in result["issues"]

    def test_title_too_short(self):
        result = ContentValidator().validate_content(make_article(title="Tiny"))
        assert "title_too_short" in result["issues"]

    def test_title_very_long(self):
        result = ContentValidator().validate_content(make_article(title="x" * 250))
        assert "title_very_long" in result["warnings"]

    def test_title_all_caps(self):
        result = ContentValidator().validate_content(
            make_article(title="BREAKING NEWS TODAY")
        )
        assert "title_all_caps" in result["warnings"]

    def test_excessive_question_marks(self):
        result = ContentValidator().validate_content(
            make_article(title="What???? Is???? Happening????")
        )
        assert "excessive_question_marks" in result["warnings"]

    def test_missing_content(self):
        result = ContentValidator().validate_content(make_article(content=""))
        assert "missing_content" in result["issues"]

    def test_content_too_short(self):
        result = ContentValidator().validate_content(make_article(content="short"))
        assert "content_too_short" in result["issues"]
        assert "insufficient_word_count" in result["issues"]

    def test_short_content_warning(self):
        content = "word " * 30  # 150 chars, above min 100 but below 200
        result = ContentValidator().validate_content(make_article(content=content))
        assert "short_content" in result["warnings"]

    def test_content_very_long(self):
        result = ContentValidator().validate_content(
            make_article(content="word " * 12000)
        )
        assert "content_very_long" in result["warnings"]

    def test_placeholder_content(self):
        content = "Lorem ipsum dolor sit amet " * 10
        result = ContentValidator().validate_content(make_article(content=content))
        assert "placeholder_content" in result["issues"]

    def test_missing_url(self):
        result = ContentValidator().validate_content(make_article(url=""))
        assert "missing_url" in result["issues"]

    def test_invalid_url_scheme(self):
        result = ContentValidator().validate_content(
            make_article(url="example.com/no-scheme")
        )
        assert "invalid_url_scheme" in result["issues"]

    def test_unusual_url_scheme(self):
        result = ContentValidator().validate_content(
            make_article(url="ftp://example.com/x")
        )
        assert "unusual_url_scheme" in result["warnings"]

    def test_shortened_url(self):
        result = ContentValidator().validate_content(
            make_article(url="https://bit.ly/abc")
        )
        assert "shortened_url" in result["warnings"]

    def test_missing_date(self):
        result = ContentValidator().validate_content(make_article(published_date=""))
        assert "missing_publication_date" in result["warnings"]

    def test_future_date(self):
        result = ContentValidator().validate_content(
            make_article(published_date="2099-01-01T00:00:00")
        )
        assert "future_publication_date" in result["issues"]

    def test_very_old_article(self):
        result = ContentValidator().validate_content(
            make_article(published_date="2015-01-01T00:00:00")
        )
        assert "very_old_article" in result["warnings"]

    def test_old_article(self):
        result = ContentValidator().validate_content(
            make_article(published_date="2026-01-01T00:00:00")
        )
        assert "old_article" in result["warnings"]

    def test_invalid_date(self):
        result = ContentValidator().validate_content(
            make_article(published_date="not-a-date-at-all-99")
        )
        assert "invalid_date_format" in result["issues"]


class TestDataValidationPipeline:
    def test_valid_article_passes(self):
        pipeline = DataValidationPipeline()
        result = pipeline.process_article(make_article())
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert result.cleaned_data["source_credibility"] == "trusted"
        assert result.cleaned_data["content_quality"] in ("high", "medium")
        assert "validated_at" in result.cleaned_data

    def test_invalid_input_returns_none(self):
        pipeline = DataValidationPipeline()
        assert pipeline.process_article(None) is None
        assert pipeline.process_article("not a dict") is None
        assert pipeline.process_article({}) is None

    def test_duplicate_rejected(self):
        pipeline = DataValidationPipeline()
        assert pipeline.process_article(make_article()) is not None
        assert pipeline.process_article(make_article()) is None
        stats = pipeline.get_statistics()
        assert stats["rejected_count"] == 1

    def test_banned_domain_rejected(self):
        pipeline = DataValidationPipeline()
        result = pipeline.process_article(
            make_article(url="https://fakenews.com/story")
        )
        assert result is None

    def test_missing_content_rejected(self):
        pipeline = DataValidationPipeline()
        result = pipeline.process_article(make_article(content=""))
        assert result is None

    def test_source_extracted_from_url(self):
        pipeline = DataValidationPipeline()
        article = make_article(source="")
        result = pipeline.process_article(article)
        assert result.cleaned_data["source"] == "reuters.com"

    def test_html_cleaned(self):
        pipeline = DataValidationPipeline()
        article = make_article(
            title="<b>Major Technology Breakthrough Announced</b>",
            content="<p>" + ("Real content paragraph here. " * 20) + "</p>",
        )
        result = pipeline.process_article(article)
        assert "<b>" not in result.cleaned_data["title"]
        assert "<p>" not in result.cleaned_data["content"]

    def test_statistics(self):
        pipeline = DataValidationPipeline()
        pipeline.process_article(make_article())
        pipeline.process_article(make_article())  # duplicate -> rejected
        stats = pipeline.get_statistics()
        assert stats["processed_count"] == 2
        assert stats["accepted_count"] == 1
        assert stats["acceptance_rate"] == 50.0
        assert stats["rejection_rate"] == 50.0

    def test_statistics_empty(self):
        stats = DataValidationPipeline().get_statistics()
        assert stats["acceptance_rate"] == 0
        assert stats["rejection_rate"] == 0

    def test_reset_statistics(self):
        pipeline = DataValidationPipeline()
        pipeline.process_article(make_article())
        pipeline.reset_statistics()
        assert pipeline.get_statistics()["processed_count"] == 0

    def test_custom_config(self):
        config = SourceReputationConfig(
            trusted_domains=["mysite.com"],
            questionable_domains=[],
            banned_domains=[],
            reputation_thresholds={
                "trusted": 0.9,
                "reliable": 0.7,
                "questionable": 0.4,
                "unreliable": 0.2,
            },
        )
        pipeline = DataValidationPipeline(config)
        result = pipeline.process_article(
            make_article(url="https://mysite.com/story")
        )
        assert result.cleaned_data["source_credibility"] == "trusted"

    def test_quality_rating_bands(self):
        pipeline = DataValidationPipeline()
        assert pipeline._get_content_quality_rating(85) == "high"
        assert pipeline._get_content_quality_rating(70) == "medium"
        assert pipeline._get_content_quality_rating(40) == "low"
