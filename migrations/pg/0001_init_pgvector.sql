-- Migration: 0001_init_pgvector.sql
-- Description: Initialize pgvector extension and basic configuration
-- Author: NeuroNews Team
-- Date: 2025-08-26

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify extension installation
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'pgvector extension failed to install';
    END IF;
    
    RAISE NOTICE 'pgvector extension successfully enabled';
END $$;

-- Create schema for vector operations if not exists
CREATE SCHEMA IF NOT EXISTS vector_ops;

-- Set up basic configuration
-- Increase work_mem for vector operations (adjust based on your system)
-- This should be done at the session or user level in production
-- ALTER SYSTEM SET work_mem = '256MB';
-- SELECT pg_reload_conf();

-- Create a function to validate vector dimensions
CREATE OR REPLACE FUNCTION vector_ops.validate_dimension(dim INTEGER)
RETURNS BOOLEAN AS $$
BEGIN
    -- Common embedding dimensions: 384 (sentence-transformers), 768 (BERT), 1536 (OpenAI), 4096 (large models)
    IF dim IN (128, 256, 384, 512, 768, 1024, 1536, 2048, 4096) THEN
        RETURN TRUE;
    END IF;
    
    -- Allow other dimensions but log a warning
    RAISE WARNING 'Unusual embedding dimension: %. Common dimensions are 384, 768, 1536', dim;
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Create a function to compute cosine similarity
CREATE OR REPLACE FUNCTION vector_ops.cosine_similarity(a vector, b vector)
RETURNS REAL AS $$
BEGIN
    RETURN 1 - (a <=> b);
END;
$$ LANGUAGE plpgsql;

-- Create a function to compute L2 distance
CREATE OR REPLACE FUNCTION vector_ops.l2_distance(a vector, b vector)
RETURNS REAL AS $$
BEGIN
    RETURN a <-> b;
END;
$$ LANGUAGE plpgsql;

-- Create a function to normalize vectors
CREATE OR REPLACE FUNCTION vector_ops.normalize_vector(v vector)
RETURNS vector AS $$
DECLARE
    magnitude REAL;
BEGIN
    -- Calculate magnitude
    magnitude := sqrt((v <#> v));
    
    -- Avoid division by zero
    IF magnitude = 0 THEN
        RETURN v;
    END IF;
    
    -- Return normalized vector
    RETURN v / magnitude;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions on schema and functions
GRANT USAGE ON SCHEMA vector_ops TO PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA vector_ops TO PUBLIC;

-- Log completion
DO $$
BEGIN
    RAISE NOTICE 'Migration 0001_init_pgvector.sql completed successfully';
    RAISE NOTICE 'pgvector version: %', (SELECT extversion FROM pg_extension WHERE extname = 'vector');
END $$;
