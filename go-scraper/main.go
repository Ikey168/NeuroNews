package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/go-resty/resty/v2"
	"golang.org/x/time/rate"
)

// Article represents a scraped news article
type Article struct {
	Title         string    `json:"title"`
	URL           string    `json:"url"`
	Content       string    `json:"content"`
	PublishedDate string    `json:"published_date"`
	Source        string    `json:"source"`
	Author        string    `json:"author"`
	Category      string    `json:"category"`
	ScrapedDate   time.Time `json:"scraped_date"`
	ContentLength int       `json:"content_length"`
	WordCount     int       `json:"word_count"`
	ReadingTime   int       `json:"reading_time"`
	Language      string    `json:"language"`
	ValidationScore int     `json:"validation_score"`
	ContentQuality string   `json:"content_quality"`
	DuplicateCheck string   `json:"duplicate_check"`
}

// NewsSource represents a news source configuration
type NewsSource struct {
	Name           string            `json:"name"`
	BaseURL        string            `json:"base_url"`
	ArticleSelectors map[string]string `json:"article_selectors"`
	LinkPatterns   []string          `json:"link_patterns"`
	RequiresJS     bool              `json:"requires_js"`
	RateLimit      int               `json:"rate_limit"` // requests per second
}

// AsyncScraper handles concurrent web scraping operations
type AsyncScraper struct {
	client       *resty.Client
	rateLimiter  *rate.Limiter
	maxWorkers   int
	timeout      time.Duration
	userAgent    string
	seenURLs     map[string]bool
	seenMutex    sync.RWMutex
	articles     []Article
	articleMutex sync.Mutex
}

// NewAsyncScraper creates a new asynchronous scraper instance
func NewAsyncScraper(maxWorkers int, requestsPerSecond int) *AsyncScraper {
	client := resty.New()
	client.SetTimeout(30 * time.Second)
	client.SetRetryCount(3)
	client.SetRetryWaitTime(1 * time.Second)
	
	return &AsyncScraper{
		client:      client,
		rateLimiter: rate.NewLimiter(rate.Limit(requestsPerSecond), requestsPerSecond),
		maxWorkers:  maxWorkers,
		timeout:     30 * time.Second,
		userAgent:   "NeuroNews-AsyncScraper/1.0 (+https://github.com/Ikey168/NeuroNews)",
		seenURLs:    make(map[string]bool),
		articles:    make([]Article, 0),
	}
}

// isDuplicate checks if a URL has already been processed
func (s *AsyncScraper) isDuplicate(url string) bool {
	s.seenMutex.RLock()
	defer s.seenMutex.RUnlock()
	return s.seenURLs[url]
}

// markAsSeen marks a URL as processed
func (s *AsyncScraper) markAsSeen(url string) {
	s.seenMutex.Lock()
	defer s.seenMutex.Unlock()
	s.seenURLs[url] = true
}

// addArticle safely adds an article to the results
func (s *AsyncScraper) addArticle(article Article) {
	s.articleMutex.Lock()
	defer s.articleMutex.Unlock()
	s.articles = append(s.articles, article)
}

// getArticles returns all scraped articles
func (s *AsyncScraper) getArticles() []Article {
	s.articleMutex.Lock()
	defer s.articleMutex.Unlock()
	return append([]Article(nil), s.articles...) // Return a copy
}

// ScrapeSource scrapes articles from a specific news source
func (s *AsyncScraper) ScrapeSource(ctx context.Context, source NewsSource) error {
	log.Printf("Starting to scrape %s (%s)", source.Name, source.BaseURL)
	
	// Get article links from the main page
	links, err := s.getArticleLinks(ctx, source)
	if err != nil {
		return fmt.Errorf("failed to get article links for %s: %v", source.Name, err)
	}
	
	log.Printf("Found %d article links for %s", len(links), source.Name)
	
	// Create worker pool for concurrent scraping
	linkChan := make(chan string, len(links))
	var wg sync.WaitGroup
	
	// Start workers
	for i := 0; i < s.maxWorkers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			s.articleWorker(ctx, linkChan, source)
		}()
	}
	
	// Send links to workers
	for _, link := range links {
		if !s.isDuplicate(link) {
			linkChan <- link
			s.markAsSeen(link)
		}
	}
	close(linkChan)
	
	// Wait for all workers to complete
	wg.Wait()
	
	log.Printf("Completed scraping %s", source.Name)
	return nil
}

// getArticleLinks extracts article URLs from a news source's main page
func (s *AsyncScraper) getArticleLinks(ctx context.Context, source NewsSource) ([]string, error) {
	// Rate limiting
	if err := s.rateLimiter.Wait(ctx); err != nil {
		return nil, err
	}
	
	resp, err := s.client.R().
		SetHeader("User-Agent", s.userAgent).
		Get(source.BaseURL)
	
	if err != nil {
		return nil, err
	}
	
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(resp.String()))
	if err != nil {
		return nil, err
	}
	
	var links []string
	linkMap := make(map[string]bool) // To avoid duplicates
	
	// Extract links based on patterns
	doc.Find("a[href]").Each(func(i int, sel *goquery.Selection) {
		href, exists := sel.Attr("href")
		if !exists {
			return
		}
		
		// Convert relative URLs to absolute
		if strings.HasPrefix(href, "/") {
			href = strings.TrimSuffix(source.BaseURL, "/") + href
		}
		
		// Check if link matches any of the patterns
		for _, pattern := range source.LinkPatterns {
			matched, _ := regexp.MatchString(pattern, href)
			if matched && !linkMap[href] {
				links = append(links, href)
				linkMap[href] = true
				break
			}
		}
	})
	
	return links, nil
}

// articleWorker processes article URLs from the channel
func (s *AsyncScraper) articleWorker(ctx context.Context, linkChan <-chan string, source NewsSource) {
	for link := range linkChan {
		select {
		case <-ctx.Done():
			return
		default:
			article, err := s.scrapeArticle(ctx, link, source)
			if err != nil {
				log.Printf("Error scraping article %s: %v", link, err)
				continue
			}
			
			if article != nil {
				s.addArticle(*article)
			}
		}
	}
}

// scrapeArticle extracts article content from a URL
func (s *AsyncScraper) scrapeArticle(ctx context.Context, url string, source NewsSource) (*Article, error) {
	// Rate limiting
	if err := s.rateLimiter.Wait(ctx); err != nil {
		return nil, err
	}
	
	resp, err := s.client.R().
		SetHeader("User-Agent", s.userAgent).
		Get(url)
	
	if err != nil {
		return nil, err
	}
	
	if resp.StatusCode() != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d for URL %s", resp.StatusCode(), url)
	}
	
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(resp.String()))
	if err != nil {
		return nil, err
	}
	
	article := &Article{
		URL:         url,
		Source:      source.Name,
		ScrapedDate: time.Now(),
		Language:    "en",
	}
	
	// Extract title
	if titleSelector, exists := source.ArticleSelectors["title"]; exists {
		article.Title = strings.TrimSpace(doc.Find(titleSelector).First().Text())
	}
	
	// Extract content
	if contentSelector, exists := source.ArticleSelectors["content"]; exists {
		var contentParts []string
		doc.Find(contentSelector).Each(func(i int, sel *goquery.Selection) {
			text := strings.TrimSpace(sel.Text())
			if text != "" {
				contentParts = append(contentParts, text)
			}
		})
		article.Content = strings.Join(contentParts, " ")
	}
	
	// Extract author
	if authorSelector, exists := source.ArticleSelectors["author"]; exists {
		article.Author = strings.TrimSpace(doc.Find(authorSelector).First().Text())
	}
	if article.Author == "" {
		article.Author = source.Name + " Staff"
	}
	
	// Extract publication date
	if dateSelector, exists := source.ArticleSelectors["date"]; exists {
		dateText := strings.TrimSpace(doc.Find(dateSelector).First().Text())
		if dateAttr, hasAttr := doc.Find(dateSelector).First().Attr("datetime"); hasAttr {
			dateText = dateAttr
		}
		article.PublishedDate = dateText
	}
	
	// Extract category from URL or content
	article.Category = s.extractCategory(url, doc)
	
	// Calculate metrics
	article.ContentLength = len(article.Content)
	article.WordCount = len(strings.Fields(article.Content))
	article.ReadingTime = max(1, article.WordCount/200) // 200 words per minute
	
	// Validate article
	article.ValidationScore = s.validateArticle(article)
	if article.ValidationScore >= 80 {
		article.ContentQuality = "high"
	} else if article.ValidationScore >= 60 {
		article.ContentQuality = "medium"
	} else {
		article.ContentQuality = "low"
	}
	
	article.DuplicateCheck = "unique"
	
	// Only return articles that meet minimum quality standards
	if article.ValidationScore >= 50 && article.Title != "" && article.ContentLength > 100 {
		return article, nil
	}
	
	return nil, nil // Article doesn't meet quality standards
}

// extractCategory attempts to determine article category
func (s *AsyncScraper) extractCategory(url string, doc *goquery.Document) string {
	urlLower := strings.ToLower(url)
	
	categories := map[string][]string{
		"Technology": {"tech", "technology", "gadgets", "ai", "artificial-intelligence"},
		"Politics":   {"politics", "political", "government", "election"},
		"Business":   {"business", "finance", "economy", "market"},
		"Sports":     {"sports", "sport", "football", "basketball", "soccer"},
		"Health":     {"health", "medical", "medicine", "wellness"},
		"Science":    {"science", "research", "study", "scientific"},
		"Entertainment": {"entertainment", "celebrity", "music", "movies"},
	}
	
	for category, keywords := range categories {
		for _, keyword := range keywords {
			if strings.Contains(urlLower, keyword) {
				return category
			}
		}
	}
	
	// Try to extract from breadcrumbs or page structure
	breadcrumb := doc.Find(".breadcrumb, nav[aria-label*='breadcrumb'] a, .category").First().Text()
	if breadcrumb != "" {
		return strings.TrimSpace(breadcrumb)
	}
	
	return "News"
}

// validateArticle calculates a validation score for the article
func (s *AsyncScraper) validateArticle(article *Article) int {
	score := 100
	
	// Check required fields
	if article.Title == "" {
		score -= 25
	}
	if article.URL == "" {
		score -= 25
	}
	if article.Content == "" {
		score -= 30
	}
	if article.Source == "" {
		score -= 20
	}
	
	// Check content quality
	if article.ContentLength < 100 {
		score -= 20
	} else if article.ContentLength > 10000 {
		score -= 5
	}
	
	// Check title length
	if len(article.Title) < 10 || len(article.Title) > 200 {
		score -= 10
	}
	
	return max(0, score)
}

// max returns the larger of two integers
func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

// SaveArticles saves scraped articles to a JSON file
func (s *AsyncScraper) SaveArticles(filename string) error {
	articles := s.getArticles()
	
	// Create output directory if it doesn't exist
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
	return encoder.Encode(articles)
}

// getDefaultSources returns a set of pre-configured news sources
func getDefaultSources() []NewsSource {
	return []NewsSource{
		{
			Name:    "CNN",
			BaseURL: "https://www.cnn.com",
			ArticleSelectors: map[string]string{
				"title":   "h1.headline__text, h1",
				"content": ".zn-body__paragraph, .zn-body__paragraph p, div[data-component-name='ArticleBody'] p",
				"author":  ".byline__name, .metadata__byline__author",
				"date":    ".timestamp, .update-time, time",
			},
			LinkPatterns: []string{
				`/2024/\d+/\d+/.*\.html`,
				`/2025/\d+/\d+/.*\.html`,
			},
			RequiresJS: false,
			RateLimit:  2,
		},
		{
			Name:    "BBC",
			BaseURL: "https://www.bbc.com/news",
			ArticleSelectors: map[string]string{
				"title":   "h1[data-testid='headline'], h1.story-headline, h1",
				"content": "div[data-component='text-block'] p, .story-body__inner p, article p",
				"author":  "div[data-testid='byline-name'], .byline__name",
				"date":    "time, div[data-testid='timestamp'], .date",
			},
			LinkPatterns: []string{
				`/news/[a-z-]+-\d+`,
			},
			RequiresJS: false,
			RateLimit:  2,
		},
		{
			Name:    "Reuters",
			BaseURL: "https://www.reuters.com",
			ArticleSelectors: map[string]string{
				"title":   "h1[data-testid='Heading'], h1.ArticleHeader_headline, h1",
				"content": "div[data-testid='paragraph'] p, .StandardArticleBody_body p, article p",
				"author":  "div[data-testid='BylineBar'] a, .byline a",
				"date":    "time, span[data-testid='Body'] time",
			},
			LinkPatterns: []string{
				`/article/.*`,
			},
			RequiresJS: false,
			RateLimit:  1,
		},
		{
			Name:    "TechCrunch",
			BaseURL: "https://techcrunch.com",
			ArticleSelectors: map[string]string{
				"title":   "h1.article__title, h1.entry-title, h1",
				"content": ".article-content p, .entry-content p, div[class*='articleContent'] p",
				"author":  ".byline a[rel='author'], .article__byline a",
				"date":    "time.full-date-time, .byline time",
			},
			LinkPatterns: []string{
				`/2024/\d+/\d+/.*`,
				`/2025/\d+/\d+/.*`,
			},
			RequiresJS: false,
			RateLimit:  2,
		},
	}
}

func main() {
	log.Println("Starting NeuroNews Async Scraper")
	
	// Create scraper with 10 concurrent workers and 5 requests per second
	scraper := NewAsyncScraper(10, 5)
	
	// Create context with timeout
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()
	
	// Get news sources
	sources := getDefaultSources()
	
	// Start scraping each source concurrently
	var wg sync.WaitGroup
	for _, source := range sources {
		wg.Add(1)
		go func(src NewsSource) {
			defer wg.Done()
			if err := scraper.ScrapeSource(ctx, src); err != nil {
				log.Printf("Error scraping %s: %v", src.Name, err)
			}
		}(source)
	}
	
	// Wait for all sources to complete
	wg.Wait()
	
	// Get results
	articles := scraper.getArticles()
	log.Printf("Successfully scraped %d articles", len(articles))
	
	// Save results
	filename := fmt.Sprintf("scraped_articles_%s.json", time.Now().Format("2006-01-02_15-04-05"))
	if err := scraper.SaveArticles(filename); err != nil {
		log.Printf("Error saving articles: %v", err)
	} else {
		log.Printf("Articles saved to output/%s", filename)
	}
	
	// Print summary statistics
	sources_stats := make(map[string]int)
	quality_stats := make(map[string]int)
	
	for _, article := range articles {
		sources_stats[article.Source]++
		quality_stats[article.ContentQuality]++
	}
	
	log.Println("\n=== Scraping Summary ===")
	log.Printf("Total articles: %d", len(articles))
	log.Println("\nBy source:")
	for source, count := range sources_stats {
		log.Printf("  %s: %d articles", source, count)
	}
	log.Println("\nBy quality:")
	for quality, count := range quality_stats {
		log.Printf("  %s: %d articles", quality, count)
	}
}
