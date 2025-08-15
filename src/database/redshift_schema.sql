-- AWS Redshift Schema for NeuroNews Articles
-- Updated to match data validation pipeline output

DROP TABLE IF EXISTS news_articles;

CREATE TABLE news_articles (
    -- Primary identifiers
    id VARCHAR(255) DISTKEY PRIMARY KEY,
    url VARCHAR(1000) NOT NULL,
    
    -- Core article content
    title VARCHAR(1000) NOT NULL,
    content VARCHAR(65535) NOT NULL,
    source VARCHAR(255) NOT NULL,
    
    -- Publishing metadata
    published_date TIMESTAMP SORTKEY,
    scraped_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Validation metadata
    validation_score DECIMAL(5,2),
    content_quality VARCHAR(20), -- 'high', 'medium', 'low'
    source_credibility VARCHAR(20), -- 'trusted', 'reliable', 'questionable', 'unreliable', 'banned'
    validation_flags SUPER, -- JSON array of validation issues
    validated_at TIMESTAMP,
    
    -- Content metrics
    word_count INTEGER,
    content_length INTEGER,
    
    -- Optional fields for future enhancement
    author VARCHAR(255),
    category VARCHAR(100),
    
    -- NLP analysis results
    sentiment_score DECIMAL(3,2),
    sentiment_label VARCHAR(20),
    entities SUPER, -- JSON array of extracted entities
    
    -- Keyword extraction and topic modeling (Issue #29)
    keywords SUPER,  -- JSON array of keywords with scores
    topics SUPER,    -- JSON array of topics with probabilities
    dominant_topic SUPER, -- JSON object of the most probable topic
    extraction_method VARCHAR(50), -- Method used for extraction (tfidf_lda, bert, etc.)
    extraction_processed_at TIMESTAMP, -- When extraction was performed
    extraction_processing_time DECIMAL(10,3) -- Processing time in seconds
)
DISTSTYLE KEY
COMPOUND SORTKEY (published_date, source_credibility, content_quality);

-- Article Summaries Table (Issue #30)
DROP TABLE IF EXISTS article_summaries;

CREATE TABLE article_summaries (
    -- Primary identifiers
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    article_id VARCHAR(255) DISTKEY REFERENCES news_articles(id),
    content_hash VARCHAR(64) NOT NULL, -- Hash of content + parameters for deduplication
    
    -- Summary content
    summary_text TEXT NOT NULL,
    summary_length VARCHAR(50) NOT NULL, -- 'short', 'medium', 'long'
    
    -- Model and processing metadata
    model_used VARCHAR(255) NOT NULL, -- e.g., 'facebook/bart-large-cnn'
    confidence_score DECIMAL(5,4), -- Quality confidence score
    processing_time DECIMAL(10,4), -- Time taken to generate (seconds)
    
    -- Summary metrics
    word_count INTEGER,
    sentence_count INTEGER,
    compression_ratio DECIMAL(5,4), -- Summary words / Original words
    
    -- Timestamps
    created_at TIMESTAMP SORTKEY DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
DISTSTYLE KEY
COMPOUND SORTKEY (created_at, summary_length, article_id);

-- Indexes for common query patterns
-- Note: Redshift automatically manages indexes, but we can suggest query optimization

-- Create staging table for batch loads
DROP TABLE IF EXISTS news_articles_staging;

CREATE TABLE news_articles_staging (
    LIKE news_articles
);

-- Create view for high-quality articles
CREATE OR REPLACE VIEW high_quality_articles AS
SELECT 
    id, url, title, content, source, published_date,
    validation_score, content_quality, source_credibility,
    word_count, author, category
FROM news_articles
WHERE 
    validation_score >= 70.0
    AND source_credibility IN ('trusted', 'reliable')
    AND content_quality IN ('high', 'medium')
ORDER BY published_date DESC;

-- Create view for article statistics
CREATE OR REPLACE VIEW article_statistics AS
SELECT 
    DATE_TRUNC('day', published_date) as publish_date,
    source,
    source_credibility,
    content_quality,
    COUNT(*) as article_count,
    AVG(validation_score) as avg_validation_score,
    AVG(word_count) as avg_word_count,
    AVG(content_length) as avg_content_length
FROM news_articles
GROUP BY 
    DATE_TRUNC('day', published_date),
    source,
    source_credibility,
    content_quality
ORDER BY publish_date DESC, article_count DESC;

-- Summary statistics view (Issue #30)
CREATE OR REPLACE VIEW summary_statistics AS
SELECT 
    summary_length,
    model_used,
    COUNT(*) as summary_count,
    COUNT(DISTINCT article_id) as unique_articles,
    AVG(confidence_score) as avg_confidence,
    AVG(processing_time) as avg_processing_time,
    AVG(word_count) as avg_word_count,
    AVG(compression_ratio) as avg_compression_ratio,
    MIN(created_at) as first_summary,
    MAX(created_at) as latest_summary
FROM article_summaries
GROUP BY summary_length, model_used
ORDER BY summary_count DESC;

-- High-quality summaries view (Issue #30)
CREATE OR REPLACE VIEW high_quality_summaries AS
SELECT 
    s.id, s.article_id, s.summary_text, s.summary_length,
    s.model_used, s.confidence_score, s.word_count,
    s.compression_ratio, s.created_at,
    a.title, a.source, a.published_date
FROM article_summaries s
JOIN news_articles a ON s.article_id = a.id
WHERE 
    s.confidence_score >= 0.7
    AND a.source_credibility IN ('trusted', 'reliable')
    AND a.content_quality IN ('high', 'medium')
ORDER BY s.created_at DESC;
