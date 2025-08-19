"""Test base pipeline functionality without S3 dependencies."""

import os
import json
import tempfile
import pytest


class JsonWriterPipeline:
    """Pipeline for writing scraped items to a JSON file."""

    def open_spider(self, spider):
        """Called when the spider is opened."""
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


class DuplicateFilterPipeline:
    """Pipeline for filtering out duplicate items."""

    def __init__(self):
        self.urls_seen = set()

    def process_item(self, item, spider):
        """Process each scraped item."""
        if item["url"] in self.urls_seen:
            # Skip duplicate items
            return None
        else:
            self.urls_seen.add(item["url"])
            return item


class TestPipelines:
    def test_duplicate_filter(self):
        pipeline = DuplicateFilterPipeline()
        spider = None  # Not needed for this test

        # Test with unique URLs
        item1 = {"url": "http://example.com/1", "title": "Test 1"}
        item2 = {"url": "http://example.com/2", "title": "Test 2"}

        result1 = pipeline.process_item(item1, spider)
        assert result1 == item1, "Should pass through unique item"

        result2 = pipeline.process_item(item2, spider)
        assert result2 == item2, "Should pass through second unique item"

        # Test with duplicate URL
        result3 = pipeline.process_item(item1, spider)
        assert result3 is None, "Should filter out duplicate item"

    def test_json_writer(self, tmp_path):
        # Create pipeline instance
        pipeline = JsonWriterPipeline()
        spider = None  # Not needed for this test

        # Redirect output to temp directory
        test_output = tmp_path / "test_output.json"
        pipeline.file = open(test_output, "w")
        pipeline.file.write("[")
        pipeline.first_item = True

        # Process items
        items = [
            {"url": "http://example.com/1", "title": "Test 1"},
            {"url": "http://example.com/2", "title": "Test 2"},
        ]

        for item in items:
            pipeline.process_item(item, spider)

        pipeline.file.write("]")
        pipeline.file.close()

        # Verify output
        with open(test_output) as f:
            data = json.load(f)
            assert len(data) == 2, "Should contain both items"
            assert data[0]["title"] == "Test 1", "First item should be Test 1"
            assert data[1]["title"] == "Test 2", "Second item should be Test 2"
