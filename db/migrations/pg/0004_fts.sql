-- Migration: 0004_fts.sql
-- Description: Add PostgreSQL Full-Text Search (FTS) capabilities for lexical search
-- Issue #231: Lexical search (Postgres FTS) for hybrid retrieval
-- Author: NeuroNews Team
-- Date: 2025-08-26

-- Add tsvector column to chunks table for full-text search
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS search_vector tsvector;

-- Create materialized tsvector from title + content
-- Using 'A' weight for title and 'B' weight for content to boost title relevance
UPDATE chunks 
SET search_vector = 
    setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
    setweight(to_tsvector('english', COALESCE(content, '')), 'B')
WHERE search_vector IS NULL;

-- Create GIN index for fast full-text search
CREATE INDEX IF NOT EXISTS idx_chunks_search_vector 
ON chunks USING gin(search_vector);

-- Create trigger function to automatically update search_vector on insert/update
CREATE OR REPLACE FUNCTION update_chunks_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := 
        setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.content, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop existing trigger if it exists
DROP TRIGGER IF EXISTS trigger_chunks_search_vector ON chunks;

-- Create trigger to automatically update search_vector
CREATE TRIGGER trigger_chunks_search_vector
    BEFORE INSERT OR UPDATE OF title, content ON chunks
    FOR EACH ROW
    EXECUTE FUNCTION update_chunks_search_vector();

-- Create lexical search function for top-k retrieval with ranking and highlights
CREATE OR REPLACE FUNCTION lexical_topk(
    query_text TEXT,
    k INTEGER DEFAULT 10,
    filters JSONB DEFAULT '{}'::jsonb
)
RETURNS TABLE(
    id UUID,
    doc_id VARCHAR(255),
    chunk_id VARCHAR(255),
    title TEXT,
    content TEXT,
    source VARCHAR(100),
    language VARCHAR(10),
    published_at TIMESTAMP WITH TIME ZONE,
    url TEXT,
    rank REAL,
    headline TEXT,
    word_count INTEGER,
    char_count INTEGER
) AS $$
DECLARE
    query_tsquery tsquery;
    source_filter VARCHAR(100);
    language_filter VARCHAR(10);
    date_from TIMESTAMP WITH TIME ZONE;
    date_to TIMESTAMP WITH TIME ZONE;
    min_rank REAL;
BEGIN
    -- Convert query text to tsquery with error handling
    BEGIN
        query_tsquery := plainto_tsquery('english', query_text);
    EXCEPTION WHEN OTHERS THEN
        -- Fallback to simple text search if tsquery fails
        query_tsquery := to_tsquery('english', quote_literal(query_text) || ':*');
    END;
    
    -- Extract filters from JSONB
    source_filter := filters->>'source';
    language_filter := filters->>'language';
    date_from := (filters->>'date_from')::timestamp with time zone;
    date_to := (filters->>'date_to')::timestamp with time zone;
    min_rank := COALESCE((filters->>'min_rank')::real, 0.0);
    
    -- Return ranked results with highlights
    RETURN QUERY
    SELECT 
        c.id,
        c.doc_id,
        c.chunk_id,
        c.title,
        c.content,
        c.source,
        c.language,
        c.published_at,
        c.url,
        ts_rank_cd(c.search_vector, query_tsquery) as rank,
        ts_headline('english', 
                   COALESCE(c.title || ' ' || c.content, c.content), 
                   query_tsquery,
                   'MaxWords=35, MinWords=15, ShortWord=3, HighlightAll=false, MaxFragments=3'
                  ) as headline,
        c.word_count,
        c.char_count
    FROM chunks c
    WHERE 
        c.search_vector @@ query_tsquery
        AND (source_filter IS NULL OR c.source = source_filter)
        AND (language_filter IS NULL OR c.language = language_filter)
        AND (date_from IS NULL OR c.published_at >= date_from)
        AND (date_to IS NULL OR c.published_at <= date_to)
        AND c.doc_id IS NOT NULL  -- Only include records from CLI indexer
        AND ts_rank_cd(c.search_vector, query_tsquery) >= min_rank
    ORDER BY 
        ts_rank_cd(c.search_vector, query_tsquery) DESC,
        c.published_at DESC NULLS LAST
    LIMIT k;
END;
$$ LANGUAGE plpgsql;

-- Create helper function for simple search without filters
CREATE OR REPLACE FUNCTION simple_lexical_search(
    query_text TEXT,
    k INTEGER DEFAULT 10
)
RETURNS TABLE(
    doc_id VARCHAR(255),
    chunk_id VARCHAR(255),
    title TEXT,
    rank REAL,
    headline TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.doc_id,
        c.chunk_id,
        c.title,
        ts_rank_cd(c.search_vector, plainto_tsquery('english', query_text)) as rank,
        ts_headline('english', 
                   COALESCE(c.title || ' ' || c.content, c.content), 
                   plainto_tsquery('english', query_text),
                   'MaxWords=20, MinWords=10'
                  ) as headline
    FROM chunks c
    WHERE 
        c.search_vector @@ plainto_tsquery('english', query_text)
        AND c.doc_id IS NOT NULL
    ORDER BY 
        ts_rank_cd(c.search_vector, plainto_tsquery('english', query_text)) DESC
    LIMIT k;
END;
$$ LANGUAGE plpgsql;

-- Create index on commonly filtered columns for performance
CREATE INDEX IF NOT EXISTS idx_chunks_source_language ON chunks(source, language);
CREATE INDEX IF NOT EXISTS idx_chunks_published_at ON chunks(published_at) WHERE published_at IS NOT NULL;

-- Create statistics view for monitoring FTS performance
CREATE OR REPLACE VIEW fts_stats AS
SELECT 
    COUNT(*) as total_chunks,
    COUNT(*) FILTER (WHERE search_vector IS NOT NULL) as indexed_chunks,
    COUNT(DISTINCT source) as unique_sources,
    COUNT(DISTINCT language) as unique_languages,
    AVG(word_count) as avg_word_count,
    MIN(published_at) as earliest_date,
    MAX(published_at) as latest_date
FROM chunks
WHERE doc_id IS NOT NULL;

-- Add helpful comments
COMMENT ON COLUMN chunks.search_vector IS 'Full-text search vector combining title (weight A) and content (weight B)';
COMMENT ON FUNCTION lexical_topk IS 'Top-k lexical search with ranking, highlights, and filtering support';
COMMENT ON FUNCTION simple_lexical_search IS 'Simplified lexical search function for basic queries';
COMMENT ON VIEW fts_stats IS 'Statistics view for monitoring full-text search performance';

-- Grant permissions
GRANT EXECUTE ON FUNCTION lexical_topk TO neuronews;
GRANT EXECUTE ON FUNCTION simple_lexical_search TO neuronews;
GRANT SELECT ON fts_stats TO neuronews;

DO $$
BEGIN
    RAISE NOTICE 'Migration 0004_fts.sql completed successfully';
    RAISE NOTICE 'Added full-text search capabilities with tsvector and GIN index';
    RAISE NOTICE 'Created lexical_topk() function for ranked search with filters';
    RAISE NOTICE 'Created automatic search_vector update triggers';
    RAISE NOTICE 'Use: SELECT * FROM lexical_topk(''your query'', 10);';
END $$;
