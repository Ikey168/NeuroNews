# NeuroNews Scraper

A Scrapy-based news scraper for the NeuroNews project.

## Features

- Crawls news websites defined in the configuration
- Extracts article content, metadata, and categorizes news
- Filters out duplicate articles
- Saves scraped data to JSON files
- Supports JavaScript-heavy pages using Playwright

## Usage

### From the Command Line

You can run the scraper directly:

```bash
python -m src.scraper.run
```

Options:
- `--output`, `-o`: Specify the output file path (default: data/news_articles.json)
- `--list-sources`, `-l`: List the configured news sources
- `--playwright`, `-p`: Use Playwright for JavaScript-heavy pages

### From the Main Application

You can also run the scraper from the main application:

```bash
python src/main.py --scrape
```

Options:
- `--output`, `-o`: Specify the output file path (default: data/news_articles.json)
- `--playwright`, `-p`: Use Playwright for JavaScript-heavy pages

### As a Library

```python
from src.scraper import scrape_news

# Run the scraper and get the results
articles = scrape_news()

# Or specify a custom output file
articles = scrape_news('path/to/output.json')

# Use Playwright for JavaScript-heavy pages
articles = scrape_news('path/to/output.json', use_playwright=True)
```

## Configuration

The scraper uses the settings defined in `config/settings.json`. The relevant settings are:

```json
{
  "scraping": {
    "interval_minutes": 60,
    "sources": [
      "https://example.com/news",
      "https://example.org/tech"
    ]
  }
}
```

## Customization

To add support for specific news sites, you may need to customize the selectors in the spider classes:
- `NewsSpider` in `src/scraper/spiders/news_spider.py` for regular sites
- `PlaywrightNewsSpider` in `src/scraper/spiders/playwright_spider.py` for JavaScript-heavy sites

## Structure

- `__init__.py`: Package initialization
- `items.py`: Defines the data structure for scraped items
- `pipelines.py`: Processing pipelines for scraped items
- `settings.py`: Scrapy settings
- `run.py`: Command-line interface
- `spiders/`: Directory containing spider implementations
  - `__init__.py`: Package initialization
  - `news_spider.py`: Regular news spider implementation
  - `playwright_spider.py`: Playwright-based spider for JavaScript-heavy pages
