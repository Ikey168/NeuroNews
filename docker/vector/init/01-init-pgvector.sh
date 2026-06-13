#!/bin/bash
set -e

# Initialize pgvector extension
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Enable pgvector extension
    CREATE EXTENSION IF NOT EXISTS vector;
    
    -- Verify extension is installed
    SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
    
    -- Create schema for vector operations
    CREATE SCHEMA IF NOT EXISTS vector_ops;
    
    -- Grant permissions
    GRANT USAGE ON SCHEMA vector_ops TO $POSTGRES_USER;
    GRANT CREATE ON SCHEMA vector_ops TO $POSTGRES_USER;
    
    -- Show available vector functions
    SELECT proname, pronargs 
    FROM pg_proc 
    WHERE pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
    AND proname LIKE '%vector%'
    ORDER BY proname;
EOSQL

echo "pgvector extension initialized successfully"
