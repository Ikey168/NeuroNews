#!/usr/bin/env python3
"""
Generate sample data files for dbt external sources testing.
Creates Parquet files for news and sources, and JSONL files for entities.
"""

import duckdb
import json
from datetime import datetime, timedelta
import os

# Ensure directories exist
os.makedirs('/workspaces/NeuroNews/data/bronze/news', exist_ok=True)
os.makedirs('/workspaces/NeuroNews/data/bronze/entities', exist_ok=True)
os.makedirs('/workspaces/NeuroNews/data/bronze/sources', exist_ok=True)

# Create DuckDB connection
conn = duckdb.connect()

# Sample news data
news_data = [
    {
        'id': 'news_001',
        'title': 'AI Breakthrough in Medical Diagnosis',
        'content': 'Researchers at MIT have developed a new AI system that can diagnose rare diseases with 95% accuracy.',
        'url': 'https://techcrunch.com/ai-medical-diagnosis',
        'source': 'TechCrunch',
        'published_at': '2024-08-20 10:00:00',
        'scraped_at': '2024-08-20 10:30:00',
        'language': 'en',
        'category': 'technology',
        'author': 'Jane Smith',
        'created_at': '2024-08-20 10:30:00',
        'updated_at': '2024-08-20 10:30:00'
    },
    {
        'id': 'news_002', 
        'title': 'Climate Change Impact on Arctic Ice',
        'content': 'New satellite imagery shows accelerated melting of Arctic ice sheets, raising concerns about sea level rise.',
        'url': 'https://reuters.com/climate-arctic-ice',
        'source': 'Reuters',
        'published_at': '2024-08-20 14:00:00',
        'scraped_at': '2024-08-20 14:15:00',
        'language': 'en',
        'category': 'environment',
        'author': 'John Doe',
        'created_at': '2024-08-20 14:15:00',
        'updated_at': '2024-08-20 14:15:00'
    },
    {
        'id': 'news_003',
        'title': 'Stock Market Reaches New Heights',
        'content': 'Major indices posted record gains today as tech stocks surged following positive earnings reports.',
        'url': 'https://bloomberg.com/markets-record-high',
        'source': 'Bloomberg',
        'published_at': '2024-08-21 09:00:00',
        'scraped_at': '2024-08-21 09:10:00',
        'language': 'en',
        'category': 'finance',
        'author': 'Mike Johnson',
        'created_at': '2024-08-21 09:10:00',
        'updated_at': '2024-08-21 09:10:00'
    }
]

# Create news parquet file
conn.execute("""
    CREATE TABLE temp_news AS 
    SELECT * FROM (VALUES 
        ('news_001', 'AI Breakthrough in Medical Diagnosis', 'Researchers at MIT have developed a new AI system that can diagnose rare diseases with 95% accuracy.', 'https://techcrunch.com/ai-medical-diagnosis', 'TechCrunch', '2024-08-20 10:00:00'::timestamp, '2024-08-20 10:30:00'::timestamp, 'en', 'technology', 'Jane Smith', '2024-08-20 10:30:00'::timestamp, '2024-08-20 10:30:00'::timestamp),
        ('news_002', 'Climate Change Impact on Arctic Ice', 'New satellite imagery shows accelerated melting of Arctic ice sheets, raising concerns about sea level rise.', 'https://reuters.com/climate-arctic-ice', 'Reuters', '2024-08-20 14:00:00'::timestamp, '2024-08-20 14:15:00'::timestamp, 'en', 'environment', 'John Doe', '2024-08-20 14:15:00'::timestamp, '2024-08-20 14:15:00'::timestamp),
        ('news_003', 'Stock Market Reaches New Heights', 'Major indices posted record gains today as tech stocks surged following positive earnings reports.', 'https://bloomberg.com/markets-record-high', 'Bloomberg', '2024-08-21 09:00:00'::timestamp, '2024-08-21 09:10:00'::timestamp, 'en', 'finance', 'Mike Johnson', '2024-08-21 09:10:00'::timestamp, '2024-08-21 09:10:00'::timestamp)
    ) AS t(id, title, content, url, source, published_at, scraped_at, language, category, author, created_at, updated_at)
""")

conn.execute("COPY temp_news TO '/workspaces/NeuroNews/data/bronze/news/news_batch_001.parquet' (FORMAT PARQUET)")

# Sample sources data
conn.execute("""
    CREATE TABLE temp_sources AS 
    SELECT * FROM (VALUES 
        ('src_001', 'TechCrunch', 'https://techcrunch.com', 'https://techcrunch.com/feed/', 'en', 'US', 'technology', true, '2024-08-21 08:00:00'::timestamp, '2024-08-20 00:00:00'::timestamp, '2024-08-21 08:00:00'::timestamp),
        ('src_002', 'Reuters', 'https://reuters.com', 'https://reuters.com/rss', 'en', 'UK', 'news', true, '2024-08-21 07:30:00'::timestamp, '2024-08-19 00:00:00'::timestamp, '2024-08-21 07:30:00'::timestamp),
        ('src_003', 'Bloomberg', 'https://bloomberg.com', 'https://bloomberg.com/feed', 'en', 'US', 'finance', true, '2024-08-21 09:15:00'::timestamp, '2024-08-18 00:00:00'::timestamp, '2024-08-21 09:15:00'::timestamp)
    ) AS t(source_id, source_name, base_url, rss_feed_url, language, country, category, scraping_enabled, last_scraped_at, created_at, updated_at)
""")

conn.execute("COPY temp_sources TO '/workspaces/NeuroNews/data/bronze/sources/sources_config.parquet' (FORMAT PARQUET)")

# Sample entities data (JSONL format)
entities_data = [
    {
        'article_id': 'news_001',
        'entity_text': 'MIT',
        'entity_type': 'ORG',
        'confidence_score': 0.95,
        'start_char': 14,
        'end_char': 17,
        'extracted_at': '2024-08-20 10:45:00',
        'created_at': '2024-08-20 10:45:00'
    },
    {
        'article_id': 'news_001', 
        'entity_text': 'AI system',
        'entity_type': 'PRODUCT',
        'confidence_score': 0.88,
        'start_char': 51,
        'end_char': 60,
        'extracted_at': '2024-08-20 10:45:00',
        'created_at': '2024-08-20 10:45:00'
    },
    {
        'article_id': 'news_002',
        'entity_text': 'Arctic',
        'entity_type': 'LOC',
        'confidence_score': 0.92,
        'start_char': 60,
        'end_char': 66,
        'extracted_at': '2024-08-20 14:20:00',
        'created_at': '2024-08-20 14:20:00'
    },
    {
        'article_id': 'news_003',
        'entity_text': 'tech stocks',
        'entity_type': 'PRODUCT',
        'confidence_score': 0.85,
        'start_char': 75,
        'end_char': 86,
        'extracted_at': '2024-08-21 09:15:00',
        'created_at': '2024-08-21 09:15:00'
    }
]

# Write entities JSONL file
with open('/workspaces/NeuroNews/data/bronze/entities/entities_batch_001.jsonl', 'w') as f:
    for entity in entities_data:
        f.write(json.dumps(entity) + '\n')

print("Sample data files created successfully!")
print("Files created:")
print("- /workspaces/NeuroNews/data/bronze/news/news_batch_001.parquet")
print("- /workspaces/NeuroNews/data/bronze/sources/sources_config.parquet") 
print("- /workspaces/NeuroNews/data/bronze/entities/entities_batch_001.jsonl")

conn.close()
