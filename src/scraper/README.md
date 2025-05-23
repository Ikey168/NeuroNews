# NeuroNews Scraper

A Scrapy-based news scraper for the NeuroNews project.

## Features

- Crawls news websites defined in the configuration
- Extracts article content, metadata, and categorizes news
- Filters out duplicate articles
- Saves scraped data to JSON files
- Supports JavaScript-heavy pages using Playwright
- Stores articles in Amazon S3 with metadata
- Logs scraper execution in AWS CloudWatch

## Usage

### Setting Up AWS Credentials and Dev Environment

The project includes a setup script to configure AWS credentials and create a dev environment configuration:

```bash
# Make the script executable if needed
chmod +x scripts/setup_aws_dev.py

# Run the setup script
./scripts/setup_aws_dev.py --access-key YOUR_AWS_ACCESS_KEY --secret-key YOUR_AWS_SECRET_KEY
```

This script will:
1. Set up AWS credentials in your `~/.aws/credentials` file
2. Create a `config/dev_aws.json` configuration file
3. Check if the required AWS resources (S3 bucket, CloudWatch log group) exist and offer to create them
4. Generate commands to run the scraper with AWS integration

### From the Command Line

You can run the scraper directly:

```bash
python -m src.scraper.run
```

Options:
- `--output`, `-o`: Specify the output file path (default: data/news_articles.json)
- `--list-sources`, `-l`: List the configured news sources
- `--playwright`, `-p`: Use Playwright for JavaScript-heavy pages
- `--env`: Environment (dev, staging, prod) for loading AWS config (default: dev)

AWS Credentials:
- `--aws-profile`: AWS profile name
- `--aws-key-id`: AWS access key ID
- `--aws-secret-key`: AWS secret access key
- `--aws-region`: AWS region (default: us-east-1)

S3 Storage Options:
- `--s3`, `-s`: Store articles in Amazon S3
- `--s3-bucket`: S3 bucket name
- `--s3-prefix`: S3 key prefix (default: news_articles)

CloudWatch Logging Options:
- `--cloudwatch`, `-c`: Log to AWS CloudWatch
- `--cloudwatch-log-group`: CloudWatch log group name (default: NeuroNews-Scraper)
- `--cloudwatch-log-stream-prefix`: CloudWatch log stream prefix (default: scraper)
- `--cloudwatch-log-level`: CloudWatch log level (default: INFO)

Example with all AWS features:
```bash
python -m src.scraper.run \
  --aws-profile neuronews-dev \
  --s3 --s3-bucket neuronews-raw-articles-dev \
  --cloudwatch --cloudwatch-log-level DEBUG
```

### From the Main Application

You can also run the scraper from the main application:

```bash
python src/main.py --scrape
```

The main application supports all the same options as the command-line interface.

### As a Library

```python
from src.scraper import scrape_news

# Run the scraper and get the results
articles = scrape_news()

# Or specify a custom output file
articles = scrape_news('path/to/output.json')

# Use Playwright for JavaScript-heavy pages
articles = scrape_news('path/to/output.json', use_playwright=True)

# Use AWS profile
articles = scrape_news(
    aws_profile='neuronews-dev',
    env='dev'  # Load config from config/dev_aws.json
)

# Store articles in S3
articles = scrape_news(
    output_file='path/to/output.json',
    s3_storage=True,
    aws_access_key_id='YOUR_KEY_ID',
    aws_secret_access_key='YOUR_SECRET_KEY',
    s3_bucket='your-bucket-name',
    s3_prefix='news_articles'
)

# Log to CloudWatch
articles = scrape_news(
    cloudwatch_logging=True,
    aws_access_key_id='YOUR_KEY_ID',
    aws_secret_access_key='YOUR_SECRET_KEY',
    cloudwatch_log_group='NeuroNews-Scraper',
    cloudwatch_log_level='DEBUG'
)

# Use all AWS features
articles = scrape_news(
    output_file='path/to/output.json',
    use_playwright=True,
    s3_storage=True,
    cloudwatch_logging=True,
    aws_access_key_id='YOUR_KEY_ID',
    aws_secret_access_key='YOUR_SECRET_KEY',
    aws_region='us-west-2',
    s3_bucket='your-bucket-name',
    s3_prefix='news_articles',
    cloudwatch_log_group='NeuroNews-Scraper',
    cloudwatch_log_stream_prefix='scraper',
    cloudwatch_log_level='INFO'
)
```

## Configuration

### Scraping Configuration

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

### AWS Configuration

For AWS services (S3 storage and CloudWatch logging), you can provide credentials in four ways:

1. AWS profile:
   ```bash
   --aws-profile neuronews-dev
   ```

2. Command-line arguments:
   ```bash
   --aws-key-id YOUR_KEY_ID --aws-secret-key YOUR_SECRET_KEY --aws-region us-west-2
   ```

3. Environment variables:
   ```bash
   export AWS_ACCESS_KEY_ID=YOUR_KEY_ID
   export AWS_SECRET_ACCESS_KEY=YOUR_SECRET_KEY
   export AWS_REGION=us-west-2
   export S3_BUCKET=your-bucket-name
   export CLOUDWATCH_LOG_GROUP=NeuroNews-Scraper
   ```

4. Configuration file:
   ```json
   {
     "aws_profile": "neuronews-dev",
     "s3_storage": {
       "enabled": true,
       "bucket": "neuronews-raw-articles-dev",
       "prefix": "news_articles"
     },
     "cloudwatch_logging": {
       "enabled": true,
       "log_group": "NeuroNews-Scraper",
       "log_stream_prefix": "scraper",
       "log_level": "INFO"
     }
   }
   ```

   You can create this file manually or use the `scripts/setup_aws_dev.py` script to generate it.

## S3 Storage Structure

Articles are stored in S3 with the following key structure:
```
{prefix}/{source-domain}/{timestamp}_{title-slug}.json
```

For example:
```
news_articles/example-com/20250406120000_breaking-news-article.json
```

Each article is stored as a JSON file with the full article content, and S3 object metadata contains key information like title, URL, source, publication date, author, and category for easy querying.

## CloudWatch Logging

The scraper logs execution details to CloudWatch Logs with the following structure:
```
{log-group}/{log-stream-prefix}-{spider-name}-{timestamp}
```

For example:
```
NeuroNews-Scraper/scraper-news-20250406120000
```

Log entries include:
- Spider start/stop events
- Request/response details
- Item extraction information
- Error and warning messages
- Performance metrics

This provides comprehensive monitoring and debugging capabilities for the scraper, especially useful for automated deployments.

## Development Environments

The scraper supports multiple environments (dev, staging, prod) for AWS configuration:

- **Dev**: Used for local development and testing
  - Configuration file: `config/dev_aws.json`
  - Command-line option: `--env dev` (default)

- **Staging**: Used for pre-production testing
  - Configuration file: `config/staging_aws.json`
  - Command-line option: `--env staging`

- **Prod**: Used for production deployment
  - Configuration file: `config/prod_aws.json`
  - Command-line option: `--env prod`

Each environment can have different AWS credentials, S3 buckets, and CloudWatch log groups.

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
- `pipelines/`: Directory containing pipeline implementations
  - `__init__.py`: Package initialization
  - `s3_pipeline.py`: Pipeline for storing articles in S3
- `logging/`: Directory containing logging implementations
  - `__init__.py`: Package initialization
  - `cloudwatch_handler.py`: Handler for logging to CloudWatch
- `extensions/`: Directory containing Scrapy extensions
  - `__init__.py`: Package initialization
  - `cloudwatch_logging.py`: Extension for CloudWatch logging
