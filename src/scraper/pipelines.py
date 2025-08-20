"""
Pipelines for processing scraped items in NeuroNews.
"""

import hashlib
import json
import os
from datetime import datetime
from urllib.parse import urlparse


class ValidationPipeline:
    """Pipeline for validating scraped items."""

    def process_item(self, item, spider):
        """Validate each scraped item."""
        validation_score = 100

        # Check required fields
        required_fields = ["title", "url", "content", "source"]
        for field in required_fields:
            if not item.get(field):
                validation_score -= 25

        # Validate title length
        if item.get("title"):
            title_len = len(item["title"])
            if title_len < 10 or title_len > 200:
                validation_score -= 10

        # Validate content length
        if item.get("content"):
            content_len = len(item["content"])
            item["content_length"] = content_len
            item["word_count"] = len(item["content"].split())

            # Calculate reading time (average 200 words per minute)
            item["reading_time"] = max(1, round(item["word_count"] / 200))

            if content_len < 100:
                validation_score -= 20
            elif content_len > 10000:
                validation_score -= 5
        else:
            validation_score -= 30

        # Validate URL format
        if item.get("url"):
            try:
                parsed_url = urlparse(item["url"])
                if not parsed_url.scheme or not parsed_url.netloc:
                    validation_score -= 15
            except BaseException:
                validation_score -= 15

        # Validate date format
        if item.get("published_date"):
            try:
                # Try to parse the date to ensure it's valid
                if "T" in item["published_date"]:
                    datetime.fromisoformat(
                        item["published_date"].replace("Z", "+00:00")
                    )
            except BaseException:
                validation_score -= 10

        # Add scraped timestamp
        item["scraped_date"] = datetime.now().isoformat()

        # Set default language
        item["language"] = item.get("language", "en")

        # Set validation score
        item["validation_score"] = max(0, validation_score)

        # Determine content quality
        if validation_score >= 80:
            item["content_quality"] = "high"
        elif validation_score >= 60:
            item["content_quality"] = "medium"
        else:
            item["content_quality"] = "low"

        # Only pass items with minimum quality
        if validation_score >= 50:
            return item
        else:
            spider.logger.warning(
                "Item rejected due to low validation score: {0}".format(
                    validation_score
                )
            )
            return None


class DuplicateFilterPipeline:
    """Enhanced pipeline for filtering out duplicate items."""

    def __init__(self):
        self.urls_seen = set()
        self.content_hashes = set()

    def process_item(self, item, spider):
        """Process each scraped item for duplicates."""
        # Check URL duplicates
        if item["url"] in self.urls_seen:
            item["duplicate_check"] = "url_duplicate"
            spider.logger.info(f"Duplicate URL found: {item['url']}")
            return None

        # Check content duplicates using hash
        if item.get("content"):
            content_hash = hashlib.md5(item["content"].encode("utf-8")).hexdigest()
            if content_hash in self.content_hashes:
                item["duplicate_check"] = "content_duplicate"
                spider.logger.info(
                    f"Duplicate content found for URL: {
                        item['url']}"
                )
                return None
            self.content_hashes.add(content_hash)

        self.urls_seen.add(item["url"])
        item["duplicate_check"] = "unique"
        return item


class EnhancedJsonWriterPipeline:
    """Enhanced pipeline for writing scraped items to JSON files organized by source."""

    def open_spider(self, spider):
        """Called when the spider is opened."""
        # Create data directory structure
        self.data_dir = "data"
        self.sources_dir = os.path.join(self.data_dir, "sources")
        os.makedirs(self.sources_dir, exist_ok=True)

        # Create a combined file for all sources
        self.combined_file = open(os.path.join(self.data_dir, "all_articles.json"), "w")
        self.combined_file.write("[")
        self.combined_first_item = True

        # Dictionary to store file handles for each source
        self.source_files = {}
        self.source_first_items = {}

    def close_spider(self, spider):
        """Called when the spider is closed."""
        # Close combined file
        self.combined_file.write("]")
        self.combined_file.close()

        # Close all source-specific files
        for source, file_handle in self.source_files.items():
            file_handle.write("]")
            file_handle.close()

    def process_item(self, item, spider):
        """Process each scraped item."""
        line = json.dumps(dict(item), indent=2, ensure_ascii=False)

        # Write to combined file
        if self.combined_first_item:
            self.combined_first_item = False
        else:
            self.combined_file.write(",\n")
        self.combined_file.write(line)

        # Write to source-specific file
        source = item.get("source", "unknown").lower().replace(" ", "_")

        if source not in self.source_files:
            source_file_path = os.path.join(
                self.sources_dir, "{0}_articles.json".format(source)
            )
            self.source_files[source] = open(source_file_path, "w")
            self.source_files[source].write("[")
            self.source_first_items[source] = True

        if self.source_first_items[source]:
            self.source_first_items[source] = False
        else:
            self.source_files[source].write(",\n")
        self.source_files[source].write(line)

        return item


class JsonWriterPipeline:
    """Legacy pipeline for backward compatibility."""

    def open_spider(self, spider):
        """Called when the spider is opened."""
        # Create data directory if it doesn't exist
        os.makedirs("data", exist_ok=True)
        self.file = open("data/news_articles.json", "w")
        self.file.write("[")
        self.first_item = True

    def close_spider(self, spider):
        """Called when the spider is closed."""
        self.file.write("]")
        self.file.close()

    def process_item(self, item, spider):
        """Process each scraped item."""
        line = json.dumps(dict(item))
        if self.first_item:
            self.first_item = False
        else:
            self.file.write(",\n")
        self.file.write(line)
        return item
