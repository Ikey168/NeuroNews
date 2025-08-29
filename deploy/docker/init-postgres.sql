-- Initialize PostgreSQL for CDC with Debezium
-- Enable logical replication
ALTER SYSTEM SET wal_level = logical;
ALTER SYSTEM SET max_wal_senders = 4;
ALTER SYSTEM SET max_replication_slots = 4;

-- Create a sample table for CDC testing
CREATE TABLE IF NOT EXISTS articles (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    content TEXT,
    author VARCHAR(100),
    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create a trigger to update the updated_at column
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_articles_updated_at 
    BEFORE UPDATE ON articles 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert sample data
INSERT INTO articles (title, content, author) VALUES
    ('Sample Article 1', 'This is the content of the first sample article.', 'John Doe'),
    ('Sample Article 2', 'This is the content of the second sample article.', 'Jane Smith'),
    ('Sample Article 3', 'This is the content of the third sample article.', 'Bob Johnson');

-- Create a user for Debezium with replication privileges
DO
$do$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_catalog.pg_roles
      WHERE  rolname = 'debezium') THEN
      
      CREATE ROLE debezium WITH LOGIN PASSWORD 'debezium';
   END IF;
END
$do$;

-- Grant necessary privileges
GRANT SELECT ON ALL TABLES IN SCHEMA public TO debezium;
GRANT USAGE ON SCHEMA public TO debezium;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO debezium;

-- Grant replication privileges
ALTER ROLE debezium WITH REPLICATION;
