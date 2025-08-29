"""
CloudWatch logging extension for Scrapy.
"""

import logging

from scrapy import signals
from scrapy.exceptions import NotConfigured

from ..log_utils import configure_cloudwatch_logging


class CloudWatchLoggingExtension:
    """
    Scrapy extension to send logs to AWS CloudWatch Logs.
    """

    @classmethod
    def from_crawler(cls, crawler):
        """Initialize the extension from a crawler."""
        # Check if CloudWatch logging is enabled
        if not crawler.settings.getbool("CLOUDWATCH_LOGGING_ENABLED", False):
            raise NotConfigured("CloudWatch logging is not enabled")

        # Create an instance of the extension
        ext = cls()

        # Connect the extension to the spider_opened signal
        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)

        # Connect the extension to the spider_closed signal
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)

        # Store the crawler for later use
        ext.crawler = crawler

        return ext

    def spider_opened(self, spider):
        """
        Called when a spider is opened.

        Args:
            spider: The spider that was opened
        """
        # Configure CloudWatch logging
        handler = configure_cloudwatch_logging(self.crawler.settings, spider.name)

        if handler:
            # Store the handler for later cleanup
            self.handler = handler

            # Add the handler to the root logger
            root_logger = logging.getLogger()
            root_logger.addHandler(handler)

            # Add the handler to the Scrapy logger
            scrapy_logger = logging.getLogger("scrapy")
            scrapy_logger.addHandler(handler)

            # Add the handler to the spider logger
            spider_logger = logging.getLogger(spider.name)
            spider_logger.addHandler(handler)

            # Log that CloudWatch logging is configured
            spider.logger.info(
                "CloudWatch logging configured: group={0}, stream={1}".format(
                    handler.log_group_name, handler.log_stream_name
                )
            )

    def spider_closed(self, spider):
        """
        Called when a spider is closed.

        Args:
            spider: The spider that was closed
        """
        if hasattr(self, "handler"):
            # Log that the spider is closing
            spider.logger.info("Spider closing, shutting down CloudWatch logging")

            # Remove the handler from the root logger
            root_logger = logging.getLogger()
            root_logger.removeHandler(self.handler)

            # Remove the handler from the Scrapy logger
            scrapy_logger = logging.getLogger("scrapy")
            scrapy_logger.removeHandler(self.handler)

            # Remove the handler from the spider logger
            spider_logger = logging.getLogger(spider.name)
            spider_logger.removeHandler(self.handler)

            # Close the handler
            self.handler.close()
