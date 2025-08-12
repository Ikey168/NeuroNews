package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"sync"
	"time"
)

// Config represents the scraper configuration
type Config struct {
	Scraper ScraperConfig `json:"scraper"`
	Sources []NewsSource  `json:"sources"`
}

// ScraperConfig contains general scraper settings
type ScraperConfig struct {
	MaxWorkers        int    `json:"max_workers"`
	RequestsPerSecond int    `json:"requests_per_second"`
	TimeoutSeconds    int    `json:"timeout_seconds"`
	MaxRetries        int    `json:"max_retries"`
	UserAgent         string `json:"user_agent"`
}

// PerformanceMetrics tracks scraping performance
type PerformanceMetrics struct {
	StartTime        time.Time         `json:"start_time"`
	EndTime          time.Time         `json:"end_time"`
	Duration         time.Duration     `json:"duration"`
	TotalArticles    int               `json:"total_articles"`
	ArticlesPerSecond float64          `json:"articles_per_second"`
	SourceStats      map[string]int    `json:"source_stats"`
	QualityStats     map[string]int    `json:"quality_stats"`
	ErrorCount       int               `json:"error_count"`
	SuccessRate      float64           `json:"success_rate"`
	mutex            sync.RWMutex
}

// NewPerformanceMetrics creates a new performance metrics tracker
func NewPerformanceMetrics() *PerformanceMetrics {
	return &PerformanceMetrics{
		StartTime:    time.Now(),
		SourceStats:  make(map[string]int),
		QualityStats: make(map[string]int),
	}
}

// RecordArticle records an article in the metrics
func (pm *PerformanceMetrics) RecordArticle(article Article) {
	pm.mutex.Lock()
	defer pm.mutex.Unlock()
	
	pm.TotalArticles++
	pm.SourceStats[article.Source]++
	pm.QualityStats[article.ContentQuality]++
}

// RecordError records an error in the metrics
func (pm *PerformanceMetrics) RecordError() {
	pm.mutex.Lock()
	defer pm.mutex.Unlock()
	
	pm.ErrorCount++
}

// Finalize calculates final metrics
func (pm *PerformanceMetrics) Finalize(totalAttempts int) {
	pm.mutex.Lock()
	defer pm.mutex.Unlock()
	
	pm.EndTime = time.Now()
	pm.Duration = pm.EndTime.Sub(pm.StartTime)
	pm.ArticlesPerSecond = float64(pm.TotalArticles) / pm.Duration.Seconds()
	
	if totalAttempts > 0 {
		pm.SuccessRate = float64(pm.TotalArticles) / float64(totalAttempts) * 100
	}
}

// Enhanced AsyncScraper with performance monitoring
type EnhancedAsyncScraper struct {
	*AsyncScraper
	metrics *PerformanceMetrics
	config  Config
}

// NewEnhancedAsyncScraper creates a new enhanced scraper with configuration
func NewEnhancedAsyncScraper(configPath string) (*EnhancedAsyncScraper, error) {
	// Load configuration
	configFile, err := os.Open(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open config file: %v", err)
	}
	defer configFile.Close()
	
	var config Config
	if err := json.NewDecoder(configFile).Decode(&config); err != nil {
		return nil, fmt.Errorf("failed to decode config: %v", err)
	}
	
	// Create base scraper
	baseScraper := NewAsyncScraper(
		config.Scraper.MaxWorkers,
		config.Scraper.RequestsPerSecond,
	)
	baseScraper.userAgent = config.Scraper.UserAgent
	
	return &EnhancedAsyncScraper{
		AsyncScraper: baseScraper,
		metrics:      NewPerformanceMetrics(),
		config:       config,
	}, nil
}

// ScrapeAllSources scrapes all configured sources with performance monitoring
func (es *EnhancedAsyncScraper) ScrapeAllSources(ctx context.Context) error {
	log.Println("Starting enhanced async scraping of all sources")
	
	var wg sync.WaitGroup
	totalAttempts := 0
	
	// Process each source concurrently
	for _, source := range es.config.Sources {
		wg.Add(1)
		go func(src NewsSource) {
			defer wg.Done()
			
			if err := es.ScrapeSourceWithMetrics(ctx, src); err != nil {
				log.Printf("Error scraping %s: %v", src.Name, err)
				es.metrics.RecordError()
			}
		}(source)
	}
	
	// Wait for all sources to complete
	wg.Wait()
	
	// Calculate total attempts (rough estimate)
	for _, source := range es.config.Sources {
		totalAttempts += 50 // Estimate 50 articles per source
	}
	
	es.metrics.Finalize(totalAttempts)
	
	return nil
}

// ScrapeSourceWithMetrics scrapes a source and records metrics
func (es *EnhancedAsyncScraper) ScrapeSourceWithMetrics(ctx context.Context, source NewsSource) error {
	log.Printf("Starting to scrape %s with enhanced monitoring", source.Name)
	
	// Override rate limit if specified in source
	if source.RateLimit > 0 {
		es.rateLimiter = rate.NewLimiter(rate.Limit(source.RateLimit), source.RateLimit)
	}
	
	// Get article links
	links, err := es.getArticleLinks(ctx, source)
	if err != nil {
		return fmt.Errorf("failed to get article links for %s: %v", source.Name, err)
	}
	
	log.Printf("Found %d article links for %s", len(links), source.Name)
	
	// Create worker pool
	linkChan := make(chan string, len(links))
	var wg sync.WaitGroup
	
	// Start workers
	for i := 0; i < es.maxWorkers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			es.enhancedArticleWorker(ctx, linkChan, source)
		}()
	}
	
	// Send links to workers
	for _, link := range links {
		if !es.isDuplicate(link) {
			linkChan <- link
			es.markAsSeen(link)
		}
	}
	close(linkChan)
	
	// Wait for completion
	wg.Wait()
	
	log.Printf("Completed scraping %s", source.Name)
	return nil
}

// enhancedArticleWorker processes articles with metrics recording
func (es *EnhancedAsyncScraper) enhancedArticleWorker(ctx context.Context, linkChan <-chan string, source NewsSource) {
	for link := range linkChan {
		select {
		case <-ctx.Done():
			return
		default:
			article, err := es.scrapeArticle(ctx, link, source)
			if err != nil {
				log.Printf("Error scraping article %s: %v", link, err)
				es.metrics.RecordError()
				continue
			}
			
			if article != nil {
				es.addArticle(*article)
				es.metrics.RecordArticle(*article)
			}
		}
	}
}

// SaveMetrics saves performance metrics to a file
func (es *EnhancedAsyncScraper) SaveMetrics(filename string) error {
	if err := os.MkdirAll("output", 0755); err != nil {
		return err
	}
	
	file, err := os.Create(fmt.Sprintf("output/%s", filename))
	if err != nil {
		return err
	}
	defer file.Close()
	
	encoder := json.NewEncoder(file)
	encoder.SetIndent("", "  ")
	return encoder.Encode(es.metrics)
}

// PrintSummary prints a detailed performance summary
func (es *EnhancedAsyncScraper) PrintSummary() {
	log.Println("\n" + strings.Repeat("=", 50))
	log.Println("📊 ENHANCED SCRAPING PERFORMANCE SUMMARY")
	log.Println(strings.Repeat("=", 50))
	
	log.Printf("⏱️  Duration: %v", es.metrics.Duration)
	log.Printf("📰 Total Articles: %d", es.metrics.TotalArticles)
	log.Printf("🚀 Articles/Second: %.2f", es.metrics.ArticlesPerSecond)
	log.Printf("✅ Success Rate: %.1f%%", es.metrics.SuccessRate)
	log.Printf("❌ Errors: %d", es.metrics.ErrorCount)
	
	log.Println("\n📈 BY SOURCE:")
	for source, count := range es.metrics.SourceStats {
		log.Printf("  %s: %d articles", source, count)
	}
	
	log.Println("\n🏆 BY QUALITY:")
	for quality, count := range es.metrics.QualityStats {
		percentage := float64(count) / float64(es.metrics.TotalArticles) * 100
		log.Printf("  %s: %d articles (%.1f%%)", quality, count, percentage)
	}
	
	log.Println(strings.Repeat("=", 50))
}

func main() {
	log.Println("🚀 Starting NeuroNews Enhanced Async Scraper")
	
	// Create enhanced scraper with configuration
	scraper, err := NewEnhancedAsyncScraper("config.json")
	if err != nil {
		log.Fatalf("Failed to create scraper: %v", err)
	}
	
	// Create context with timeout
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Minute)
	defer cancel()
	
	// Start scraping
	if err := scraper.ScrapeAllSources(ctx); err != nil {
		log.Printf("Error during scraping: %v", err)
	}
	
	// Get results
	articles := scraper.getArticles()
	log.Printf("✅ Successfully scraped %d articles", len(articles))
	
	// Save results with timestamp
	timestamp := time.Now().Format("2006-01-02_15-04-05")
	articlesFile := fmt.Sprintf("async_scraped_articles_%s.json", timestamp)
	metricsFile := fmt.Sprintf("scraping_metrics_%s.json", timestamp)
	
	if err := scraper.SaveArticles(articlesFile); err != nil {
		log.Printf("❌ Error saving articles: %v", err)
	} else {
		log.Printf("💾 Articles saved to output/%s", articlesFile)
	}
	
	if err := scraper.SaveMetrics(metricsFile); err != nil {
		log.Printf("❌ Error saving metrics: %v", err)
	} else {
		log.Printf("📊 Metrics saved to output/%s", metricsFile)
	}
	
	// Print detailed summary
	scraper.PrintSummary()
}
