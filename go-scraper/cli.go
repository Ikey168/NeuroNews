package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// CLI represents command-line interface
type CLI struct {
	configFile     string
	outputDir      string
	sources        string
	workers        int
	rateLimit      float64
	timeout        time.Duration
	jsMode         bool
	verbose        bool
	testMode       bool
}

// parseCLI parses command-line arguments
func parseCLI() *CLI {
	cli := &CLI{}
	
	flag.StringVar(&cli.configFile, "config", "config.json", "Configuration file path")
	flag.StringVar(&cli.outputDir, "output", "output", "Output directory for scraped articles")
	flag.StringVar(&cli.sources, "sources", "", "Comma-separated list of sources to scrape (leave empty for all)")
	flag.IntVar(&cli.workers, "workers", 0, "Number of concurrent workers (0 = use config default)")
	flag.Float64Var(&cli.rateLimit, "rate", 0, "Rate limit requests per second (0 = use config default)")
	flag.DurationVar(&cli.timeout, "timeout", 0, "Timeout for requests (0 = use config default)")
	flag.BoolVar(&cli.jsMode, "js", false, "Enable JavaScript-heavy scraping mode")
	flag.BoolVar(&cli.verbose, "verbose", false, "Enable verbose logging")
	flag.BoolVar(&cli.testMode, "test", false, "Run in test mode with limited sources")
	
	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "NeuroNews Go Async Scraper\n\n")
		fmt.Fprintf(os.Stderr, "Usage: %s [options]\n\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "Options:\n")
		flag.PrintDefaults()
		fmt.Fprintf(os.Stderr, "\nExamples:\n")
		fmt.Fprintf(os.Stderr, "  %s -config config.json\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s -sources \"BBC,CNN\" -workers 5\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s -js -verbose\n", os.Args[0])
		fmt.Fprintf(os.Stderr, "  %s -test\n", os.Args[0])
	}
	
	flag.Parse()
	return cli
}

// runScraper executes the scraping based on CLI arguments
func runScraper(cli *CLI) error {
	// Setup logging
	if cli.verbose {
		log.SetFlags(log.LstdFlags | log.Lshortfile)
	}
	
	log.Println("🚀 Starting NeuroNews Go Async Scraper")
	
	// Load configuration
	config, err := LoadConfig(cli.configFile)
	if err != nil {
		return fmt.Errorf("failed to load config: %v", err)
	}
	
	// Override config with CLI arguments
	if cli.outputDir != "" {
		config.OutputDir = cli.outputDir
	}
	if cli.workers > 0 {
		config.MaxWorkers = cli.workers
	}
	if cli.rateLimit > 0 {
		config.RateLimit = cli.rateLimit
	}
	if cli.timeout > 0 {
		config.Timeout = cli.timeout
	}
	
	// Create output directory
	if err := os.MkdirAll(config.OutputDir, 0755); err != nil {
		return fmt.Errorf("failed to create output directory: %v", err)
	}
	
	// Filter sources if specified
	var sourcesToScrape []NewsSource
	if cli.testMode {
		sourcesToScrape = getTestSources()
		log.Println("📝 Running in test mode with limited sources")
	} else if cli.sources != "" {
		sourcesToScrape = filterSources(config.Sources, cli.sources)
		log.Printf("🎯 Scraping selected sources: %s", cli.sources)
	} else {
		sourcesToScrape = config.Sources
		log.Printf("🌍 Scraping all %d configured sources", len(config.Sources))
	}
	
	if len(sourcesToScrape) == 0 {
		return fmt.Errorf("no sources to scrape")
	}
	
	// Create context with timeout
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()
	
	// Run appropriate scraper
	if cli.jsMode {
		return runJSScrapingMode(ctx, sourcesToScrape, config)
	} else {
		return runAsyncScrapingMode(ctx, sourcesToScrape, config)
	}
}

// runAsyncScrapingMode runs the regular async scraper
func runAsyncScrapingMode(ctx context.Context, sources []NewsSource, config *Config) error {
	log.Println("⚡ Using Async HTTP Scraper")
	
	scraper := NewAsyncScraper(config, sources)
	
	// Start scraping
	startTime := time.Now()
	err := scraper.ScrapeAllSources(ctx)
	duration := time.Since(startTime)
	
	// Get final metrics
	metrics := scraper.GetMetrics()
	
	// Display results
	log.Println("\n" + strings.Repeat("=", 50))
	log.Println("📊 SCRAPING RESULTS")
	log.Println(strings.Repeat("=", 50))
	log.Printf("⏱️  Total Duration: %v", duration)
	log.Printf("📰 Total Articles: %d", metrics.TotalArticles)
	log.Printf("✅ Successful Scrapes: %d", metrics.SuccessfulScrapes)
	log.Printf("❌ Failed Scrapes: %d", metrics.FailedScrapes)
	log.Printf("📈 Articles/Second: %.2f", metrics.ArticlesPerSecond)
	log.Printf("🎯 Success Rate: %.1f%%", metrics.SuccessRate)
	
	// Display source-specific stats
	log.Println("\n📋 Source Statistics:")
	for source, stats := range metrics.SourceStats {
		log.Printf("  %s: %d articles", source, stats.ArticleCount)
	}
	
	if err != nil {
		log.Printf("⚠️  Scraper completed with errors: %v", err)
	} else {
		log.Println("🎉 Scraping completed successfully!")
	}
	
	return err
}

// runJSScrapingMode runs the JavaScript-heavy scraper
func runJSScrapingMode(ctx context.Context, sources []NewsSource, config *Config) error {
	log.Println("🌐 Using JavaScript-Heavy Browser Scraper")
	
	jsScraper := NewJSHeavyScraper(config.ConcurrentBrowsers)
	
	startTime := time.Now()
	
	// Filter JS-required sources
	jsSources := []NewsSource{}
	for _, source := range sources {
		if source.RequiresJS {
			jsSources = append(jsSources, source)
		}
	}
	
	if len(jsSources) == 0 {
		log.Println("⚠️  No JavaScript-heavy sources found in configuration")
		return nil
	}
	
	log.Printf("🎯 Scraping %d JavaScript-heavy sources", len(jsSources))
	
	// Scrape JS sources sequentially to avoid browser conflicts
	for _, source := range jsSources {
		log.Printf("🔄 Processing %s...", source.Name)
		if err := jsScraper.ScrapeJSHeavySite(ctx, source); err != nil {
			log.Printf("❌ Error scraping %s: %v", source.Name, err)
		}
	}
	
	duration := time.Since(startTime)
	articles := jsScraper.getArticles()
	
	// Save results
	filename := fmt.Sprintf("js_scraped_articles_%s.json", time.Now().Format("2006-01-02_15-04-05"))
	if err := jsScraper.SaveJSArticles(filename); err != nil {
		log.Printf("❌ Error saving articles: %v", err)
	}
	
	// Display results
	log.Println("\n" + strings.Repeat("=", 50))
	log.Println("📊 JS SCRAPING RESULTS")
	log.Println(strings.Repeat("=", 50))
	log.Printf("⏱️  Total Duration: %v", duration)
	log.Printf("📰 Total Articles: %d", len(articles))
	log.Printf("📈 Articles/Minute: %.1f", float64(len(articles))/duration.Minutes())
	log.Printf("💾 Results saved to: output/%s", filename)
	
	log.Println("🎉 JavaScript scraping completed!")
	return nil
}

// filterSources filters sources based on comma-separated list
func filterSources(allSources []NewsSource, sourceNames string) []NewsSource {
	names := strings.Split(sourceNames, ",")
	nameMap := make(map[string]bool)
	for _, name := range names {
		nameMap[strings.TrimSpace(name)] = true
	}
	
	var filtered []NewsSource
	for _, source := range allSources {
		if nameMap[source.Name] {
			filtered = append(filtered, source)
		}
	}
	
	return filtered
}

// getTestSources returns a small set of sources for testing
func getTestSources() []NewsSource {
	return []NewsSource{
		{
			Name:    "Reuters Test",
			BaseURL: "https://www.reuters.com",
			ArticleSelectors: map[string]string{
				"title":   "h1[data-testid='Headline'], h1",
				"content": "div[data-testid='ArticleBody'] p",
				"author":  "a[data-testid='Author']",
				"date":    "time[datetime]",
			},
			LinkPatterns: []string{`/world/.*`},
			RequiresJS:   false,
			RateLimit:    2,
		},
		{
			Name:    "BBC Test",
			BaseURL: "https://www.bbc.com/news",
			ArticleSelectors: map[string]string{
				"title":   "h1[data-testid='headline']",
				"content": "div[data-component='text-block'] p",
				"author":  "span[data-testid='byline']",
				"date":    "time[datetime]",
			},
			LinkPatterns: []string{`/news/.*`},
			RequiresJS:   false,
			RateLimit:    2,
		},
	}
}

// printBanner displays application banner
func printBanner() {
	banner := `
    ╔═══════════════════════════════════════════════╗
    ║           NeuroNews Go Async Scraper          ║
    ║        High-Performance News Collection       ║
    ╚═══════════════════════════════════════════════╝
    `
	fmt.Println(banner)
}

// checkDependencies verifies required dependencies
func checkDependencies() error {
	// Check if output directory can be created
	testDir := "temp_test_dir"
	if err := os.MkdirAll(testDir, 0755); err != nil {
		return fmt.Errorf("cannot create directories: %v", err)
	}
	os.RemoveAll(testDir)
	
	// Check if config file exists (if specified)
	configFile := "config.json"
	if len(os.Args) > 1 {
		for i, arg := range os.Args {
			if arg == "-config" && i+1 < len(os.Args) {
				configFile = os.Args[i+1]
				break
			}
		}
	}
	
	if _, err := os.Stat(configFile); err != nil {
		log.Printf("⚠️  Config file %s not found, will use defaults", configFile)
	}
	
	return nil
}

func main() {
	printBanner()
	
	// Check dependencies
	if err := checkDependencies(); err != nil {
		log.Fatalf("❌ Dependency check failed: %v", err)
	}
	
	// Parse CLI arguments
	cli := parseCLI()
	
	// Run scraper
	if err := runScraper(cli); err != nil {
		log.Fatalf("❌ Scraper failed: %v", err)
	}
	
	log.Println("👋 NeuroNews scraper finished successfully!")
}
