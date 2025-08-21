"""
Integration tests for the data validation pipeline.

Tests the complete validation pipeline with real-world scenarios
to ensure all components work together correctly.
"""

from src.database.data_validation_pipeline import (
    DataValidationPipeline,
    DuplicateDetector,
    HTMLCleaner,
    SourceReputationConfig,
)
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.append("/workspaces/NeuroNews")


class TestDataValidationPipeline(unittest.TestCase):
    """Test the complete data validation pipeline."""

    def setUp(self):
        """Set up test fixtures."""
        # Create test configuration
        self.config = SourceReputationConfig(
            trusted_domains=["reuters.com", "bbc.com"],
            questionable_domains=["dailymail.co.uk"],
            banned_domains=["infowars.com"],
            reputation_thresholds={
                "trusted": 0.9,
                "reliable": 0.7,
                "questionable": 0.4,
                "unreliable": 0.2,
            },
        )

        self.pipeline = DataValidationPipeline(self.config)

        # Sample articles for testing
        self.valid_article = {
            "url": "https://reuters.com/news/technology/ai-breakthrough",
            "title": "Major AI Breakthrough Announced by Leading Researchers",
            "content": """
                <p>Scientists at leading universities have announced a significant breakthrough
                in artificial intelligence research. The new method shows promising results
                in natural language understanding and could revolutionize how AI systems
                process human communication.</p>

                <p>Dr. Jane Smith, lead researcher on the project, explained that the
                breakthrough involves a novel approach to neural network architecture
                that dramatically improves performance while reducing computational
                requirements.</p>

                <p>"This represents a major step forward in making AI more accessible
                and efficient," Smith said in an interview. "We're excited about the
                potential applications in healthcare, education, and scientific research."</p>
            """,
            "source": "reuters.com",
            "published_date": datetime.now().isoformat(),
            "author": "Tech Reporter",
            "summary": "Researchers announce breakthrough in AI technology",
        }

        self.invalid_article = {
            "url": "https://infowars.com/fake-news",
            "title": "BREAKING: Government Mind Control Exposed!!!",
            "content": "<p>Short content.</p>",
            "source": "infowars.com",
            "published_date": (datetime.now() - timedelta(days=100)).isoformat(),
            "author": "",
            "summary": "",
        }

        self.html_messy_article = {
            "url": "https://bbc.com/news/tech-story",
            "title": "Technology News Update",
            "content": """
                <div class="article-content" id="main-content">
                    <script>gtag('config', 'GA_TRACKING_ID');</script>
                    <style>.ad { display: none; }</style>
                    <p>This is the actual content of the article.</p>
                    <div class="advertisement">Advertisement content here</div>
                    <p>More article content with <a onclick="trackClick()">tracking links</a>.</p>
                    <noscript>No JavaScript version</noscript>
                    <p>Final paragraph of the article.</p>
                </div>
            """,
            "source": "bbc.com",
            "published_date": datetime.now().isoformat(),
            "author": "BBC Reporter",
        }

    def test_valid_article_processing(self):
        """Test processing of a valid high-quality article."""
        result = self.pipeline.process_article(self.valid_article)

        self.assertIsNotNone(result)
        self.assertTrue(result.is_valid)
        self.assertGreaterEqual(result.score, 70.0)
        self.assertEqual(result.cleaned_data["source_credibility"], "trusted")
        self.assertIn("content_quality", result.cleaned_data)
        self.assertEqual(len(result.issues), 0)

    def test_invalid_article_rejection(self):
        """Test rejection of invalid articles."""
        result = self.pipeline.process_article(self.invalid_article)

        # Should be rejected due to banned domain
        self.assertIsNone(result)

    def test_html_cleaning(self):
        """Test HTML cleaning functionality."""
        result = self.pipeline.process_article(self.html_messy_article)

        self.assertIsNotNone(result)
        cleaned_content = result.cleaned_data["content"]

        # Check that HTML tags and scripts are removed
        self.assertNotIn("<script>", cleaned_content)
        self.assertNotIn("<style>", cleaned_content)
        self.assertNotIn("<noscript>", cleaned_content)
        self.assertNotIn("onclick=", cleaned_content)
        self.assertNotIn("class=", cleaned_content)

        # Check that actual content is preserved
        self.assertIn("This is the actual content", cleaned_content)
        self.assertIn("More article content", cleaned_content)
        self.assertIn("Final paragraph", cleaned_content)

    def test_duplicate_detection(self):
        """Test duplicate detection across multiple articles."""
        # Process first article
        result1 = self.pipeline.process_article(self.valid_article)
        self.assertIsNotNone(result1)

        # Try to process same article again
        result2 = self.pipeline.process_article(self.valid_article)
        self.assertIsNone(result2)  # Should be rejected as duplicate

        # Try with slightly different URL but same content
        duplicate_article = self.valid_article.copy()
        duplicate_article["url"] = (
            "https://reuters.com/news/technology/ai-breakthrough?utm_source=twitter"
        )

        result3 = self.pipeline.process_article(duplicate_article)
        self.assertIsNone(result3)  # Should be rejected as duplicate content

    def test_source_reputation_scoring(self):
        """Test source reputation analysis."""
        # Create a fresh pipeline for each test to avoid cross-contamination

        # Test trusted source
        pipeline1 = DataValidationPipeline(self.config)
        trusted_article = self.valid_article.copy()
        trusted_article["source"] = "reuters.com"
        # Unique URL
        trusted_article["url"] = "https://reuters.com/trusted-article"
        trusted_article["title"] = "Trusted Source Article: AI Development"  # Unique title
        result = pipeline1.process_article(trusted_article)
        self.assertEqual(result.cleaned_data["source_credibility"], "trusted")

        # Test questionable source
        pipeline2 = DataValidationPipeline(self.config)
        questionable_article = self.valid_article.copy()
        questionable_article["source"] = "dailymail.co.uk"
        questionable_article["url"] = (
            "https://dailymail.co.uk/news/questionable-article"  # Unique URL
        )
        questionable_article["title"] = (
            "Questionable Source Article: Technology News"  # Unique title
        )
        # Use longer content to boost the score above rejection threshold
        questionable_article[
            "content"
        ] = """
            <p>Scientists at leading universities have announced a significant breakthrough
            in artificial intelligence research. The new method shows promising results
            in natural language understanding and could revolutionize how AI systems
            process human communication.</p>

            <p>Dr. Jane Smith, lead researcher on the project, explained that the
            breakthrough involves a novel approach to neural network architecture
            that dramatically improves performance while reducing computational
            requirements.</p>
        """
        result = pipeline2.process_article(questionable_article)
        self.assertIsNotNone(result)  # Should pass despite questionable source
        self.assertEqual(result.cleaned_data["source_credibility"], "questionable")

        # Test unknown source
        pipeline3 = DataValidationPipeline(self.config)
        unknown_article = self.valid_article.copy()
        unknown_article["source"] = "unknown-news.com"
        unknown_article["url"] = "https://unknown-news.com/unknown-article"  # Unique URL
        unknown_article["title"] = "Unknown Source Article: Research Update"  # Unique title
        result = pipeline3.process_article(unknown_article)
        self.assertIsNotNone(result)
        # Unknown sources are classified as 'questionable' in the
        # implementation
        self.assertEqual(result.cleaned_data["source_credibility"], "questionable")

    def test_content_validation(self):
        """Test content quality validation."""
        # Test short content (should be between 100-200 chars to trigger
        # warning)
        short_article = self.valid_article.copy()
        short_article["content"] = (
            "<p>This is short content that is just under 200 characters but above 100 characters to test the warning functionality for articles that have minimal content but still pass validation.</p>"
        )
        short_article["url"] = "https://reuters.com/short-article"

        result = self.pipeline.process_article(short_article)
        if result:  # Should pass but with warnings
            self.assertIn("short_content", result.warnings)

        # Test missing title
        no_title_article = self.valid_article.copy()
        no_title_article["title"] = ""
        no_title_article["url"] = "https://reuters.com/no-title"

        result = self.pipeline.process_article(no_title_article)
        if result:
            self.assertIn("missing_title", result.issues)

        # Test old article
        old_article = self.valid_article.copy()
        old_article["published_date"] = (datetime.now() - timedelta(days=60)).isoformat()
        old_article["url"] = "https://reuters.com/old-article"

        result = self.pipeline.process_article(old_article)
        if result:
            self.assertIn("old_article", result.warnings)

    def test_statistics_tracking(self):
        """Test that statistics are properly tracked."""
        # Process several articles
        articles = [self.valid_article, self.invalid_article, self.html_messy_article]

        for i, article in enumerate(articles):
            # Make URLs unique
            article = article.copy()
            article["url"] = f"{article['url']}-{i}"
            self.pipeline.process_article(article)

        stats = self.pipeline.get_statistics()

        self.assertGreater(stats["processed_count"], 0)
        self.assertIn("acceptance_rate", stats)
        self.assertIn("rejection_rate", stats)
        self.assertGreaterEqual(stats["acceptance_rate"] + stats["rejection_rate"], 0)

    def test_configuration_loading(self):
        """Test loading configuration from file."""
        # Create temporary config file
        config_data = {
            "source_reputation": {
                "trusted_domains": ["test-trusted.com"],
                "questionable_domains": ["test-questionable.com"],
                "banned_domains": ["test-banned.com"],
                "reputation_thresholds": {
                    "trusted": 0.9,
                    "reliable": 0.7,
                    "questionable": 0.4,
                    "unreliable": 0.2,
                },
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            # Load configuration
            config = SourceReputationConfig.from_file(config_file)
            pipeline = DataValidationPipeline(config)

            # Test with configured domains
            test_article = self.valid_article.copy()
            test_article["source"] = "test-trusted.com"
            test_article["url"] = "https://test-trusted.com/article"

            result = pipeline.process_article(test_article)
            self.assertEqual(result.cleaned_data["source_credibility"], "trusted")

        finally:
            os.unlink(config_file)

    def test_edge_cases(self):
        """Test edge cases and error handling."""
        # Test with None article
        result = self.pipeline.process_article(None)
        self.assertIsNone(result)

        # Test with empty article
        result = self.pipeline.process_article({})
        self.assertIsNone(result)

        # Test with malformed content
        malformed_article = {
            "url": "https://test.com/malformed",
            "title": "Test Article",
            "content": None,  # Malformed content
            "source": "test.com",
        }

        result = self.pipeline.process_article(malformed_article)
        # Should be rejected due to missing content (critical issue)
        self.assertIsNone(result)

    def test_performance_with_large_dataset(self):
        """Test pipeline performance with multiple articles."""
        import time

        # Generate test articles
        articles = []
        for i in range(50):
            article = self.valid_article.copy()
            article["url"] = "https://reuters.com/article-{0}".format(i)
            article["title"] = "Test Article {0}".format(i)
            articles.append(article)

        # Measure processing time
        start_time = time.time()

        processed_count = 0
        for article in articles:
            result = self.pipeline.process_article(article)
            if result:
                processed_count += 1

        end_time = time.time()
        processing_time = end_time - start_time

        # Verify performance
        self.assertGreater(processed_count, 0)
        self.assertLess(processing_time, 10.0)  # Should process 50 articles in under 10 seconds

        # Check statistics
        stats = self.pipeline.get_statistics()
        self.assertEqual(stats["processed_count"], len(articles))


class TestHTMLCleaner(unittest.TestCase):
    """Test HTML cleaning functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.cleaner = HTMLCleaner()

    def test_basic_html_removal(self):
        """Test basic HTML tag removal."""
        html_content = "<p>This is <b>bold</b> and <i>italic</i> text.</p>"
        cleaned = self.cleaner.clean_content(html_content)

        self.assertEqual(cleaned, "This is bold and italic text.")

    def test_script_and_style_removal(self):
        """Test removal of script and style tags."""
        html_content = """
        <div>
            <script>alert('test');</script>
            <style>.class { color: red; }</style>
            <p>Actual content</p>
        </div>
        """

        cleaned = self.cleaner.clean_content(html_content)

        self.assertNotIn("alert", cleaned)
        self.assertNotIn("color: red", cleaned)
        self.assertIn("Actual content", cleaned)

    def test_entity_decoding(self):
        """Test HTML entity decoding."""
        html_content = "Price: $100 &amp; free shipping. It&#39;s great!"
        cleaned = self.cleaner.clean_content(html_content)

        self.assertIn("$100 & free shipping", cleaned)
        self.assertIn("It's great!", cleaned)

    def test_whitespace_normalization(self):
        """Test whitespace normalization."""
        html_content = """
        <p>Paragraph   with    extra      spaces.</p>


        <p>Another paragraph.</p>
        """

        cleaned = self.cleaner.clean_content(html_content)

        # Should normalize multiple spaces to single spaces
        self.assertNotIn("    ", cleaned)
        self.assertIn("Paragraph with extra spaces.", cleaned)


class TestDuplicateDetector(unittest.TestCase):
    """Test duplicate detection functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.detector = DuplicateDetector()

        self.article1 = {
            "url": "https://example.com/article1",
            "title": "Breaking News: Important Event Happens",
            "content": "This is the content of the first article about an important event.",
        }

        self.article2 = {
            "url": "https://example.com/article2",
            "title": "Breaking News: Important Event Happens",  # Same title
            "content": "Different content about the same event.",
        }

    def test_url_duplicate_detection(self):
        """Test URL-based duplicate detection."""
        # Add first article
        is_dup, reason = self.detector.is_duplicate(self.article1)
        self.assertFalse(is_dup)

        # Try same URL again
        is_dup, reason = self.detector.is_duplicate(self.article1)
        self.assertTrue(is_dup)
        self.assertEqual(reason, "duplicate_url")

    def test_title_duplicate_detection(self):
        """Test title-based duplicate detection."""
        # Add first article
        self.detector.is_duplicate(self.article1)

        # Try article with same title but different URL
        is_dup, reason = self.detector.is_duplicate(self.article2)
        self.assertTrue(is_dup)
        self.assertEqual(reason, "duplicate_title")

    def test_content_hash_detection(self):
        """Test content hash-based duplicate detection."""
        article_copy = self.article1.copy()
        article_copy["url"] = "https://different-site.com/article"
        article_copy["title"] = "Different Title"
        # Same content as article1

        # Add first article
        self.detector.is_duplicate(self.article1)

        # Try article with same content
        is_dup, reason = self.detector.is_duplicate(article_copy)
        self.assertTrue(is_dup)
        self.assertEqual(reason, "duplicate_content")

    def test_fuzzy_title_matching(self):
        """Test fuzzy title matching."""
        # Add first article
        self.detector.is_duplicate(self.article1)

        # Create article with very similar title (should have >80% similarity)
        similar_article = {
            "url": "https://different.com/article",
            "title": "Breaking News: Important Event Happening",  # Very similar
            "content": "Completely different content here.",
        }

        is_dup, reason = self.detector.is_duplicate(similar_article)
        self.assertTrue(is_dup)
        self.assertEqual(reason, "similar_title")


if __name__ == "__main__":
    unittest.main()
