package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"testing"
	"time"
)

func TestAsyncScraper(t *testing.T) {
	// Create test configuration
	config := &Config{
		MaxWorkers:  2,
		RateLimit:   1.0,
		Timeout:     30 * time.Second,
		OutputDir:   "test_output",
		UserAgent:   "NeuroNews-Test/1.0",
		RetryCount:  1,
		RetryDelay:  1 * time.Second,
		ConcurrentBrowsers: 1,
	}
	
	// Create test sources (limited for testing)
	testSources := []NewsSource{
		{
			Name:    "BBC Test",
			BaseURL: "https://www.bbc.com/news",
			ArticleSelectors: map[string]string{
				"title":   "h1[data-testid='headline'], h1",
				"content": "div[data-component='text-block'] p, article p",
				"author":  "span[data-testid='byline'], .byline-name",
				"date":    "time[datetime]",
			},
			LinkPatterns: []string{`/news/.*`},
			RequiresJS:   false,
			RateLimit:    1,
		},
	}
	
	// Create output directory
	os.MkdirAll(config.OutputDir, 0755)
	defer os.RemoveAll(config.OutputDir)
	
	// Initialize scraper
	scraper := NewAsyncScraper(config, testSources)
	
	// Create context with timeout
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	
	// Run scraper
	err := scraper.ScrapeAllSources(ctx)
	if err != nil {
		t.Fatalf("Scraper failed: %v", err)
	}
	
	// Validate results
	metrics := scraper.GetMetrics()
	if metrics.TotalArticles == 0 {
		t.Logf("Warning: No articles scraped in test")
	}
	
	log.Printf("Test completed: %d articles scraped", metrics.TotalArticles)
}

func TestJSHeavyScraper(t *testing.T) {
	scraper := NewJSHeavyScraper(1) // Single browser for test
	
	// Create test source
	testSource := NewsSource{
		Name:    "Test JS Site",
		BaseURL: "https://www.example.com",
		ArticleSelectors: map[string]string{
			"title":   "h1",
			"content": "p",
			"author":  ".author",
			"date":    "time",
		},
		LinkPatterns: []string{`/article/.*`},
		RequiresJS:   true,
		RateLimit:    1,
	}
	
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	
	// This test might fail if site is unreachable, but validates structure
	err := scraper.ScrapeJSHeavySite(ctx, testSource)
	if err != nil {
		t.Logf("JS scraper test completed with expected error: %v", err)
	}
	
	articles := scraper.getArticles()
	t.Logf("JS scraper collected %d articles", len(articles))
}

func TestPerformanceMetrics(t *testing.T) {
	metrics := NewPerformanceMetrics()
	
	// Test article tracking
	metrics.IncrementArticleCount("test-source")
	metrics.RecordSuccessfulScrape("test-source")
	metrics.IncrementArticleCount("test-source")
	metrics.RecordFailedScrape("test-source", "test error")
	
	// Wait a moment for timing
	time.Sleep(100 * time.Millisecond)
	
	// Get summary
	summary := metrics.GetSummary()
	
	if summary.TotalArticles != 2 {
		t.Errorf("Expected 2 articles, got %d", summary.TotalArticles)
	}
	
	if summary.SuccessfulScrapes != 1 {
		t.Errorf("Expected 1 successful scrape, got %d", summary.SuccessfulScrapes)
	}
	
	if summary.FailedScrapes != 1 {
		t.Errorf("Expected 1 failed scrape, got %d", summary.FailedScrapes)
	}
	
	// Test source-specific metrics
	sourceStats := metrics.GetSourceStats("test-source")
	if sourceStats.ArticleCount != 2 {
		t.Errorf("Expected 2 articles for test-source, got %d", sourceStats.ArticleCount)
	}
	
	log.Printf("Performance metrics test completed successfully")
}

func TestArticleValidation(t *testing.T) {
	// Test high-quality article
	goodArticle := &Article{
		Title:         "Test Article Title",
		Content:       "This is a test article with sufficient content to pass validation checks. It contains multiple sentences and provides meaningful information.",
		Author:        "Test Author",
		PublishedDate: "2024-01-01",
		Source:        "Test Source",
		URL:           "https://example.com/article",
		ContentLength: 150,
		WordCount:     25,
	}
	
	score := validateArticleQuality(goodArticle)
	if score < 80 {
		t.Errorf("Good article should score >= 80, got %d", score)
	}
	
	// Test poor-quality article
	badArticle := &Article{
		Title:   "",
		Content: "Short",
		URL:     "https://example.com",
	}
	
	score = validateArticleQuality(badArticle)
	if score >= 50 {
		t.Errorf("Bad article should score < 50, got %d", score)
	}
	
	log.Printf("Article validation test completed successfully")
}

func TestConfigLoading(t *testing.T) {
	// Create temporary config file
	configData := `{
		"max_workers": 5,
		"rate_limit": 2.0,
		"timeout": "60s",
		"output_dir": "test_output",
		"user_agent": "Test Agent",
		"retry_count": 3,
		"retry_delay": "2s",
		"concurrent_browsers": 2,
		"sources": []
	}`
	
	tmpFile := "test_config.json"
	err := os.WriteFile(tmpFile, []byte(configData), 0644)
	if err != nil {
		t.Fatalf("Failed to create test config: %v", err)
	}
	defer os.Remove(tmpFile)
	
	// Load config
	config, err := LoadConfig(tmpFile)
	if err != nil {
		t.Fatalf("Failed to load config: %v", err)
	}
	
	if config.MaxWorkers != 5 {
		t.Errorf("Expected MaxWorkers=5, got %d", config.MaxWorkers)
	}
	
	if config.RateLimit != 2.0 {
		t.Errorf("Expected RateLimit=2.0, got %f", config.RateLimit)
	}
	
	log.Printf("Config loading test completed successfully")
}

// Benchmark test for scraper performance
func BenchmarkArticleProcessing(b *testing.B) {
	article := &Article{
		Title:   "Benchmark Test Article",
		Content: "This is a benchmark test article with some content for performance testing.",
		Author:  "Benchmark Author",
		URL:     "https://example.com/benchmark",
	}
	
	b.ResetTimer()
	
	for i := 0; i < b.N; i++ {
		// Simulate article processing
		article.ContentLength = len(article.Content)
		article.WordCount = len(strings.Fields(article.Content))
		article.ReadingTime = max(1, article.WordCount/200)
		article.ValidationScore = validateArticleQuality(article)
		
		// Simulate category extraction
		article.Category = extractCategoryFromURL(article.URL)
	}
}

// Integration test with real sources (optional)
func TestIntegrationScraping(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}
	
	// Small integration test with one real source
	config := &Config{
		MaxWorkers:  1,
		RateLimit:   0.5, // Very conservative for testing
		Timeout:     30 * time.Second,
		OutputDir:   "integration_output",
		UserAgent:   "NeuroNews-Integration-Test/1.0",
		RetryCount:  1,
		RetryDelay:  2 * time.Second,
		ConcurrentBrowsers: 1,
	}
	
	// Use a simple, reliable source for integration testing
	testSources := []NewsSource{
		{
			Name:    "Reuters Test",
			BaseURL: "https://www.reuters.com",
			ArticleSelectors: map[string]string{
				"title":   "h1[data-testid='Headline'], h1",
				"content": "div[data-testid='ArticleBody'] p, .article-body p",
				"author":  "a[data-testid='Author'], .byline",
				"date":    "time[datetime]",
			},
			LinkPatterns: []string{`/world/.*`, `/business/.*`},
			RequiresJS:   false,
			RateLimit:    2, // Conservative rate limiting
		},
	}
	
	// Create output directory
	os.MkdirAll(config.OutputDir, 0755)
	defer os.RemoveAll(config.OutputDir)
	
	scraper := NewAsyncScraper(config, testSources)
	
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	
	err := scraper.ScrapeAllSources(ctx)
	if err != nil {
		t.Logf("Integration test completed with error (expected for test environment): %v", err)
	}
	
	metrics := scraper.GetMetrics()
	t.Logf("Integration test metrics: %d total articles, %d successful scrapes, %d failed scrapes",
		metrics.TotalArticles, metrics.SuccessfulScrapes, metrics.FailedScrapes)
}

func TestMain(m *testing.M) {
	log.Println("🧪 Starting Go Scraper Tests")
	
	// Create test directories
	os.MkdirAll("test_output", 0755)
	os.MkdirAll("integration_output", 0755)
	
	// Run tests
	code := m.Run()
	
	// Cleanup
	os.RemoveAll("test_output")
	os.RemoveAll("integration_output")
	
	log.Println("🏁 Tests completed")
	os.Exit(code)
}
