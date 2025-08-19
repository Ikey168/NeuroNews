"""
Enhanced async pipelines for processing scraped articles.
Provides high-performance processing with ThreadPoolExecutor and async I/O.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiofiles
import boto3
from botocore.exceptions import ClientError


class AsyncPipelineProcessor:
    """High-performance async pipeline processor."""

    def __init__(self, max_threads: int = 4):
        self.max_threads = max_threads
        self.thread_pool = ThreadPoolExecutor(max_workers=max_threads)
        self.processed_articles = []
        self.validation_stats = {"passed": 0, "failed": 0}
        self.duplicate_stats = {"unique": 0, "duplicates": 0}

        self.logger = logging.getLogger(__name__)

        # Initialize S3 client if configured
        self.s3_client = None
        if all(
            os.getenv(key) for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
        ):
            self.s3_client = boto3.client("s3")

    async def process_articles_async(
        self, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Process articles through async pipeline."""
        self.logger.info(
            f"🔄 Processing {len(articles)} articles through async pipeline"
        )

        # Create semaphore for controlled concurrency
        semaphore = asyncio.Semaphore(self.max_threads * 2)

        # Process articles concurrently
        tasks = []
        for article in articles:
            task = asyncio.create_task(self.process_single_article(semaphore, article))
            tasks.append(task)

        # Wait for all processing to complete
        processed_articles = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter successful results
        valid_articles = [
            article
            for article in processed_articles
            if isinstance(article, dict) and article is not None
        ]

        self.processed_articles = valid_articles

        self.logger.info(
            f"✅ Pipeline processing completed: {len(valid_articles)} valid articles"
        )
        self.logger.info(
            f"📊 Validation: {self.validation_stats['passed']} passed, {self.validation_stats['failed']} failed"
        )
        self.logger.info(
            f"🔍 Duplicates: {self.duplicate_stats['unique']} unique, {self.duplicate_stats['duplicates']} duplicates"
        )

        return valid_articles

    async def process_single_article(
        self, semaphore: asyncio.Semaphore, article: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Process a single article through the pipeline."""
        async with semaphore:
            try:
                # Validation pipeline
                if not await self.validate_article_async(article):
                    self.validation_stats["failed"] += 1
                    return None

                self.validation_stats["passed"] += 1

                # Duplicate detection pipeline
                if await self.check_duplicate_async(article):
                    self.duplicate_stats["duplicates"] += 1
                    return None

                self.duplicate_stats["unique"] += 1

                # Enhancement pipeline
                enhanced_article = await self.enhance_article_async(article)

                return enhanced_article

            except Exception as e:
                self.logger.error(
                    f"Error processing article {article.get('url', 'unknown')}: {e}"
                )
                return None

    async def validate_article_async(self, article: Dict[str, Any]) -> bool:
        """Async article validation (CPU-intensive task in thread pool)."""
        loop = asyncio.get_event_loop()

        return await loop.run_in_executor(
            self.thread_pool, self.validate_article_sync, article
        )

    def validate_article_sync(self, article: Dict[str, Any]) -> bool:
        """Synchronous validation logic (runs in thread pool)."""
        validation_score = 100

        # Check required fields
        required_fields = ["title", "url", "content", "source"]
        for field in required_fields:
            if not article.get(field):
                validation_score -= 25

        # Validate title length
        title = article.get("title", "")
        if len(title) < 10 or len(title) > 200:
            validation_score -= 10

        # Validate content length
        content = article.get("content", "")
        content_length = len(content)

        if content_length < 100:
            validation_score -= 20
        elif content_length > 20000:
            validation_score -= 5

        # Validate URL format
        url = article.get("url", "")
        try:
            parsed_url = urlparse(url)
            if not parsed_url.scheme or not parsed_url.netloc:
                validation_score -= 15
        except:
            validation_score -= 15

        # Check for spam indicators
        spam_keywords = ["click here", "buy now", "limited time", "act fast"]
        title_lower = title.lower()
        content_lower = content.lower()

        for keyword in spam_keywords:
            if keyword in title_lower or keyword in content_lower:
                validation_score -= 10

        # Update article with validation info
        article["validation_score"] = max(0, validation_score)
        article["content_length"] = content_length
        article["word_count"] = len(content.split())
        article["reading_time"] = max(1, article["word_count"] // 200)

        # Quality classification
        if validation_score >= 80:
            article["content_quality"] = "high"
        elif validation_score >= 60:
            article["content_quality"] = "medium"
        else:
            article["content_quality"] = "low"

        return validation_score >= 50

    async def check_duplicate_async(self, article: Dict[str, Any]) -> bool:
        """Async duplicate detection."""
        loop = asyncio.get_event_loop()

        return await loop.run_in_executor(
            self.thread_pool, self.check_duplicate_sync, article
        )

    def check_duplicate_sync(self, article: Dict[str, Any]) -> bool:
        """Synchronous duplicate detection (runs in thread pool)."""
        url = article.get("url", "")
        title = article.get("title", "")
        content = article.get("content", "")

        # URL-based deduplication
        url_hash = hashlib.md5(url.encode()).hexdigest()

        # Content-based deduplication (first 500 chars)
        content_sample = content[:500]
        content_hash = hashlib.md5(content_sample.encode()).hexdigest()

        # Title similarity check
        title_words = set(title.lower().split())

        # Store hashes for future duplicate detection
        article["url_hash"] = url_hash
        article["content_hash"] = content_hash
        article["duplicate_check"] = "unique"  # Assume unique for now

        # In a real implementation, you'd check against a database or cache
        # For now, we'll assume all articles are unique
        return False

    async def enhance_article_async(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance article with additional metadata."""
        loop = asyncio.get_event_loop()

        return await loop.run_in_executor(
            self.thread_pool, self.enhance_article_sync, article
        )

    def enhance_article_sync(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous article enhancement (runs in thread pool)."""
        # Extract category from URL and content
        article["category"] = self.extract_category(article)

        # Extract keywords
        article["keywords"] = self.extract_keywords(article.get("content", ""))

        # Sentiment analysis (basic)
        article["sentiment"] = self.analyze_sentiment(article.get("content", ""))

        # Add processing timestamp
        article["processed_date"] = datetime.now().isoformat()

        # Extract entities (basic)
        article["entities"] = self.extract_entities(article.get("content", ""))

        return article

    def extract_category(self, article: Dict[str, Any]) -> str:
        """Extract category from URL and content."""
        url = article.get("url", "").lower()
        content = article.get("content", "").lower()
        title = article.get("title", "").lower()

        categories = {
            "Technology": [
                "tech",
                "technology",
                "software",
                "ai",
                "artificial intelligence",
                "computer",
                "digital",
            ],
            "Politics": [
                "politics",
                "political",
                "government",
                "election",
                "vote",
                "congress",
                "senate",
            ],
            "Business": [
                "business",
                "finance",
                "economy",
                "market",
                "stock",
                "economic",
                "trade",
            ],
            "Sports": [
                "sports",
                "sport",
                "football",
                "basketball",
                "baseball",
                "soccer",
                "tennis",
            ],
            "Health": [
                "health",
                "medical",
                "medicine",
                "doctor",
                "hospital",
                "covid",
                "vaccine",
            ],
            "Science": [
                "science",
                "research",
                "study",
                "discovery",
                "scientist",
                "experiment",
            ],
            "Entertainment": [
                "entertainment",
                "movie",
                "film",
                "music",
                "celebrity",
                "hollywood",
            ],
            "World": [
                "world",
                "international",
                "global",
                "foreign",
                "country",
                "nation",
            ],
        }

        # Check URL first
        for category, keywords in categories.items():
            if any(keyword in url for keyword in keywords):
                return category

        # Check title and content
        text_to_check = f"{title} {content}"
        category_scores = {}

        for category, keywords in categories.items():
            score = sum(1 for keyword in keywords if keyword in text_to_check)
            if score > 0:
                category_scores[category] = score

        if category_scores:
            return max(category_scores, key=category_scores.get)

        return "News"

    def extract_keywords(self, content: str, max_keywords: int = 10) -> List[str]:
        """Extract keywords from content."""
        # Simple keyword extraction
        words = re.findall(r"\b[a-zA-Z]{4,}\b", content.lower())

        # Remove common stop words
        stop_words = {
            "that",
            "with",
            "have",
            "this",
            "will",
            "you",
            "from",
            "they",
            "know",
            "want",
            "been",
            "good",
            "much",
            "some",
            "time",
            "very",
            "when",
            "come",
            "here",
            "just",
            "like",
            "long",
            "make",
            "many",
            "over",
            "such",
            "take",
            "than",
            "them",
            "well",
            "were",
            "what",
            "your",
            "about",
            "after",
            "back",
            "could",
            "first",
            "into",
            "most",
            "only",
            "other",
            "right",
            "should",
            "these",
            "think",
            "through",
            "would",
            "said",
            "says",
            "according",
        }

        # Count word frequencies
        word_counts = {}
        for word in words:
            if word not in stop_words and len(word) > 3:
                word_counts[word] = word_counts.get(word, 0) + 1

        # Get top keywords
        top_keywords = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        return [word for word, count in top_keywords[:max_keywords]]

    def analyze_sentiment(self, content: str) -> str:
        """Basic sentiment analysis."""
        positive_words = {
            "good",
            "great",
            "excellent",
            "amazing",
            "wonderful",
            "fantastic",
            "positive",
            "success",
            "win",
            "victory",
            "progress",
            "improve",
            "better",
            "best",
            "happy",
            "pleased",
            "excited",
            "optimistic",
            "hopeful",
        }

        negative_words = {
            "bad",
            "terrible",
            "awful",
            "horrible",
            "negative",
            "fail",
            "failure",
            "loss",
            "decline",
            "worse",
            "worst",
            "sad",
            "angry",
            "disappointed",
            "crisis",
            "problem",
            "issue",
            "concern",
            "worry",
            "fear",
        }

        words = content.lower().split()
        positive_count = sum(1 for word in words if word in positive_words)
        negative_count = sum(1 for word in words if word in negative_words)

        if positive_count > negative_count:
            return "positive"
        elif negative_count > positive_count:
            return "negative"
        else:
            return "neutral"

    def extract_entities(self, content: str) -> Dict[str, List[str]]:
        """Basic entity extraction."""
        entities = {"people": [], "organizations": [], "locations": [], "dates": []}

        # Simple regex patterns for entity extraction
        # In production, you'd use spaCy or similar NLP library

        # People (capitalized words that might be names)
        people_pattern = r"\b[A-Z][a-z]+ [A-Z][a-z]+\b"
        people = re.findall(people_pattern, content)
        entities["people"] = list(set(people))[:5]  # Limit to 5

        # Organizations (Inc, Corp, Ltd, etc.)
        org_pattern = (
            r"\b[A-Z][a-z]+(?: [A-Z][a-z]+)*(?: Inc\.?| Corp\.?| Ltd\.?| LLC)\b"
        )
        orgs = re.findall(org_pattern, content)
        entities["organizations"] = list(set(orgs))[:5]

        # Dates (basic patterns)
        date_pattern = r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2},? \d{4}\b"
        dates = re.findall(date_pattern, content)
        entities["dates"] = list(set(dates))[:3]

        return entities

    async def save_processed_articles(
        self, articles: List[Dict[str, Any]], output_path: str
    ):
        """Save processed articles to file."""
        async with aiofiles.open(output_path, "w") as f:
            await f.write(json.dumps(articles, indent=2, ensure_ascii=False))

    async def upload_to_s3_async(
        self, articles: List[Dict[str, Any]], bucket: str, key: str
    ) -> bool:
        """Upload articles to S3 asynchronously."""
        if not self.s3_client:
            self.logger.warning("S3 client not configured")
            return False

        try:
            # Prepare data
            data = json.dumps(articles, indent=2, ensure_ascii=False)

            # Upload in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self.thread_pool, self.upload_to_s3_sync, data, bucket, key
            )

            self.logger.info(
                f"✅ Uploaded {len(articles)} articles to s3://{bucket}/{key}"
            )
            return True

        except Exception as e:
            self.logger.error(f"❌ S3 upload failed: {e}")
            return False

    def upload_to_s3_sync(self, data: str, bucket: str, key: str):
        """Synchronous S3 upload (runs in thread pool)."""
        self.s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data.encode(),
            ContentType="application/json",
            Metadata={
                "scraper": "async-python",
                "timestamp": datetime.now().isoformat(),
                "articles": str(len(json.loads(data))),
            },
        )

    def get_processing_stats(self) -> Dict[str, Any]:
        """Get processing statistics."""
        return {
            "total_processed": len(self.processed_articles),
            "validation_stats": self.validation_stats.copy(),
            "duplicate_stats": self.duplicate_stats.copy(),
            "quality_distribution": self.get_quality_distribution(),
            "category_distribution": self.get_category_distribution(),
        }

    def get_quality_distribution(self) -> Dict[str, int]:
        """Get quality distribution of processed articles."""
        distribution = {"high": 0, "medium": 0, "low": 0}

        for article in self.processed_articles:
            quality = article.get("content_quality", "unknown")
            if quality in distribution:
                distribution[quality] += 1

        return distribution

    def get_category_distribution(self) -> Dict[str, int]:
        """Get category distribution of processed articles."""
        distribution = {}

        for article in self.processed_articles:
            category = article.get("category", "Unknown")
            distribution[category] = distribution.get(category, 0) + 1

        return distribution

    def close(self):
        """Clean up resources."""
        self.thread_pool.shutdown(wait=True)
