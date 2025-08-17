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

-- Event Clusters Table (Issue #31)
DROP TABLE IF EXISTS event_clusters CASCADE;

CREATE TABLE event_clusters (
    -- Primary identifiers
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    cluster_id VARCHAR(255) UNIQUE NOT NULL, -- e.g., 'tech_event_20250815_001'
    
    -- Cluster metadata
    cluster_name VARCHAR(500), -- Descriptive name for the event
    event_type VARCHAR(100), -- 'breaking', 'trending', 'developing', 'resolved'
    category VARCHAR(100), -- 'Technology', 'Politics', 'Health', etc.
    
    -- Clustering parameters
    embedding_model VARCHAR(255) NOT NULL, -- e.g., 'all-MiniLM-L6-v2'
    clustering_method VARCHAR(100) DEFAULT 'kmeans', -- 'kmeans', 'dbscan', etc.
    cluster_size INTEGER, -- Number of articles in cluster
    
    -- Quality metrics
    silhouette_score DECIMAL(5,4), -- Clustering quality score
    cohesion_score DECIMAL(5,4), -- How similar articles are within cluster
    separation_score DECIMAL(5,4), -- How different cluster is from others
    
    -- Event detection metadata
    first_article_date TIMESTAMP, -- When first article in cluster was published
    last_article_date TIMESTAMP, -- When last article in cluster was published
    peak_activity_date TIMESTAMP, -- When most articles were published
    event_duration_hours DECIMAL(8,2), -- Duration of event in hours
    
    -- Geographic and source information
    primary_sources SUPER, -- JSON array of main sources covering the event
    geographic_focus SUPER, -- JSON array of locations mentioned
    key_entities SUPER, -- JSON array of main entities (people, orgs) involved
    
    -- Event significance
    trending_score DECIMAL(8,4), -- How trending/viral the event is
    impact_score DECIMAL(5,2), -- Estimated impact/importance (1-100)
    velocity_score DECIMAL(8,4), -- How fast the story is developing
    
    -- Status and lifecycle
    status VARCHAR(50) DEFAULT 'active', -- 'active', 'merged', 'split', 'archived'
    merged_into_cluster_id VARCHAR(255), -- If merged with another cluster
    
    -- Timestamps
    created_at TIMESTAMP SORTKEY DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
DISTSTYLE EVEN
COMPOUND SORTKEY (created_at, category, event_type);

-- Article Cluster Assignments Table (Issue #31)
DROP TABLE IF EXISTS article_cluster_assignments CASCADE;

CREATE TABLE article_cluster_assignments (
    -- Primary identifiers
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    article_id VARCHAR(255) DISTKEY REFERENCES news_articles(id),
    cluster_id VARCHAR(255) REFERENCES event_clusters(cluster_id),
    
    -- Assignment metadata
    assignment_confidence DECIMAL(5,4), -- How confident the clustering is
    distance_to_centroid DECIMAL(10,6), -- Distance from cluster center
    is_cluster_representative BOOLEAN DEFAULT FALSE, -- Is this a key article for the cluster?
    
    -- Article contribution to cluster
    contribution_score DECIMAL(5,4), -- How much this article contributes to cluster definition
    novelty_score DECIMAL(5,4), -- How novel/unique this article is within cluster
    
    -- Processing metadata
    embedding_vector SUPER, -- JSON array of the article's embedding vector (optional)
    processing_method VARCHAR(100), -- Method used for assignment
    processing_version VARCHAR(50), -- Version of clustering algorithm
    
    -- Timestamps
    assigned_at TIMESTAMP SORTKEY DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
DISTSTYLE KEY
COMPOUND SORTKEY (assigned_at, cluster_id, assignment_confidence);

-- Article Embeddings Table (Issue #31)
DROP TABLE IF EXISTS article_embeddings CASCADE;

CREATE TABLE article_embeddings (
    -- Primary identifiers
    id BIGINT IDENTITY(1,1) PRIMARY KEY,
    article_id VARCHAR(255) DISTKEY REFERENCES news_articles(id),
    
    -- Embedding metadata
    embedding_model VARCHAR(255) NOT NULL, -- e.g., 'all-MiniLM-L6-v2'
    embedding_dimension INTEGER NOT NULL, -- Vector dimension (e.g., 384, 768)
    embedding_vector SUPER NOT NULL, -- JSON array of embedding values
    
    -- Text processing metadata
    text_preprocessed TEXT, -- Preprocessed text used for embedding
    text_hash VARCHAR(64), -- Hash of preprocessed text for deduplication
    tokens_count INTEGER, -- Number of tokens processed
    
    -- Quality metrics
    embedding_quality_score DECIMAL(5,4), -- Quality assessment of embedding
    processing_time DECIMAL(8,4), -- Time taken to generate embedding (seconds)
    
    -- Timestamps
    created_at TIMESTAMP SORTKEY DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
DISTSTYLE KEY
COMPOUND SORTKEY (created_at, embedding_model);

-- Create indexes for performance optimization
-- Redshift automatically manages indexes, but we define compound sort keys above

-- Event Clusters Statistics View (Issue #31)
CREATE OR REPLACE VIEW event_cluster_statistics AS
SELECT 
    ec.cluster_id,
    ec.cluster_name,
    ec.category,
    ec.event_type,
    ec.cluster_size,
    ec.trending_score,
    ec.impact_score,
    ec.first_article_date,
    ec.last_article_date,
    ec.event_duration_hours,
    COUNT(aca.article_id) as actual_article_count,
    AVG(aca.assignment_confidence) as avg_confidence,
    AVG(aca.distance_to_centroid) as avg_distance,
    COUNT(CASE WHEN aca.is_cluster_representative THEN 1 END) as representative_articles,
    STRING_AGG(DISTINCT a.source, ', ') as sources,
    COUNT(DISTINCT a.source) as unique_sources
FROM event_clusters ec
LEFT JOIN article_cluster_assignments aca ON ec.cluster_id = aca.cluster_id
LEFT JOIN news_articles a ON aca.article_id = a.id
GROUP BY 
    ec.cluster_id, ec.cluster_name, ec.category, ec.event_type,
    ec.cluster_size, ec.trending_score, ec.impact_score,
    ec.first_article_date, ec.last_article_date, ec.event_duration_hours
ORDER BY ec.trending_score DESC, ec.created_at DESC;

-- Active Breaking News View (Issue #31)
CREATE OR REPLACE VIEW active_breaking_news AS
SELECT 
    ec.cluster_id,
    ec.cluster_name,
    ec.category,
    ec.event_type,
    ec.trending_score,
    ec.impact_score,
    ec.velocity_score,
    ec.cluster_size,
    ec.first_article_date,
    ec.last_article_date,
    ec.peak_activity_date,
    ec.event_duration_hours,
    STRING_AGG(DISTINCT a.title, ' | ') as sample_headlines,
    COUNT(DISTINCT a.source) as source_count,
    AVG(aca.assignment_confidence) as avg_confidence
FROM event_clusters ec
JOIN article_cluster_assignments aca ON ec.cluster_id = aca.cluster_id
JOIN news_articles a ON aca.article_id = a.id
WHERE 
    ec.status = 'active'
    AND ec.event_type IN ('breaking', 'trending', 'developing')
    AND ec.last_article_date >= DATEADD(hour, -24, CURRENT_TIMESTAMP) -- Active in last 24 hours
    AND a.source_credibility IN ('trusted', 'reliable')
GROUP BY 
    ec.cluster_id, ec.cluster_name, ec.category, ec.event_type,
    ec.trending_score, ec.impact_score, ec.velocity_score, ec.cluster_size,
    ec.first_article_date, ec.last_article_date, ec.peak_activity_date,
    ec.event_duration_hours
HAVING COUNT(aca.article_id) >= 3 -- At least 3 articles
ORDER BY ec.trending_score DESC, ec.impact_score DESC;

-- Trending Events by Category View (Issue #31)
CREATE OR REPLACE VIEW trending_events_by_category AS
SELECT 
    ec.category,
    COUNT(DISTINCT ec.cluster_id) as active_events,
    SUM(ec.cluster_size) as total_articles,
    AVG(ec.trending_score) as avg_trending_score,
    AVG(ec.impact_score) as avg_impact_score,
    MAX(ec.trending_score) as max_trending_score,
    STRING_AGG(DISTINCT ec.cluster_name, ' | ') as top_events
FROM event_clusters ec
WHERE 
    ec.status = 'active'
    AND ec.last_article_date >= DATEADD(hour, -24, CURRENT_TIMESTAMP)
GROUP BY ec.category
ORDER BY avg_trending_score DESC, active_events DESC;

-- Breaking News View (Issue #31)
CREATE OR REPLACE VIEW breaking_news_view AS
SELECT 
    ec.cluster_id,
    ec.cluster_name,
    ec.event_type,
    ec.category,
    ec.trending_score,
    ec.impact_score,
    ec.velocity_score,
    ec.cluster_size,
    ec.first_article_date,
    ec.last_article_date,
    ec.peak_activity_date,
    ec.event_duration_hours,
    STRING_AGG(DISTINCT a.title, ' | ') as sample_headlines,
    COUNT(DISTINCT a.source) as source_count,
    AVG(aca.confidence_score) as avg_confidence
FROM event_clusters ec
JOIN article_cluster_assignments aca ON ec.cluster_id = aca.cluster_id
JOIN articles a ON aca.article_id = a.id
WHERE 
    ec.status = 'active'
    AND ec.event_type IN ('breaking', 'trending')
    AND ec.last_article_date >= DATEADD(hour, -6, CURRENT_TIMESTAMP) -- Breaking in last 6 hours
    AND a.source_credibility IN ('trusted', 'reliable')
GROUP BY 
    ec.cluster_id, ec.cluster_name, ec.category, ec.event_type,
    ec.trending_score, ec.impact_score, ec.velocity_score, ec.cluster_size,
    ec.first_article_date, ec.last_article_date, ec.peak_activity_date,
    ec.event_duration_hours
HAVING COUNT(aca.article_id) >= 2 -- At least 2 articles for breaking news
ORDER BY ec.trending_score DESC, ec.impact_score DESC;

-- Trending Events View (Issue #31)  
CREATE OR REPLACE VIEW trending_events_view AS
SELECT 
    ec.cluster_id,
    ec.cluster_name,
    ec.event_type,
    ec.category,
    ec.trending_score,
    ec.impact_score,
    ec.velocity_score,
    ec.cluster_size,
    ec.first_article_date,
    ec.last_article_date,
    ec.peak_activity_date,
    ec.event_duration_hours,
    STRING_AGG(DISTINCT a.title, ' | ') as sample_headlines,
    COUNT(DISTINCT a.source) as source_count,
    AVG(aca.confidence_score) as avg_confidence
FROM event_clusters ec
JOIN article_cluster_assignments aca ON ec.cluster_id = aca.cluster_id
JOIN articles a ON aca.article_id = a.id
WHERE 
    ec.status = 'active'
    AND ec.last_article_date >= DATEADD(hour, -24, CURRENT_TIMESTAMP) -- Active in last 24 hours
    AND a.source_credibility IN ('trusted', 'reliable')
GROUP BY 
    ec.cluster_id, ec.cluster_name, ec.category, ec.event_type,
    ec.trending_score, ec.impact_score, ec.velocity_score, ec.cluster_size,
    ec.first_article_date, ec.last_article_date, ec.peak_activity_date,
    ec.event_duration_hours
HAVING COUNT(aca.article_id) >= 3 -- At least 3 articles
ORDER BY ec.trending_score DESC, ec.impact_score DESC;
