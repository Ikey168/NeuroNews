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
}

# S3 storage pipeline (disabled by default, enabled with --s3 flag)
# When enabled, this will be inserted into the pipeline
S3_PIPELINE_PRIORITY = 400  # Run after JsonWriterPipeline

# AWS settings (override these with environment variables or command line arguments)
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
S3_BUCKET = os.environ.get('S3_BUCKET', '')
S3_PREFIX = os.environ.get('S3_PREFIX', 'news_articles')

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
