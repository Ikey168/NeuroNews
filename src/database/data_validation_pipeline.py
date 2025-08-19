"""
Comprehensive Data Validation Pipeline for NeuroNews.

This module implements advanced data validation, cleaning, and quality assurance
for scraped news articles before they are stored in the database.

Issue #21: Set Up Data Validation Pipeline
- Implement duplicate detection before storing articles
- Validate article length, title consistency, and publication date
- Remove HTML artifacts & unnecessary metadata
- Flag potential fake or low-quality news sources
"""

import hashlib
import html
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

# Set up logging
logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of article validation process."""

    score: float
    is_valid: bool
    issues: List[str]
    warnings: List[str]
    cleaned_data: Dict[str, Any]


@dataclass
class SourceReputationConfig:
    """Configuration for source reputation scoring."""

    trusted_domains: List[str]
    questionable_domains: List[str]
    banned_domains: List[str]
    reputation_thresholds: Dict[str, float]

    @classmethod
    def from_file(cls, config_file: str) -> "SourceReputationConfig":
        """Load configuration from JSON file."""
        import json

        with open(config_file, "r") as f:
            config_data = json.load(f)

        source_config = config_data["source_reputation"]
        return cls(
            trusted_domains=source_config["trusted_domains"],
            questionable_domains=source_config["questionable_domains"],
            banned_domains=source_config["banned_domains"],
            reputation_thresholds=source_config["reputation_thresholds"],
        )


class HTMLCleaner:
    """Advanced HTML content cleaner."""

    def __init__(self):
        # Common HTML artifacts and patterns to remove
        self.html_patterns = [
            # HTML tags
            re.compile(r"<[^>]+>", re.IGNORECASE),
            # HTML entities
            re.compile(r"&[a-zA-Z0-9#]+;"),
            # JavaScript code blocks
            re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL),
            # CSS style blocks
            re.compile(r"<style[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL),
            # HTML comments
            re.compile(r"<!--.*?-->", re.DOTALL),
            # Multiple whitespace/newlines
            re.compile(r"\s+", re.MULTILINE),
            # Common navigation text
            re.compile(
                r"(Skip to main content|Subscribe now|Sign up|Log in|Advertisement)",
                re.IGNORECASE,
            ),
            # Social media sharing text
            re.compile(
                r"(Share on Facebook|Tweet|Share on LinkedIn|Pin it)", re.IGNORECASE
            ),
            # Cookie and privacy notices
            re.compile(
                r"(This website uses cookies|We use cookies|Privacy Policy|Accept all cookies)",
                re.IGNORECASE,
            ),
        ]

        # Metadata patterns to remove
        self.metadata_patterns = [
            re.compile(r"Published:\s*\d+.*?ago", re.IGNORECASE),
            re.compile(r"Updated:\s*\d+.*?ago", re.IGNORECASE),
            re.compile(r"Reading time:\s*\d+\s*min", re.IGNORECASE),
            re.compile(r"\d+\s*comments?", re.IGNORECASE),
            re.compile(r"Share this article", re.IGNORECASE),
            re.compile(r"Follow us on", re.IGNORECASE),
        ]

    def clean_content(self, content: str) -> str:
        """
        Clean HTML content and remove artifacts.

        Args:
            content: Raw content string

        Returns:
            Cleaned content string
        """
        if not content:
            return ""

        cleaned = content

        # Remove script and style tags first (with content)
        cleaned = re.sub(
            r"<script[^>]*>.*?</script>", "", cleaned, flags=re.IGNORECASE | re.DOTALL
        )
        cleaned = re.sub(
            r"<style[^>]*>.*?</style>", "", cleaned, flags=re.IGNORECASE | re.DOTALL
        )
        cleaned = re.sub(
            r"<noscript[^>]*>.*?</noscript>",
            "",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )

        # Remove HTML comments
        cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)

        # Remove HTML tags
        cleaned = re.sub(r"<[^>]+>", "", cleaned)

        # Decode HTML entities
        cleaned = html.unescape(cleaned)

        # Remove metadata patterns
        for pattern in self.metadata_patterns:
            cleaned = pattern.sub("", cleaned)

        # Normalize unicode characters
        cleaned = unicodedata.normalize("NFKD", cleaned)

        # Clean up whitespace
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = cleaned.strip()

        return cleaned

    def clean_title(self, title: str) -> str:
        """
        Clean article title.

        Args:
            title: Raw title string

        Returns:
            Cleaned title string
        """
        if not title:
            return ""

        cleaned = html.unescape(title)
        cleaned = re.sub(r"<[^>]+>", "", cleaned)  # Remove HTML tags
        cleaned = re.sub(r"\s+", " ", cleaned)  # Normalize whitespace
        cleaned = cleaned.strip()

        # Remove common title suffixes
        cleaned = re.sub(
            r"\s*-\s*(Reuters|BBC|NPR|CNN).*$", "", cleaned, flags=re.IGNORECASE
        )

        return cleaned


class DuplicateDetector:
    """Enhanced duplicate detection with multiple strategies."""

    def __init__(self):
        self.url_cache = set()
        self.title_cache = set()
        self.content_hashes = set()
        self.fuzzy_title_cache = set()

    def is_duplicate(self, article: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if article is a duplicate.

        Args:
            article: Article dictionary

        Returns:
            Tuple of (is_duplicate, reason)
        """
        url = article.get("url", "")
        title = article.get("title", "")
        content = article.get("content", "")

        # Check URL duplicates
        if url and url in self.url_cache:
            return True, "duplicate_url"

        # Check exact title duplicates
        title_normalized = title.lower().strip()
        if title_normalized and title_normalized in self.title_cache:
            return True, "duplicate_title"

        # Check content hash duplicates
        if content:
            content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
            if content_hash in self.content_hashes:
                return True, "duplicate_content"
            self.content_hashes.add(content_hash)

        # Check fuzzy title duplicates (similar titles)
        if title:
            fuzzy_title = self._create_fuzzy_title(title)
            for cached_fuzzy in self.fuzzy_title_cache:
                similarity = SequenceMatcher(None, fuzzy_title, cached_fuzzy).ratio()
                if similarity >= 0.8:
                    return True, "similar_title"

            # Add to cache if not duplicate
            if fuzzy_title:
                self.fuzzy_title_cache.add(fuzzy_title)

        # Not a duplicate, add to caches
        if url:
            self.url_cache.add(url)
        if title_normalized:
            self.title_cache.add(title_normalized)

        return False, "unique"

    def _create_fuzzy_title(self, title: str) -> str:
        """Create fuzzy title for similarity matching."""
        if not title:
            return ""

        # Remove punctuation and normalize
        fuzzy = re.sub(r"[^\w\s]", "", title.lower())
        fuzzy = re.sub(r"\s+", " ", fuzzy).strip()

        # Remove common stop words
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "is",
            "are",
            "was",
            "were",
        }
        words = [w for w in fuzzy.split() if w not in stop_words]

        return " ".join(sorted(words))  # Sort words for better matching


class SourceReputationAnalyzer:
    """Analyzer for source credibility and reputation."""

    def __init__(self, config: Optional[SourceReputationConfig] = None):
        self.config = config or self._get_default_config()

    def _get_default_config(self) -> SourceReputationConfig:
        """Get default source reputation configuration."""
        return SourceReputationConfig(
            trusted_domains=[
                "reuters.com",
                "ap.org",
                "bbc.com",
                "npr.org",
                "pbs.org",
                "economist.com",
                "wsj.com",
                "ft.com",
                "bloomberg.com",
                "axios.com",
                "politico.com",
            ],
            questionable_domains=[
                "dailymail.co.uk",
                "nypost.com",
                "foxnews.com",
                "breitbart.com",
                "infowars.com",
                "naturalnews.com",
            ],
            banned_domains=["fakenews.com", "clickbait.com", "spam.com"],
            reputation_thresholds={
                "trusted": 0.9,
                "reliable": 0.7,
                "questionable": 0.4,
                "unreliable": 0.2,
            },
        )

    def analyze_source(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze source reputation and credibility.

        Args:
            article: Article dictionary

        Returns:
            Source analysis results
        """
        url = article.get("url", "")
        source = article.get("source", "")

        if not url:
            return {
                "reputation_score": 0.5,
                "credibility_level": "unknown",
                "flags": ["missing_url"],
                "domain": None,
            }

        try:
            domain = urlparse(url).netloc.lower()
        except BaseException:
            domain = ""

        reputation_score = self._calculate_reputation_score(domain, source)
        credibility_level = self._get_credibility_level(reputation_score)
        flags = self._get_reputation_flags(domain, article)

        return {
            "reputation_score": reputation_score,
            "credibility_level": credibility_level,
            "flags": flags,
            "domain": domain,
        }

    def _calculate_reputation_score(self, domain: str, source: str) -> float:
        """Calculate reputation score for domain/source."""
        score = 0.5  # Default neutral score

        # Check trusted domains
        for trusted in self.config.trusted_domains:
            if trusted in domain:
                score = 0.95
                break

        # Check questionable domains
        for questionable in self.config.questionable_domains:
            if questionable in domain:
                score = (
                    0.45  # Changed from 0.3 to 0.45 to be above questionable threshold
                )
                break

        # Check banned domains
        for banned in self.config.banned_domains:
            if banned in domain:
                score = 0.1
                break

        # Adjust based on domain characteristics
        if ".edu" in domain or ".gov" in domain:
            score = min(score + 0.2, 1.0)
        elif ".org" in domain:
            score = min(score + 0.1, 1.0)

        return score

    def _get_credibility_level(self, score: float) -> str:
        """Get credibility level from score."""
        thresholds = self.config.reputation_thresholds

        if score >= thresholds["trusted"]:
            return "trusted"
        elif score >= thresholds["reliable"]:
            return "reliable"
        elif score >= thresholds["questionable"]:
            return "questionable"
        else:
            return "unreliable"

    def _get_reputation_flags(self, domain: str, article: Dict[str, Any]) -> List[str]:
        """Get reputation warning flags."""
        flags = []

        # Check for suspicious patterns
        title = article.get("title", "").lower()
        content = article.get("content", "").lower()

        # Clickbait indicators
        clickbait_patterns = [
            r"you won\'t believe",
            r"shocking truth",
            r"doctors hate",
            r"one weird trick",
            r"amazing secret",
            r"\d+ reasons why",
            r"this will blow your mind",
        ]

        for pattern in clickbait_patterns:
            if re.search(pattern, title):
                flags.append("clickbait_title")
                break

        # Sensationalism indicators
        if re.search(r"[A-Z]{3,}", title):  # Excessive caps
            flags.append("excessive_caps")

        if title.count("!") > 2:
            flags.append("excessive_exclamation")

        # Content quality indicators
        if content and len(content) < 200:
            flags.append("thin_content")

        # Domain reputation flags
        for banned in self.config.banned_domains:
            if banned in domain:
                flags.append("banned_domain")

        for questionable in self.config.questionable_domains:
            if questionable in domain:
                flags.append("questionable_source")

        return flags


class ContentValidator:
    """Validator for article content quality and consistency."""

    def __init__(self):
        self.min_title_length = 10
        self.max_title_length = 200
        self.min_content_length = 100
        self.max_content_length = 50000
        self.min_word_count = 20

    def validate_content(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate article content quality.

        Args:
            article: Article dictionary

        Returns:
            Validation results
        """
        issues = []
        warnings = []
        score = 100.0

        title = article.get("title", "")
        content = article.get("content", "")
        url = article.get("url", "")
        published_date = article.get("published_date", "")

        # Validate title
        title_result = self._validate_title(title)
        score += title_result["score_adjustment"]
        issues.extend(title_result["issues"])
        warnings.extend(title_result["warnings"])

        # Validate content
        content_result = self._validate_content_quality(content)
        score += content_result["score_adjustment"]
        issues.extend(content_result["issues"])
        warnings.extend(content_result["warnings"])

        # Validate URL
        url_result = self._validate_url(url)
        score += url_result["score_adjustment"]
        issues.extend(url_result["issues"])
        warnings.extend(url_result["warnings"])

        # Validate date
        date_result = self._validate_date(published_date)
        score += date_result["score_adjustment"]
        issues.extend(date_result["issues"])
        warnings.extend(date_result["warnings"])

        return {
            "validation_score": max(0, min(100, score)),
            "issues": issues,
            "warnings": warnings,
            "is_valid": score >= 50,  # Minimum threshold
            "quality_metrics": {
                "title_length": len(title),
                "content_length": len(content),
                "word_count": len(content.split()) if content else 0,
                "reading_time": max(1, len(content.split()) // 200) if content else 0,
            },
        }

    def _validate_title(self, title: str) -> Dict[str, Any]:
        """Validate article title."""
        issues = []
        warnings = []
        score_adjustment = 0

        if not title:
            issues.append("missing_title")
            score_adjustment -= 25
        else:
            title_len = len(title)

            if title_len < self.min_title_length:
                issues.append("title_too_short")
                score_adjustment -= 15
            elif title_len > self.max_title_length:
                warnings.append("title_very_long")
                score_adjustment -= 5

            # Check for title quality
            if title.isupper():
                warnings.append("title_all_caps")
                score_adjustment -= 5

            if title.count("?") > 3:
                warnings.append("excessive_question_marks")
                score_adjustment -= 5

        return {
            "score_adjustment": score_adjustment,
            "issues": issues,
            "warnings": warnings,
        }

    def _validate_content_quality(self, content: str) -> Dict[str, Any]:
        """Validate content quality."""
        issues = []
        warnings = []
        score_adjustment = 0

        if not content:
            issues.append("missing_content")
            score_adjustment -= 30
        else:
            content_len = len(content)
            word_count = len(content.split())

            if content_len < self.min_content_length:
                issues.append("content_too_short")
                score_adjustment -= 20
            elif content_len < 200:  # Add warning for short content
                warnings.append("short_content")
                score_adjustment -= 5
            elif content_len > self.max_content_length:
                warnings.append("content_very_long")
                score_adjustment -= 5

            if word_count < self.min_word_count:
                issues.append("insufficient_word_count")
                score_adjustment -= 15

            # Check content quality indicators
            if content.count("\n") / len(content) > 0.1:
                warnings.append("excessive_line_breaks")
                score_adjustment -= 5

            # Check for placeholder content
            placeholder_patterns = [
                "lorem ipsum",
                "placeholder",
                "coming soon",
                "under construction",
                "page not found",
            ]

            for pattern in placeholder_patterns:
                if pattern in content.lower():
                    issues.append("placeholder_content")
                    score_adjustment -= 20
                    break

        return {
            "score_adjustment": score_adjustment,
            "issues": issues,
            "warnings": warnings,
        }

    def _validate_url(self, url: str) -> Dict[str, Any]:
        """Validate URL format and accessibility."""
        issues = []
        warnings = []
        score_adjustment = 0

        if not url:
            issues.append("missing_url")
            score_adjustment -= 20
        else:
            try:
                parsed = urlparse(url)
                if not parsed.scheme:
                    issues.append("invalid_url_scheme")
                    score_adjustment -= 10
                elif parsed.scheme not in ["http", "https"]:
                    warnings.append("unusual_url_scheme")
                    score_adjustment -= 5

                if not parsed.netloc:
                    issues.append("invalid_url_domain")
                    score_adjustment -= 10

                # Check for shortened URLs
                short_domains = ["bit.ly", "tinyurl.com", "goo.gl", "t.co"]
                if any(domain in parsed.netloc for domain in short_domains):
                    warnings.append("shortened_url")
                    score_adjustment -= 5

            except Exception:
                issues.append("malformed_url")
                score_adjustment -= 15

        return {
            "score_adjustment": score_adjustment,
            "issues": issues,
            "warnings": warnings,
        }

    def _validate_date(self, published_date: str) -> Dict[str, Any]:
        """Validate publication date."""
        issues = []
        warnings = []
        score_adjustment = 0

        if not published_date:
            warnings.append("missing_publication_date")
            score_adjustment -= 5
        else:
            try:
                # Try to parse the date
                if isinstance(published_date, str):
                    # Handle ISO format and common formats
                    from dateutil import parser

                    parsed_date = parser.parse(published_date)
                else:
                    parsed_date = published_date

                now = datetime.now()

                # Check if date is in the future
                if parsed_date > now:
                    issues.append("future_publication_date")
                    score_adjustment -= 10

                # Check if article is very old
                days_old = (now - parsed_date).days
                if days_old > 365 * 5:  # 5 years
                    warnings.append("very_old_article")
                    score_adjustment -= 5
                elif days_old > 30:  # 30 days
                    warnings.append("old_article")

            except Exception:
                issues.append("invalid_date_format")
                score_adjustment -= 10

        return {
            "score_adjustment": score_adjustment,
            "issues": issues,
            "warnings": warnings,
        }


class DataValidationPipeline:
    """Main data validation pipeline orchestrating all validation components."""

    def __init__(self, config: Optional[SourceReputationConfig] = None):
        self.html_cleaner = HTMLCleaner()
        self.duplicate_detector = DuplicateDetector()
        self.source_analyzer = SourceReputationAnalyzer(config)
        self.content_validator = ContentValidator()

        # Statistics tracking
        self.processed_count = 0
        self.rejected_count = 0
        self.warnings_count = 0

        logger.info("Data validation pipeline initialized")

    def process_article(self, article: Dict[str, Any]) -> Optional[ValidationResult]:
        """
        Process a single article through the validation pipeline.

        Args:
            article: Raw article dictionary

        Returns:
            ValidationResult if article passes validation, None if rejected
        """
        # Handle edge cases
        if not article or not isinstance(article, dict):
            logger.warning("Invalid article input - not a dictionary")
            return None

        self.processed_count += 1

        try:
            # Step 1: Clean HTML and remove artifacts
            cleaned_article = self._clean_article(article)

            # Step 2: Check for duplicates
            is_duplicate, duplicate_reason = self.duplicate_detector.is_duplicate(
                cleaned_article
            )
            if is_duplicate:
                logger.info(
                    f"Article rejected - {duplicate_reason}: {cleaned_article.get('url', 'Unknown URL')}"
                )
                self.rejected_count += 1
                return None

            # Step 3: Validate content quality
            content_validation = self.content_validator.validate_content(
                cleaned_article
            )

            # Step 4: Analyze source reputation
            source_analysis = self.source_analyzer.analyze_source(cleaned_article)

            # Step 5: Calculate overall validation score
            overall_score = self._calculate_overall_score(
                content_validation, source_analysis
            )

            # Step 6: Determine if article passes validation
            all_issues = content_validation["issues"] + source_analysis["flags"]
            all_warnings = content_validation["warnings"]

            # Check for critical issues that cause automatic rejection
            critical_issues = ["missing_title", "missing_content", "banned_domain"]
            has_critical_issues = any(issue in all_issues for issue in critical_issues)

            if has_critical_issues or overall_score < 50:
                logger.info(
                    f"Article failed validation (score: {
                        overall_score:.1f}): {
                        cleaned_article.get(
                            'url', 'Unknown URL')}"
                )
                self.rejected_count += 1
                return None

            # Count warnings
            if all_warnings:
                self.warnings_count += 1

            # Prepare cleaned data with additional metadata
            cleaned_data = cleaned_article.copy()
            cleaned_data.update(
                {
                    "validation_score": overall_score,
                    "content_quality": self._get_content_quality_rating(overall_score),
                    "source_credibility": source_analysis["credibility_level"],
                    "validation_flags": all_issues,
                    "word_count": len(cleaned_article.get("content", "").split()),
                    "content_length": len(cleaned_article.get("content", "")),
                    "validated_at": datetime.now().isoformat(),
                }
            )

            return ValidationResult(
                score=overall_score,
                is_valid=True,
                issues=all_issues,
                warnings=all_warnings,
                cleaned_data=cleaned_data,
            )

        except Exception as e:
            logger.error(f"Error processing article: {str(e)}")
            self.rejected_count += 1
            return None

    def _clean_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """Clean article content and metadata."""
        cleaned = article.copy()

        # Clean title and content
        if "title" in cleaned:
            cleaned["title"] = self.html_cleaner.clean_title(cleaned["title"])

        if "content" in cleaned:
            cleaned["content"] = self.html_cleaner.clean_content(cleaned["content"])

        # Extract source from URL if not provided
        if "source" not in cleaned or not cleaned["source"]:
            url = cleaned.get("url", "")
            if url:
                try:
                    domain = urlparse(url).netloc.lower()
                    cleaned["source"] = domain
                except BaseException:
                    cleaned["source"] = "unknown"

        return cleaned

    def _calculate_overall_score(
        self, content_validation: Dict[str, Any], source_analysis: Dict[str, Any]
    ) -> float:
        """Calculate overall validation score from components."""
        content_score = content_validation["validation_score"]
        reputation_score = source_analysis["reputation_score"] * 100

        # Weighted average: 70% content quality, 30% source reputation
        overall_score = (content_score * 0.7) + (reputation_score * 0.3)

        return round(overall_score, 1)

    def _get_content_quality_rating(self, score: float) -> str:
        """Get content quality rating from score."""
        if score >= 80:
            return "high"
        elif score >= 60:
            return "medium"
        else:
            return "low"

    def get_statistics(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        accepted_count = self.processed_count - self.rejected_count

        return {
            "processed_count": self.processed_count,
            "accepted_count": accepted_count,
            "rejected_count": self.rejected_count,
            "warnings_count": self.warnings_count,
            "acceptance_rate": (
                (accepted_count / self.processed_count * 100)
                if self.processed_count > 0
                else 0
            ),
            "rejection_rate": (
                (self.rejected_count / self.processed_count * 100)
                if self.processed_count > 0
                else 0
            ),
        }

    def reset_statistics(self):
        """Reset pipeline statistics."""
        self.processed_count = 0
        self.rejected_count = 0
        self.warnings_count = 0
        logger.info("Pipeline statistics reset")
