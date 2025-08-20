"""
Enhanced Scrapy Pipelines integrating the comprehensive data validation system.

This module extends the existing Scrapy pipelines with the new data validation
pipeline to implement Issue #21 requirements within the scraping workflow.
"""

import logging
from datetime import datetime
from typing import Any, Dict

from scrapy import Item
from scrapy.exceptions import DropItem

from src.database.data_validation_pipeline import (
    DataValidationPipeline,
    SourceReputationConfig,
)

logger = logging.getLogger(__name__)


class EnhancedValidationPipeline:
    """
    Enhanced Scrapy pipeline with comprehensive data validation.

    Integrates the DataValidationPipeline into Scrapy's processing workflow
    to ensure only high-quality, validated articles are stored.
    """

    def __init__(self, settings=None):
        """Initialize the enhanced validation pipeline."""
        # Configure source reputation based on settings
        config = None
        if settings:
            trusted_domains = settings.get("TRUSTED_DOMAINS", [])
            questionable_domains = settings.get("QUESTIONABLE_DOMAINS", [])
            banned_domains = settings.get("BANNED_DOMAINS", [])

            if any([trusted_domains, questionable_domains, banned_domains]):
                config = SourceReputationConfig(
                    trusted_domains=trusted_domains,
                    questionable_domains=questionable_domains,
                    banned_domains=banned_domains,
                    reputation_thresholds={
                        "trusted": 0.9,
                        "reliable": 0.7,
                        "questionable": 0.4,
                        "unreliable": 0.2,
                    },
                )

        self.validation_pipeline = DataValidationPipeline(config)
        self.stats_logged = False

    @classmethod
    def from_crawler(cls, crawler):
        """Create pipeline instance from crawler."""
        return cls(settings=crawler.settings)

    def process_item(self, item: Item, spider) -> Item:
        """
        Process item through enhanced validation pipeline.

        Args:
            item: Scraped item
            spider: Spider instance

        Returns:
            Validated and enhanced item

        Raises:
            DropItem: If item fails validation
        """
        # Convert item to dictionary
        article_dict = dict(item)

        # Process through validation pipeline
        result = self.validation_pipeline.process_article(article_dict)

        if result is None:
            # Article was rejected by validation pipeline
            spider.logger.info(
                f"Article dropped by validation pipeline: {
                    article_dict.get(
                        'url', 'Unknown URL')}"
            )
            raise DropItem("Article failed validation pipeline")

        # Update item with validated and enhanced data
        for key, value in result.cleaned_data.items():
            item[key] = value

        # Add validation metadata
        item["validation_result"] = {
            "score": result.score,
            "is_valid": result.is_valid,
            "issues": result.issues,
            "warnings": result.warnings,
        }

        # Log warnings if any
        if result.warnings:
            spider.logger.warning(
                f"Article validation warnings for {
                    item.get(
                        'url', 'Unknown URL')}: {
                    result.warnings}"
            )

        # Log quality info
        quality = result.cleaned_data.get("content_quality", "unknown")
        spider.logger.debug(
            "Article validated - Quality: {0}, Score: {1}".format(quality, result.score)
        )

        return item

    def close_spider(self, spider):
        """Log final statistics when spider closes."""
        stats = self.validation_pipeline.get_statistics()

        spider.logger.info(
            """
=== Data Validation Pipeline Statistics ===
Processed: {stats['processed_count']} articles
Accepted: {stats['accepted_count']} articles ({stats['acceptance_rate']:.1f}%)
Rejected: {stats['rejected_count']} articles ({stats['rejection_rate']:.1f}%)
Warnings: {stats['warnings_count']} articles
==========================================
    """
        )

        # Store stats in spider stats
        spider.crawler.stats.set_value(
            "validation_processed_count", stats["processed_count"]
        )
        spider.crawler.stats.set_value(
            "validation_accepted_count", stats["accepted_count"]
        )
        spider.crawler.stats.set_value(
            "validation_rejected_count", stats["rejected_count"]
        )
        spider.crawler.stats.set_value(
            "validation_acceptance_rate", stats["acceptance_rate"]
        )


class QualityFilterPipeline:
    """
    Pipeline to filter articles by minimum quality thresholds.

    Provides additional filtering based on validation scores and specific criteria.
    """

    def __init__(self, min_score: float = 60.0, min_content_length: int = 200):
        """
        Initialize quality filter pipeline.

        Args:
            min_score: Minimum validation score required
            min_content_length: Minimum content length required
        """
        self.min_score = min_score
        self.min_content_length = min_content_length
        self.filtered_count = 0

    @classmethod
    def from_crawler(cls, crawler):
        """Create pipeline instance from crawler."""
        settings = crawler.settings
        min_score = settings.getfloat("QUALITY_MIN_SCORE", 60.0)
        min_content_length = settings.getint("QUALITY_MIN_CONTENT_LENGTH", 200)

        return cls(min_score=min_score, min_content_length=min_content_length)

    def process_item(self, item: Item, spider) -> Item:
        """
        Filter item based on quality thresholds.

        Args:
            item: Scraped item
            spider: Spider instance

        Returns:
            Item if it passes quality filters

        Raises:
            DropItem: If item doesn't meet quality thresholds
        """
        # Check validation score
        validation_score = item.get("validation_score", 0)
        if validation_score < self.min_score:
            self.filtered_count += 1
            spider.logger.info(
                f"Article filtered - low score ({
                    validation_score}): {
                    item.get(
                        'url',
                        'Unknown URL')}"
            )
            raise DropItem(
                "Article validation score ({0:.1f}) below threshold ({1})".format(
                    validation_score, self.min_score
                )
            )

        # Check content length
        content_length = item.get("content_length", 0)
        if content_length < self.min_content_length:
            self.filtered_count += 1
            spider.logger.info(
                f"Article filtered - short content ({content_length}): {item.get('url', 'Unknown URL')}"
            )
            raise DropItem(
                "Article content length ({0}) below threshold ({1})".format(
                    content_length, self.min_content_length
                )
            )

        # Check for critical validation flags
        validation_result = item.get("validation_result", {})
        issues = validation_result.get("issues", [])

        critical_issues = [
            "missing_title",
            "missing_content",
            "banned_domain",
            "placeholder_content",
        ]
        for issue in critical_issues:
            if issue in issues:
                self.filtered_count += 1
                spider.logger.warning(
                    f"Article filtered - critical issue ({issue}): {item.get('url', 'Unknown URL')}"
                )
                raise DropItem(
                    "Article has critical validation issue: {0}".format(issue)
                )

        return item

    def close_spider(self, spider):
        """Log filtering statistics when spider closes."""
        spider.logger.info(
            "Quality filter removed {0} low-quality articles".format(
                self.filtered_count
            )
        )
        spider.crawler.stats.set_value("quality_filtered_count", self.filtered_count)


class SourceCredibilityPipeline:
    """
    Pipeline to handle source credibility and reputation scoring.

    Adds additional processing based on source reputation analysis.
    """

    def __init__(self, block_unreliable: bool = False):
        """
        Initialize source credibility pipeline.

        Args:
            block_unreliable: Whether to block unreliable sources entirely
        """
        self.block_unreliable = block_unreliable
        self.blocked_count = 0
        self.credibility_stats = {
            "trusted": 0,
            "reliable": 0,
            "questionable": 0,
            "unreliable": 0,
            "unknown": 0,
        }

    @classmethod
    def from_crawler(cls, crawler):
        """Create pipeline instance from crawler."""
        settings = crawler.settings
        block_unreliable = settings.getbool("BLOCK_UNRELIABLE_SOURCES", False)

        return cls(block_unreliable=block_unreliable)

    def process_item(self, item: Item, spider) -> Item:
        """
        Process item based on source credibility.

        Args:
            item: Scraped item
            spider: Spider instance

        Returns:
            Item with credibility processing

        Raises:
            DropItem: If source is unreliable and blocking is enabled
        """
        credibility = item.get("source_credibility", "unknown")
        self.credibility_stats[credibility] = (
            self.credibility_stats.get(credibility, 0) + 1
        )

        # Block unreliable sources if configured
        if self.block_unreliable and credibility == "unreliable":
            self.blocked_count += 1
            spider.logger.warning(
                f"Article blocked - unreliable source: {item.get('url', 'Unknown URL')}"
            )
            raise DropItem("Article from unreliable source blocked")

        # Add credibility warning to questionable sources
        if credibility in ["questionable", "unreliable"]:
            validation_result = item.get("validation_result", {})
            warnings = validation_result.get("warnings", [])
            warnings.append("source_credibility_{0}".format(credibility))
            validation_result["warnings"] = warnings
            item["validation_result"] = validation_result

        # Adjust priority based on credibility
        if credibility == "trusted":
            item["priority"] = item.get("priority", 0) + 10
        elif credibility == "reliable":
            item["priority"] = item.get("priority", 0) + 5
        elif credibility == "questionable":
            item["priority"] = item.get("priority", 0) - 5
        elif credibility == "unreliable":
            item["priority"] = item.get("priority", 0) - 10

        return item

    def close_spider(self, spider):
        """Log credibility statistics when spider closes."""
        total = sum(self.credibility_stats.values())

        spider.logger.info(
            """
=== Source Credibility Statistics ===
Total articles: {total}
Trusted: {self.credibility_stats['trusted']} ({self.credibility_stats['trusted'] / total * 100:.1f}%)
Reliable: {self.credibility_stats['reliable']} ({self.credibility_stats['reliable'] / total * 100:.1f}%)
Questionable: {self.credibility_stats['questionable']} ({self.credibility_stats['questionable'] / total * 100:.1f}%)
Unreliable: {self.credibility_stats['unreliable']} ({self.credibility_stats['unreliable'] / total * 100:.1f}%)
Unknown: {self.credibility_stats['unknown']} ({self.credibility_stats['unknown'] / total * 100:.1f}%)
Blocked unreliable: {self.blocked_count}
====================================
"""
        )

        # Store stats in spider stats
        for level, count in self.credibility_stats.items():
            spider.crawler.stats.set_value("credibility_{0}_count".format(level), count)
        spider.crawler.stats.set_value("credibility_blocked_count", self.blocked_count)


class DuplicateFilterPipeline:
    """
    Enhanced duplicate filter pipeline with multiple detection strategies.

    Replaces the basic duplicate filter with advanced detection capabilities.
    """

    def __init__(self):
        """Initialize enhanced duplicate filter."""
        from src.database.data_validation_pipeline import DuplicateDetector

        self.duplicate_detector = DuplicateDetector()
        self.duplicate_count = 0
        self.duplicate_reasons = {
            "duplicate_url": 0,
            "duplicate_title": 0,
            "duplicate_content": 0,
            "similar_title": 0,
        }

    def process_item(self, item: Item, spider) -> Item:
        """
        Check for duplicates using enhanced detection.

        Args:
            item: Scraped item
            spider: Spider instance

        Returns:
            Item if unique

        Raises:
            DropItem: If item is a duplicate
        """
        article_dict = dict(item)
        is_duplicate, reason = self.duplicate_detector.is_duplicate(article_dict)

        if is_duplicate:
            self.duplicate_count += 1
            self.duplicate_reasons[reason] = self.duplicate_reasons.get(reason, 0) + 1

            spider.logger.info(
                f"Duplicate article detected ({reason}): {
                    item.get(
                        'url', 'Unknown URL')}"
            )
            raise DropItem("Duplicate article: {0}".format(reason))

        # Mark as unique
        item["duplicate_check"] = "unique"
        return item

    def close_spider(self, spider):
        """Log duplicate detection statistics when spider closes."""
        spider.logger.info(
            """
=== Duplicate Detection Statistics ===
Total duplicates found: {self.duplicate_count}
By URL: {self.duplicate_reasons.get('duplicate_url', 0)}
By title: {self.duplicate_reasons.get('duplicate_title', 0)}
By content: {self.duplicate_reasons.get('duplicate_content', 0)}
Similar titles: {self.duplicate_reasons.get('similar_title', 0)}
=====================================
"""
        )

        spider.crawler.stats.set_value("duplicates_total_count", self.duplicate_count)
        for reason, count in self.duplicate_reasons.items():
            spider.crawler.stats.set_value("duplicates_{0}_count".format(reason), count)


class ValidationReportPipeline:
    """
    Pipeline to generate validation reports and metrics.

    Collects validation data and generates comprehensive reports.
    """

    def __init__(self, report_file: str = "data/validation_report.json"):
        """
        Initialize validation report pipeline.

        Args:
            report_file: Path to save validation report
        """
        self.report_file = report_file
        self.articles = []

    @classmethod
    def from_crawler(cls, crawler):
        """Create pipeline instance from crawler."""
        settings = crawler.settings
        report_file = settings.get(
            "VALIDATION_REPORT_FILE", "data/validation_report.json"
        )

        return cls(report_file=report_file)

    def process_item(self, item: Item, spider) -> Item:
        """
        Collect validation data for reporting.

        Args:
            item: Scraped item
            spider: Spider instance

        Returns:
            Unchanged item
        """
        # Collect validation metrics
        validation_data = {
            "url": item.get("url"),
            "source": item.get("source"),
            "validation_score": item.get("validation_score", 0),
            "content_quality": item.get("content_quality"),
            "source_credibility": item.get("source_credibility"),
            "content_length": item.get("content_length", 0),
            "word_count": item.get("word_count", 0),
            "validation_flags": item.get("validation_flags", []),
            "validation_result": item.get("validation_result", {}),
            "validated_at": item.get("validated_at"),
        }

        self.articles.append(validation_data)
        return item

    def close_spider(self, spider):
        """Generate and save validation report when spider closes."""
        if not self.articles:
            spider.logger.warning("No articles to include in validation report")
            return

        # Generate report
        report = self._generate_report(spider)

        # Save report
        import json
        import os

        os.makedirs(os.path.dirname(self.report_file), exist_ok=True)

        with open(self.report_file, "w") as f:
            json.dump(report, f, indent=2, default=str)

        spider.logger.info("Validation report saved to: {0}".format(self.report_file))

    def _generate_report(self, spider) -> Dict[str, Any]:
        """Generate comprehensive validation report."""
        total_articles = len(self.articles)

        if total_articles == 0:
            return {"error": "No articles processed"}

        # Calculate summary statistics
        scores = [a["validation_score"] for a in self.articles if a["validation_score"]]
        avg_score = sum(scores) / len(scores) if scores else 0

        quality_distribution = {}
        credibility_distribution = {}
        source_distribution = {}

        for article in self.articles:
            # Quality distribution
            quality = article.get("content_quality", "unknown")
            quality_distribution[quality] = quality_distribution.get(quality, 0) + 1

            # Credibility distribution
            credibility = article.get("source_credibility", "unknown")
            credibility_distribution[credibility] = (
                credibility_distribution.get(credibility, 0) + 1
            )

            # Source distribution
            source = article.get("source", "unknown")
            source_distribution[source] = source_distribution.get(source, 0) + 1

        # Find best and worst performing sources
        source_scores = {}
        for article in self.articles:
            source = article.get("source", "unknown")
            score = article.get("validation_score", 0)
            if source not in source_scores:
                source_scores[source] = []
            source_scores[source].append(score)

        source_avg_scores = {
            source: sum(scores) / len(scores)
            for source, scores in source_scores.items()
            if scores
        }

        best_source = (
            max(source_avg_scores.items(), key=lambda x: x[1])
            if source_avg_scores
            else ("unknown", 0)
        )
        worst_source = (
            min(source_avg_scores.items(), key=lambda x: x[1])
            if source_avg_scores
            else ("unknown", 0)
        )

        return {
            "report_metadata": {
                "generated_at": datetime.now().isoformat(),
                "spider_name": spider.name,
                "total_articles_processed": total_articles,
            },
            "summary_statistics": {
                "average_validation_score": avg_score,
                "min_validation_score": min(scores) if scores else 0,
                "max_validation_score": max(scores) if scores else 0,
                "quality_distribution": quality_distribution,
                "credibility_distribution": credibility_distribution,
                "source_distribution": source_distribution,
            },
            "source_performance": {
                "best_performing_source": {
                    "name": best_source[0],
                    "average_score": best_source[1],
                },
                "worst_performing_source": {
                    "name": worst_source[0],
                    "average_score": worst_source[1],
                },
                "source_scores": source_avg_scores,
            },
            "detailed_articles": self.articles,
        }


# Configuration for enhanced pipelines
ENHANCED_PIPELINES = {
    # Duplicate detection (first to avoid processing duplicates)
    "src.scraper.enhanced_pipelines.DuplicateFilterPipeline": 100,
    # Data validation and cleaning
    "src.scraper.enhanced_pipelines.EnhancedValidationPipeline": 200,
    # Quality filtering
    "src.scraper.enhanced_pipelines.QualityFilterPipeline": 300,
    # Source credibility processing
    "src.scraper.enhanced_pipelines.SourceCredibilityPipeline": 400,
    # Report generation
    "src.scraper.enhanced_pipelines.ValidationReportPipeline": 800,
    # Final JSON output (existing)
    "src.scraper.pipelines.EnhancedJsonWriterPipeline": 900,
}
