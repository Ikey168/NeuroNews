package main

import (
	"context"
	"fmt"
	"log"
	"strings"
	"sync"
	"time"

	"github.com/chromedp/chromedp"
)

// JSHeavyScraper handles JavaScript-heavy sites using headless Chrome
type JSHeavyScraper struct {
	maxBrowsers int
	timeout     time.Duration
	articles    []Article
	mutex       sync.Mutex
}

// NewJSHeavyScraper creates a new JavaScript-heavy scraper
func NewJSHeavyScraper(maxBrowsers int) *JSHeavyScraper {
	return &JSHeavyScraper{
		maxBrowsers: maxBrowsers,
		timeout:     60 * time.Second,
		articles:    make([]Article, 0),
	}
}

// addArticle safely adds an article to the results
func (js *JSHeavyScraper) addArticle(article Article) {
	js.mutex.Lock()
	defer js.mutex.Unlock()
	js.articles = append(js.articles, article)
}

// getArticles returns all scraped articles
func (js *JSHeavyScraper) getArticles() []Article {
	js.mutex.Lock()
	defer js.mutex.Unlock()
	return append([]Article(nil), js.articles...) // Return a copy
}

// ScrapeJSHeavySite scrapes a JavaScript-heavy news site
func (js *JSHeavyScraper) ScrapeJSHeavySite(ctx context.Context, source NewsSource) error {
	log.Printf("Starting JavaScript-heavy scraping for %s", source.Name)
	
	// Create browser context
	opts := append(chromedp.DefaultExecAllocatorOptions[:],
		chromedp.Flag("headless", true),
		chromedp.Flag("disable-gpu", true),
		chromedp.Flag("no-sandbox", true),
		chromedp.Flag("disable-dev-shm-usage", true),
		chromedp.UserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"),
	)
	
	allocCtx, cancel := chromedp.NewExecAllocator(ctx, opts...)
	defer cancel()
	
	// Get article links using browser
	links, err := js.getJSArticleLinks(allocCtx, source)
	if err != nil {
		return fmt.Errorf("failed to get JS article links for %s: %v", source.Name, err)
	}
	
	log.Printf("Found %d article links for %s", len(links), source.Name)
	
	// Process articles with browser pool
	linkChan := make(chan string, len(links))
	var wg sync.WaitGroup
	
	// Start browser workers
	for i := 0; i < js.maxBrowsers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			js.browserWorker(allocCtx, linkChan, source)
		}()
	}
	
	// Send links to workers
	for _, link := range links {
		linkChan <- link
	}
	close(linkChan)
	
	// Wait for completion
	wg.Wait()
	
	log.Printf("Completed JavaScript-heavy scraping for %s", source.Name)
	return nil
}

// getJSArticleLinks extracts article links using headless browser
func (js *JSHeavyScraper) getJSArticleLinks(allocCtx context.Context, source NewsSource) ([]string, error) {
	ctx, cancel := chromedp.NewContext(allocCtx)
	defer cancel()
	
	ctx, cancel = context.WithTimeout(ctx, js.timeout)
	defer cancel()
	
	var links []string
	
	err := chromedp.Run(ctx,
		chromedp.Navigate(source.BaseURL),
		chromedp.Sleep(3*time.Second), // Wait for content to load
		chromedp.Evaluate(`
			Array.from(document.querySelectorAll('a[href]')).map(a => a.href)
			.filter(href => {
				const patterns = `+fmt.Sprintf("%q", source.LinkPatterns)+`;
				return patterns.some(pattern => new RegExp(pattern).test(href));
			});
		`, &links),
	)
	
	if err != nil {
		return nil, err
	}
	
	// Remove duplicates
	linkMap := make(map[string]bool)
	uniqueLinks := []string{}
	for _, link := range links {
		if !linkMap[link] {
			uniqueLinks = append(uniqueLinks, link)
			linkMap[link] = true
		}
	}
	
	return uniqueLinks, nil
}

// browserWorker processes article URLs using headless browser
func (js *JSHeavyScraper) browserWorker(allocCtx context.Context, linkChan <-chan string, source NewsSource) {
	ctx, cancel := chromedp.NewContext(allocCtx)
	defer cancel()
	
	for link := range linkChan {
		article, err := js.scrapeJSArticle(ctx, link, source)
		if err != nil {
			log.Printf("Error scraping JS article %s: %v", link, err)
			continue
		}
		
		if article != nil {
			js.addArticle(*article)
		}
	}
}

// scrapeJSArticle extracts article content using headless browser
func (js *JSHeavyScraper) scrapeJSArticle(ctx context.Context, url string, source NewsSource) (*Article, error) {
	ctx, cancel := context.WithTimeout(ctx, js.timeout)
	defer cancel()
	
	var title, content, author, date string
	
	err := chromedp.Run(ctx,
		chromedp.Navigate(url),
		chromedp.Sleep(2*time.Second), // Wait for content to load
		
		// Extract title
		chromedp.Evaluate(fmt.Sprintf(`
			const titleElement = document.querySelector('%s');
			titleElement ? titleElement.textContent.trim() : '';
		`, source.ArticleSelectors["title"]), &title),
		
		// Extract content
		chromedp.Evaluate(fmt.Sprintf(`
			const contentElements = document.querySelectorAll('%s');
			Array.from(contentElements).map(el => el.textContent.trim()).join(' ');
		`, source.ArticleSelectors["content"]), &content),
		
		// Extract author
		chromedp.Evaluate(fmt.Sprintf(`
			const authorElement = document.querySelector('%s');
			authorElement ? authorElement.textContent.trim() : '';
		`, source.ArticleSelectors["author"]), &author),
		
		// Extract date
		chromedp.Evaluate(fmt.Sprintf(`
			const dateElement = document.querySelector('%s');
			if (dateElement) {
				return dateElement.getAttribute('datetime') || dateElement.textContent.trim();
			}
			return '';
		`, source.ArticleSelectors["date"]), &date),
	)
	
	if err != nil {
		return nil, err
	}
	
	// Create article
	article := &Article{
		Title:         title,
		URL:           url,
		Content:       content,
		Author:        author,
		PublishedDate: date,
		Source:        source.Name,
		ScrapedDate:   time.Now(),
		Language:      "en",
	}
	
	if article.Author == "" {
		article.Author = source.Name + " Staff"
	}
	
	// Calculate metrics
	article.ContentLength = len(article.Content)
	article.WordCount = len(strings.Fields(article.Content))
	article.ReadingTime = max(1, article.WordCount/200)
	
	// Extract category
	article.Category = extractCategoryFromURL(url)
	
	// Validate article
	article.ValidationScore = validateArticleQuality(article)
	if article.ValidationScore >= 80 {
		article.ContentQuality = "high"
	} else if article.ValidationScore >= 60 {
		article.ContentQuality = "medium"
	} else {
		article.ContentQuality = "low"
	}
	
	article.DuplicateCheck = "unique"
	
	// Only return articles that meet quality standards
	if article.ValidationScore >= 50 && article.Title != "" && article.ContentLength > 100 {
		return article, nil
	}
	
	return nil, nil
}

// extractCategoryFromURL extracts category from URL
func extractCategoryFromURL(url string) string {
	urlLower := strings.ToLower(url)
	
	categories := map[string][]string{
		"Technology": {"tech", "technology", "gadgets", "ai"},
		"Politics":   {"politics", "political", "government"},
		"Business":   {"business", "finance", "economy"},
		"Sports":     {"sports", "sport"},
		"Health":     {"health", "medical"},
		"Science":    {"science", "research"},
	}
	
	for category, keywords := range categories {
		for _, keyword := range keywords {
			if strings.Contains(urlLower, keyword) {
				return category
			}
		}
	}
	
	return "News"
}

// validateArticleQuality validates article quality
func validateArticleQuality(article *Article) int {
	score := 100
	
	if article.Title == "" {
		score -= 25
	}
	if article.Content == "" {
		score -= 30
	}
	if article.ContentLength < 100 {
		score -= 20
	}
	if len(article.Title) < 10 {
		score -= 10
	}
	
	return max(0, score)
}

// SaveJSArticles saves articles scraped by JS scraper
func (js *JSHeavyScraper) SaveJSArticles(filename string) error {
	articles := js.getArticles()
	
	file, err := os.Create(fmt.Sprintf("output/%s", filename))
	if err != nil {
		return err
	}
	defer file.Close()
	
	encoder := json.NewEncoder(file)
	encoder.SetIndent("", "  ")
	return encoder.Encode(articles)
}

// getJSHeavySources returns sources that require JavaScript
func getJSHeavySources() []NewsSource {
	return []NewsSource{
		{
			Name:    "The Verge",
			BaseURL: "https://www.theverge.com",
			ArticleSelectors: map[string]string{
				"title":   "h1.c-page-title, h1[data-testid='ArticleTitle'], h1",
				"content": ".c-entry-content p, div[data-testid='ArticleBody'] p, article p",
				"author":  ".c-byline__author-name, span[data-testid='BylineAuthor']",
				"date":    "time[datetime]",
			},
			LinkPatterns: []string{
				`/2024/\d+/\d+/.*`,
				`/2025/\d+/\d+/.*`,
			},
			RequiresJS: true,
			RateLimit:  1,
		},
		{
			Name:    "Wired",
			BaseURL: "https://www.wired.com",
			ArticleSelectors: map[string]string{
				"title":   "h1[data-testid='ContentHeaderHed'], h1.content-header__hed, h1",
				"content": "div[data-testid='ArticleBodyWrapper'] p, .article__body p, article p",
				"author":  "a[data-testid='ContentHeaderAuthorLink'], .byline__name",
				"date":    "time[data-testid='ContentHeaderPublishDate'], time",
			},
			LinkPatterns: []string{
				`/story/.*`,
			},
			RequiresJS: true,
			RateLimit:  1,
		},
	}
}

func runJSHeavyScraper() {
	log.Println("🌐 Starting JavaScript-Heavy Scraper")
	
	scraper := NewJSHeavyScraper(3) // 3 concurrent browsers
	
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()
	
	sources := getJSHeavySources()
	var wg sync.WaitGroup
	
	for _, source := range sources {
		wg.Add(1)
		go func(src NewsSource) {
			defer wg.Done()
			if err := scraper.ScrapeJSHeavySite(ctx, src); err != nil {
				log.Printf("Error scraping JS site %s: %v", src.Name, err)
			}
		}(source)
	}
	
	wg.Wait()
	
	articles := scraper.getArticles()
	log.Printf("🎉 JavaScript scraper collected %d articles", len(articles))
	
	// Save JS articles
	filename := fmt.Sprintf("js_scraped_articles_%s.json", time.Now().Format("2006-01-02_15-04-05"))
	if err := scraper.SaveJSArticles(filename); err != nil {
		log.Printf("❌ Error saving JS articles: %v", err)
	} else {
		log.Printf("💾 JS articles saved to output/%s", filename)
	}
}
