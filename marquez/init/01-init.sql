-- Initial setup for Marquez database
-- This will be executed when the PostgreSQL container starts

-- Create extensions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create initial namespace for NeuroNews
-- This will be done via API calls in the demo script
