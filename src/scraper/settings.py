"""
Scrapy settings for NeuroNews scrapers.
"""
import json
import os

# Load settings from config file
CONFIG_PATH = os.path.join('config', 'settings.json')
with open(CONFIG_PATH) as f:
    config = json.load(f)

# Scrapy settings
BOT_NAME = config['app_name']
SPIDER_MODULES = ['src.scraper.spiders']
NEWSPIDER_MODULE = 'src.scraper.spiders'

# Crawl responsibly by identifying yourself on the user-agent
USER_AGENT = f'{config["app_name"]}/{config["version"]} (+https://example.com)'

# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Configure maximum concurrent requests
CONCURRENT_REQUESTS = 16

# Configure a delay for requests for the same website
DOWNLOAD_DELAY = 3
RANDOMIZE_DOWNLOAD_DELAY = True

# Disable cookies
COOKIES_ENABLED = False

# Configure item pipelines
ITEM_PIPELINES = {
    'src.scraper.pipelines.DuplicateFilterPipeline': 100,
    'src.scraper.pipelines.JsonWriterPipeline': 300,
    'src.scraper.pipelines.s3_pipeline.S3StoragePipeline': 400,
}

# S3 storage pipeline configuration

# AWS settings (override these with environment variables or command line arguments)
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
AWS_REGION = os.environ.get('AWS_REGION', config['aws']['region'])
S3_BUCKET = os.environ.get('S3_BUCKET', config['aws']['s3']['bucket'])
S3_PREFIX = os.environ.get('S3_PREFIX', config['aws']['s3']['prefix'])

# CloudWatch logging settings (disabled by default, enabled with --cloudwatch flag)
CLOUDWATCH_LOGGING_ENABLED = True  # Enable CloudWatch logging by default
CLOUDWATCH_LOG_GROUP = os.environ.get('CLOUDWATCH_LOG_GROUP', config['aws']['cloudwatch']['log_group'])
CLOUDWATCH_LOG_STREAM_PREFIX = os.environ.get('CLOUDWATCH_LOG_STREAM_PREFIX', config['aws']['cloudwatch']['log_stream_prefix'])
CLOUDWATCH_LOG_LEVEL = os.environ.get('CLOUDWATCH_LOG_LEVEL', config['aws']['cloudwatch']['log_level'])

# Configure extensions
EXTENSIONS = {
    'src.scraper.extensions.cloudwatch_logging.CloudWatchLoggingExtension': 100,
}

# Enable and configure the AutoThrottle extension
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 5
AUTOTHROTTLE_MAX_DELAY = 60
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
AUTOTHROTTLE_DEBUG = config['debug']

# Enable showing throttling stats for every response received
HTTPCACHE_ENABLED = True
HTTPCACHE_EXPIRATION_SECS = 0
HTTPCACHE_DIR = 'httpcache'
HTTPCACHE_IGNORE_HTTP_CODES = []
HTTPCACHE_STORAGE = 'scrapy.extensions.httpcache.FilesystemCacheStorage'

# Playwright settings for JavaScript-heavy pages
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

# Playwright browser settings
PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "timeout": 20 * 1000,  # 20 seconds
}
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30 * 1000  # 30 seconds

# Custom settings
SCRAPING_SOURCES = config['scraping']['sources']
SCRAPING_INTERVAL = config['scraping']['interval_minutes']
