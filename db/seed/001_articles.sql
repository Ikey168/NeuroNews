-- Articles table schema with primary key and NOT NULL constraints
-- for CDC streaming setup with Debezium

-- Drop existing table if it exists (in case it has a different schema)
DROP TABLE IF EXISTS public.articles;

CREATE TABLE public.articles (
    article_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    body TEXT,
    language TEXT NOT NULL,
    country TEXT,
    published_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Insert demo data for CDC testing
INSERT INTO public.articles (
    article_id,
    source_id,
    url,
    title,
    body,
    language,
    country,
    published_at,
    updated_at
) VALUES 
    (
        'a1',
        's1', 
        'https://example.com/article1',
        'Breaking: AI Revolution in Healthcare',
        'Artificial intelligence is transforming healthcare with new diagnostic tools and personalized treatment approaches.',
        'en',
        'US',
        NOW(),
        NOW()
    ),
    (
        'a2',
        's2',
        'https://example.com/article2', 
        'Climate Change: Latest Research Findings',
        'New research reveals accelerating impacts of climate change on global ecosystems and weather patterns.',
        'en',
        'UK',
        NOW() - INTERVAL '1 hour',
        NOW() - INTERVAL '30 minutes'
    )
ON CONFLICT (article_id) DO NOTHING;
