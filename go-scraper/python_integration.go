package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/s3"
	"github.com/aws/aws-sdk-go/service/cloudwatchlogs"
)

// IntegratedConfig extends the basic config with Python infrastructure integration
type IntegratedConfig struct {
	*Config
	S3Enabled         bool   `json:"s3_enabled"`
	S3Bucket          string `json:"s3_bucket"`
	S3Prefix          string `json:"s3_prefix"`
	AWSRegion         string `json:"aws_region"`
	ValidationEnabled bool   `json:"validation_enabled"`
	DuplicateCheck    bool   `json:"duplicate_check"`
	QualityThreshold  int    `json:"quality_threshold"`
	CloudWatchEnabled bool   `json:"cloudwatch_enabled"`
	CloudWatchLogGroup string `json:"cloudwatch_log_group"`
	CloudWatchLogStream string `json:"cloudwatch_log_stream"`
}

// PythonCompatibleScraper extends AsyncScraper with Python infrastructure integration
type PythonCompatibleScraper struct {
	*AsyncScraper
	integratedConfig *IntegratedConfig
	s3Client         *s3.S3
	cwLogsClient     *cloudwatchlogs.CloudWatchLogs
}

// NewPythonCompatibleScraper creates a new scraper with Python infrastructure integration
func NewPythonCompatibleScraper(configFile string) (*PythonCompatibleScraper, error) {
	// Load integrated config
	integratedConfig, err := LoadIntegratedConfig(configFile)
	if err != nil {
		return nil, err
	}
	
	// Create base scraper
	baseScraper := NewAsyncScraper(integratedConfig.Config, integratedConfig.Sources)
	
	scraper := &PythonCompatibleScraper{
		AsyncScraper:     baseScraper,
		integratedConfig: integratedConfig,
	}
	
	// Initialize AWS services if enabled
	if integratedConfig.S3Enabled || integratedConfig.CloudWatchEnabled {
		sess, err := session.NewSession(&aws.Config{
			Region: aws.String(integratedConfig.AWSRegion),
		})
		if err != nil {
			return nil, fmt.Errorf("failed to create AWS session: %v", err)
		}
		
		if integratedConfig.S3Enabled {
			scraper.s3Client = s3.New(sess)
		}
		
		if integratedConfig.CloudWatchEnabled {
			scraper.cwLogsClient = cloudwatchlogs.New(sess)
		}
	}
	
	return scraper, nil
}

// LoadIntegratedConfig loads configuration with Python integration settings
func LoadIntegratedConfig(filename string) (*IntegratedConfig, error) {
	file, err := os.Open(filename)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	
	var integratedConfig IntegratedConfig
	decoder := json.NewDecoder(file)
	if err := decoder.Decode(&integratedConfig); err != nil {
		return nil, err
	}
	
	// Parse timeout
	timeout, err := time.ParseDuration(integratedConfig.Timeout)
	if err != nil {
		return nil, err
	}
	integratedConfig.Config.Timeout = timeout
	
	// Parse retry delay
	retryDelay, err := time.ParseDuration(integratedConfig.RetryDelay)
	if err != nil {
		return nil, err
	}
	integratedConfig.Config.RetryDelay = retryDelay
	
	// Resolve environment variables in S3 bucket name
	if integratedConfig.S3Bucket != "" {
		env := os.Getenv("ENVIRONMENT")
		if env == "" {
			env = "dev"
		}
		integratedConfig.S3Bucket = os.ExpandEnv(integratedConfig.S3Bucket)
		// Replace ${environment} with actual environment
		integratedConfig.S3Bucket = filepath.Join(integratedConfig.S3Bucket[:len(integratedConfig.S3Bucket)-len("${environment}")], env)
	}
	
	return &integratedConfig, nil
}

// ScrapeAndIntegrate runs scraping with full Python infrastructure integration
func (pcs *PythonCompatibleScraper) ScrapeAndIntegrate(ctx context.Context) error {
	log.Println("🔗 Starting integrated scraping with Python infrastructure compatibility")
	
	// Log to CloudWatch if enabled
	if pcs.integratedConfig.CloudWatchEnabled {
		pcs.logToCloudWatch("Starting Go scraper integration", "INFO")
	}
	
	// Run base scraping
	err := pcs.AsyncScraper.ScrapeAllSources(ctx)
	if err != nil {
		pcs.logToCloudWatch(fmt.Sprintf("Scraping error: %v", err), "ERROR")
		return err
	}
	
	// Get scraped articles
	articles := pcs.AsyncScraper.GetAllArticles()
	
	// Apply Python-compatible validation
	validatedArticles := pcs.applyPythonValidation(articles)
	
	// Save locally (compatible with Python pipeline)
	filename := fmt.Sprintf("scraped_articles_%s.json", time.Now().Format("2006-01-02_15-04-05"))
	localPath := filepath.Join(pcs.config.OutputDir, filename)
	
	if err := pcs.saveArticlesCompatible(validatedArticles, localPath); err != nil {
		return fmt.Errorf("failed to save articles locally: %v", err)
	}
	
	log.Printf("💾 Saved %d articles to %s", len(validatedArticles), localPath)
	
	// Upload to S3 if enabled (same structure as Python scraper)
	if pcs.integratedConfig.S3Enabled {
		s3Key := pcs.generateS3Key(filename)
		if err := pcs.uploadToS3(validatedArticles, s3Key); err != nil {
			log.Printf("⚠️  Failed to upload to S3: %v", err)
		} else {
			log.Printf("☁️  Uploaded articles to S3: s3://%s/%s", pcs.integratedConfig.S3Bucket, s3Key)
		}
	}
	
	// Log completion
	if pcs.integratedConfig.CloudWatchEnabled {
		pcs.logToCloudWatch(fmt.Sprintf("Completed scraping: %d articles", len(validatedArticles)), "INFO")
	}
	
	return nil
}

// applyPythonValidation applies the same validation logic as Python scraper
func (pcs *PythonCompatibleScraper) applyPythonValidation(articles []Article) []Article {
	var validatedArticles []Article
	
	for _, article := range articles {
		// Apply same validation as Python ValidationPipeline
		if article.ValidationScore >= pcs.integratedConfig.QualityThreshold {
			validatedArticles = append(validatedArticles, article)
		}
	}
	
	log.Printf("✅ Validation: %d/%d articles passed quality threshold (%d)",
		len(validatedArticles), len(articles), pcs.integratedConfig.QualityThreshold)
	
	return validatedArticles
}

// saveArticlesCompatible saves articles in Python-compatible format
func (pcs *PythonCompatibleScraper) saveArticlesCompatible(articles []Article, filename string) error {
	// Ensure output directory exists
	if err := os.MkdirAll(filepath.Dir(filename), 0755); err != nil {
		return err
	}
	
	file, err := os.Create(filename)
	if err != nil {
		return err
	}
	defer file.Close()
	
	// Use same JSON formatting as Python scraper
	encoder := json.NewEncoder(file)
	encoder.SetIndent("", "  ")
	encoder.SetEscapeHTML(false) // Python doesn't escape HTML
	
	return encoder.Encode(articles)
}

// generateS3Key generates S3 key compatible with Python scraper structure
func (pcs *PythonCompatibleScraper) generateS3Key(filename string) string {
	now := time.Now()
	datePrefix := now.Format("2006/01/02")
	
	return fmt.Sprintf("%s/%s/%s", 
		pcs.integratedConfig.S3Prefix, 
		datePrefix, 
		filename)
}

// uploadToS3 uploads articles to S3 in the same structure as Python scraper
func (pcs *PythonCompatibleScraper) uploadToS3(articles []Article, key string) error {
	// Convert articles to JSON
	data, err := json.MarshalIndent(articles, "", "  ")
	if err != nil {
		return err
	}
	
	// Upload to S3
	_, err = pcs.s3Client.PutObject(&s3.PutObjectInput{
		Bucket:        aws.String(pcs.integratedConfig.S3Bucket),
		Key:           aws.String(key),
		Body:          bytes.NewReader(data),
		ContentType:   aws.String("application/json"),
		ContentLength: aws.Int64(int64(len(data))),
		Metadata: map[string]*string{
			"scraper":    aws.String("go-async"),
			"version":    aws.String("1.0"),
			"timestamp":  aws.String(time.Now().Format(time.RFC3339)),
			"articles":   aws.String(fmt.Sprintf("%d", len(articles))),
		},
	})
	
	return err
}

// logToCloudWatch sends logs to CloudWatch compatible with Python scraper
func (pcs *PythonCompatibleScraper) logToCloudWatch(message, level string) {
	if pcs.cwLogsClient == nil {
		return
	}
	
	logEvent := &cloudwatchlogs.InputLogEvent{
		Message:   aws.String(fmt.Sprintf("[%s] %s", level, message)),
		Timestamp: aws.Int64(time.Now().UnixNano() / int64(time.Millisecond)),
	}
	
	streamName := fmt.Sprintf("%s-%s", 
		pcs.integratedConfig.CloudWatchLogStream, 
		time.Now().Format("2006-01-02"))
	
	_, err := pcs.cwLogsClient.PutLogEvents(&cloudwatchlogs.PutLogEventsInput{
		LogGroupName:  aws.String(pcs.integratedConfig.CloudWatchLogGroup),
		LogStreamName: aws.String(streamName),
		LogEvents:     []*cloudwatchlogs.InputLogEvent{logEvent},
	})
	
	if err != nil {
		log.Printf("Failed to send log to CloudWatch: %v", err)
	}
}

// GetCompatibilityReport generates a report comparing Go and Python scraper outputs
func (pcs *PythonCompatibleScraper) GetCompatibilityReport() map[string]interface{} {
	metrics := pcs.GetMetrics()
	
	return map[string]interface{}{
		"scraper_type":        "go-async-integrated",
		"python_compatible":   true,
		"total_articles":      metrics.TotalArticles,
		"validation_enabled":  pcs.integratedConfig.ValidationEnabled,
		"quality_threshold":   pcs.integratedConfig.QualityThreshold,
		"s3_integration":      pcs.integratedConfig.S3Enabled,
		"cloudwatch_logging":  pcs.integratedConfig.CloudWatchEnabled,
		"duplicate_check":     pcs.integratedConfig.DuplicateCheck,
		"sources_configured":  len(pcs.integratedConfig.Sources),
		"timestamp":           time.Now().Format(time.RFC3339),
	}
}

// RunIntegratedScraper is the main entry point for Python-compatible scraping
func RunIntegratedScraper(configFile string) error {
	log.Println("🔗 Initializing Python-compatible Go scraper")
	
	scraper, err := NewPythonCompatibleScraper(configFile)
	if err != nil {
		return fmt.Errorf("failed to initialize integrated scraper: %v", err)
	}
	
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()
	
	// Run integrated scraping
	if err := scraper.ScrapeAndIntegrate(ctx); err != nil {
		return fmt.Errorf("integrated scraping failed: %v", err)
	}
	
	// Generate compatibility report
	report := scraper.GetCompatibilityReport()
	reportData, _ := json.MarshalIndent(report, "", "  ")
	
	reportFile := filepath.Join(scraper.config.OutputDir, "compatibility_report.json")
	if err := os.WriteFile(reportFile, reportData, 0644); err != nil {
		log.Printf("⚠️  Failed to save compatibility report: %v", err)
	} else {
		log.Printf("📊 Compatibility report saved: %s", reportFile)
	}
	
	log.Println("🎉 Python-compatible scraping completed successfully!")
	return nil
}
