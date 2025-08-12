# NeuroNews Go Async Scraper

A high-performance, concurrent news scraper built in Go for collecting articles from multiple news sources simultaneously.

## 🚀 Features

- **Async HTTP Scraping**: Non-blocking concurrent requests using goroutines
- **JavaScript-Heavy Site Support**: Headless browser automation with chromedp
- **Rate Limiting**: Configurable rate limiting per source to respect robots.txt
- **Performance Monitoring**: Real-time metrics and statistics
- **Quality Validation**: Article quality scoring and validation
- **Flexible Configuration**: JSON-based configuration with CLI overrides
- **Retry Logic**: Automatic retry with exponential backoff
- **Multi-format Output**: JSON output with structured article data

## 📋 Requirements

- Go 1.19+
- Chrome/Chromium (for JavaScript-heavy scraping)

## 🛠 Installation

1. **Clone the repository:**
```bash
git clone <repository-url>
cd go-scraper
```

2. **Initialize Go module:**
```bash
go mod init neuronews-scraper
go mod tidy
```

3. **Install dependencies:**
```bash
go get github.com/PuerkitoBio/goquery
go get github.com/go-resty/resty/v2
go get github.com/chromedp/chromedp
go get golang.org/x/time/rate
```

4. **Build the scraper:**
```bash
go build -o neuronews-scraper
```

## ⚙️ Configuration

Create a `config.json` file:

```json
{
  "max_workers": 10,
  "rate_limit": 1.0,
  "timeout": "60s",
  "output_dir": "output",
  "user_agent": "NeuroNews-Scraper/1.0",
  "retry_count": 3,
  "retry_delay": "5s",
  "concurrent_browsers": 3,
  "sources": []
}
```

The configuration includes pre-configured sources for:
- BBC News
- CNN
- TechCrunch
- Ars Technica
- Reuters
- The Guardian
- The Verge (JS-heavy)
- Wired (JS-heavy)
- NPR

## 🎯 Usage

### Basic Usage

```bash
# Run with default configuration
./neuronews-scraper

# Use custom config file
./neuronews-scraper -config my-config.json

# Scrape specific sources
./neuronews-scraper -sources "BBC,CNN,Reuters"

# Enable JavaScript-heavy scraping
./neuronews-scraper -js

# Test mode with limited sources
./neuronews-scraper -test
```

### Advanced Options

```bash
# Custom workers and rate limiting
./neuronews-scraper -workers 15 -rate 2.0

# Verbose logging
./neuronews-scraper -verbose

# Custom output directory
./neuronews-scraper -output /path/to/output

# Custom timeout
./neuronews-scraper -timeout 90s
```

## 🧪 Testing

Run the test suite:

```bash
# Run all tests
go test -v

# Run tests with coverage
go test -cover

# Run benchmark tests
go test -bench=.

# Run integration tests (requires internet)
go test -v -integration
```

## 📊 Performance Metrics

The scraper provides real-time performance metrics:

- **Articles per second**
- **Success/failure rates**
- **Source-specific statistics**
- **Error tracking**
- **Duration measurements**

Example output:
```
==================================================
📊 SCRAPING RESULTS
==================================================
⏱️  Total Duration: 2m30s
📰 Total Articles: 1,247
✅ Successful Scrapes: 1,200
❌ Failed Scrapes: 47
📈 Articles/Second: 8.31
🎯 Success Rate: 96.2%

📋 Source Statistics:
  BBC: 156 articles
  CNN: 198 articles
  Reuters: 234 articles
  TechCrunch: 89 articles
```

## 🏗 Architecture

### Components

1. **AsyncScraper**: Main concurrent scraper using HTTP requests
2. **JSHeavyScraper**: Browser-based scraper for JavaScript-heavy sites
3. **PerformanceMetrics**: Real-time performance monitoring
4. **NewsSource**: Configuration for each news source
5. **Article**: Structured article data with validation

### Flow

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│ Load Config │───▶│ Filter       │───▶│ Initialize  │
│             │    │ Sources      │    │ Scrapers    │
└─────────────┘    └──────────────┘    └─────────────┘
                                              │
                                              ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│ Save        │◀───│ Process      │◀───│ Scrape      │
│ Articles    │    │ Articles     │    │ Concurrently│
└─────────────┘    └──────────────┘    └─────────────┘
```

## 🔧 Customization

### Adding New Sources

Add to `config.json`:

```json
{
  "name": "Your News Site",
  "base_url": "https://example.com",
  "article_selectors": {
    "title": "h1.title",
    "content": ".article-body p",
    "author": ".byline",
    "date": "time[datetime]"
  },
  "link_patterns": ["/articles/.*"],
  "requires_js": false,
  "rate_limit": 1
}
```

### Custom Article Processing

Modify the `Article` struct and validation logic in `main.go`:

```go
type Article struct {
    // Add custom fields
    CustomField string `json:"custom_field"`
    // ... existing fields
}

func validateArticleQuality(article *Article) int {
    // Add custom validation logic
    score := 100
    // ... validation rules
    return score
}
```

## 🚨 Error Handling

The scraper includes comprehensive error handling:

- **Network errors**: Automatic retry with exponential backoff
- **Parsing errors**: Graceful degradation with fallback selectors
- **Rate limiting**: Respect for robots.txt and custom rate limits
- **Memory management**: Efficient goroutine management
- **Timeout handling**: Configurable timeouts for all operations

## 📈 Performance Tips

1. **Optimize Workers**: Start with CPU cores × 2, adjust based on performance
2. **Rate Limiting**: Balance speed vs. respectful scraping
3. **Memory Usage**: Monitor goroutine counts for large-scale scraping
4. **Browser Instances**: Limit concurrent browsers (recommended: 2-5)
5. **Network**: Use fast, stable internet connection

## 🔒 Ethical Considerations

- **Respect robots.txt**: Configure appropriate rate limits
- **User Agent**: Use descriptive user agent strings
- **Request Volume**: Implement reasonable delays between requests
- **Copyright**: Respect content licensing and fair use
- **Terms of Service**: Review target site terms before scraping

## 🐛 Troubleshooting

### Common Issues

1. **Chrome/Chromium not found**:
```bash
# Install Chrome on Ubuntu/Debian
sudo apt-get install google-chrome-stable
```

2. **Rate limiting errors**:
```bash
# Reduce rate limit in config
"rate_limit": 0.5
```

3. **Memory issues**:
```bash
# Reduce concurrent workers
"max_workers": 5
```

4. **Timeout errors**:
```bash
# Increase timeout
"timeout": "120s"
```

## 📝 Output Format

Articles are saved in JSON format:

```json
{
  "title": "Article Title",
  "url": "https://example.com/article",
  "content": "Article content...",
  "author": "Author Name",
  "published_date": "2024-01-01T10:00:00Z",
  "source": "News Source",
  "scraped_date": "2024-01-01T10:05:00Z",
  "language": "en",
  "content_length": 1500,
  "word_count": 250,
  "reading_time": 2,
  "category": "Technology",
  "validation_score": 95,
  "content_quality": "high",
  "duplicate_check": "unique"
}
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make changes and add tests
4. Run tests: `go test -v`
5. Commit changes: `git commit -am 'Add feature'`
6. Push to branch: `git push origin feature-name`
7. Create Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙋‍♂️ Support

For issues and questions:
- Create an issue on GitHub
- Review the troubleshooting section
- Check the test files for usage examples

---

Built with ❤️ using Go for high-performance news scraping.
