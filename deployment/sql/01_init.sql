-- Database initialization script for NeuroNews
-- This script sets up the basic database schema for both development and testing

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create schemas
CREATE SCHEMA IF NOT EXISTS neuronews;
SET search_path TO neuronews, public;

-- Articles table
CREATE TABLE IF NOT EXISTS articles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    author TEXT,
    published_date TIMESTAMP WITH TIME ZONE,
    source TEXT NOT NULL,
    category TEXT,
    language TEXT DEFAULT 'en',
    sentiment_score NUMERIC(3,2),
    sentiment_label TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Article embeddings table for event detection
CREATE TABLE IF NOT EXISTS article_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    article_id UUID REFERENCES articles(id) ON DELETE CASCADE,
    embedding_model TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL,
    embedding_vector JSONB NOT NULL,
    text_preprocessed TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    tokens_count INTEGER,
    embedding_quality_score NUMERIC(3,2),
    processing_time NUMERIC(6,3),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(article_id, text_hash, embedding_model)
);

-- Keywords and topics table
CREATE TABLE IF NOT EXISTS article_keywords (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    article_id UUID REFERENCES articles(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    score NUMERIC(6,4) NOT NULL,
    extraction_method TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS article_topics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    article_id UUID REFERENCES articles(id) ON DELETE CASCADE,
    topic_name TEXT NOT NULL,
    topic_probability NUMERIC(6,4) NOT NULL,
    topic_words JSONB,
    model_version TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Event clusters table
CREATE TABLE IF NOT EXISTS event_clusters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cluster_name TEXT NOT NULL,
    event_type TEXT,
    category TEXT,
    description TEXT,
    significance_score NUMERIC(6,4),
    trending_score NUMERIC(6,4),
    impact_score NUMERIC(6,4),
    velocity_score NUMERIC(6,4),
    article_count INTEGER DEFAULT 0,
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    peak_time TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Article cluster assignments
CREATE TABLE IF NOT EXISTS article_clusters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    article_id UUID REFERENCES articles(id) ON DELETE CASCADE,
    cluster_id UUID REFERENCES event_clusters(id) ON DELETE CASCADE,
    similarity_score NUMERIC(6,4),
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(article_id, cluster_id)
);

-- Multi-language support
CREATE TABLE IF NOT EXISTS article_translations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    article_id UUID REFERENCES articles(id) ON DELETE CASCADE,
    source_language TEXT NOT NULL,
    target_language TEXT NOT NULL,
    translated_title TEXT,
    translated_content TEXT,
    translation_quality_score NUMERIC(3,2),
    translation_service TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(article_id, target_language)
);

-- User management and authentication
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    role TEXT DEFAULT 'user',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- API keys and access tokens
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    key_name TEXT NOT NULL,
    key_hash TEXT UNIQUE NOT NULL,
    permissions JSONB DEFAULT '{}',
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_articles_published_date ON articles(published_date);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
CREATE INDEX IF NOT EXISTS idx_articles_language ON articles(language);
CREATE INDEX IF NOT EXISTS idx_articles_sentiment ON articles(sentiment_score);

CREATE INDEX IF NOT EXISTS idx_embeddings_article_id ON article_embeddings(article_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_model ON article_embeddings(embedding_model);
CREATE INDEX IF NOT EXISTS idx_embeddings_hash ON article_embeddings(text_hash);

CREATE INDEX IF NOT EXISTS idx_keywords_article_id ON article_keywords(article_id);
CREATE INDEX IF NOT EXISTS idx_keywords_keyword ON article_keywords(keyword);
CREATE INDEX IF NOT EXISTS idx_keywords_score ON article_keywords(score);

CREATE INDEX IF NOT EXISTS idx_topics_article_id ON article_topics(article_id);
CREATE INDEX IF NOT EXISTS idx_topics_name ON article_topics(topic_name);

CREATE INDEX IF NOT EXISTS idx_clusters_type ON event_clusters(event_type);
CREATE INDEX IF NOT EXISTS idx_clusters_category ON event_clusters(category);
CREATE INDEX IF NOT EXISTS idx_clusters_significance ON event_clusters(significance_score);
CREATE INDEX IF NOT EXISTS idx_clusters_created ON event_clusters(created_at);

CREATE INDEX IF NOT EXISTS idx_article_clusters_article ON article_clusters(article_id);
CREATE INDEX IF NOT EXISTS idx_article_clusters_cluster ON article_clusters(cluster_id);

-- Create functions for updating timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for automatic timestamp updates
CREATE TRIGGER update_articles_updated_at BEFORE UPDATE ON articles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_event_clusters_updated_at BEFORE UPDATE ON event_clusters
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert sample admin user (password: admin123)
INSERT INTO users (username, email, password_hash, full_name, role)
VALUES (
    'admin',
    'admin@neuronews.local',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LeU1bqeB0Z1S2nCCS',
    'System Administrator',
    'admin'
) ON CONFLICT (username) DO NOTHING;

-- Grant necessary permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA neuronews TO neuronews;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA neuronews TO neuronews;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA neuronews TO neuronews;

-- Also grant to test user if exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'test_user') THEN
        GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA neuronews TO test_user;
        GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA neuronews TO test_user;
        GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA neuronews TO test_user;
    END IF;
END
$$;
