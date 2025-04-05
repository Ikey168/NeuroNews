"""
Pipelines for processing scraped items in NeuroNews.
"""
import json
import os


class JsonWriterPipeline:
    """Pipeline for writing scraped items to a JSON file."""

    def open_spider(self, spider):
        """Called when the spider is opened."""
        # Create data directory if it doesn't exist
        os.makedirs('data', exist_ok=True)
        self.file = open('data/news_articles.json', 'w')
        self.file.write('[')
        self.first_item = True

    def close_spider(self, spider):
        """Called when the spider is closed."""
        self.file.write(']')
        self.file.close()

    def process_item(self, item, spider):
        """Process each scraped item."""
        line = json.dumps(dict(item))
        if self.first_item:
            self.first_item = False
        else:
            self.file.write(',\n')
        self.file.write(line)
        return item


class DuplicateFilterPipeline:
    """Pipeline for filtering out duplicate items."""

    def __init__(self):
        self.urls_seen = set()

    def process_item(self, item, spider):
        """Process each scraped item."""
        if item['url'] in self.urls_seen:
            # Skip duplicate items
            return None
        else:
            self.urls_seen.add(item['url'])
            return item
