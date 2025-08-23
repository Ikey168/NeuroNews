"""
NeuroNews Data Pipeline DAG (Issue #189)

A minimal, reviewable DAG that demonstrates the complete NeuroNews data pipeline
from scraping to publishing, with proper OpenLineage tracking for data lineage.

This DAG shows:
- TaskFlow API usage for clean, maintainable code
- Deterministic dataset paths for lineage tracking
- Four-stage data processing: Raw → Bronze → Silver → Gold
- Proper error handling and retries
- Daily scheduling with European timezone
"""

from datetime import datetime, timedelta
from pathlib import Path
import json
import pandas as pd
import yaml
from typing import Dict, List, Any

from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.utils.dates import days_ago


# Default arguments for all tasks
default_args = {
    'owner': 'neuronews',
    'depends_on_past': False,
    'start_date': datetime(2025, 8, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'max_active_runs': 1,
}


def load_io_paths() -> Dict[str, Any]:
    """Load dataset paths configuration from YAML file."""
    yaml_path = Path("/opt/airflow/include/io_paths.yml")
    with open(yaml_path, 'r') as f:
        return yaml.safe_load(f)


@dag(
    dag_id='news_pipeline',
    default_args=default_args,
    description='NeuroNews data pipeline: scrape → clean → nlp → publish',
    schedule_interval='0 8 * * *',  # Daily at 08:00 Europe/Berlin
    start_date=datetime(2025, 8, 1),
    catchup=False,
    tags=['neuronews', 'data-pipeline', 'openlineage'],
    max_active_runs=1,
    doc_md=__doc__,
)
def news_pipeline():
    """
    NeuroNews daily data pipeline.
    
    Pipeline stages:
    1. Scrape: Collect news articles from various sources
    2. Clean: Standardize, deduplicate, and validate data
    3. NLP: Extract insights, sentiment, entities, keywords
    4. Publish: Create business-ready datasets for analytics
    """
    
    @task
    def scrape(**context) -> Dict[str, str]:
        """
        Scrape news articles from various sources.
        
        Returns:
            Dict with paths to created files
        """
        from datetime import datetime
        import os
        
        # Load IO paths configuration
        io_paths = load_io_paths()
        ds = context['ds']
        
        # Resolve paths with date
        articles_path = io_paths['raw']['news_articles'].replace('{{ ds }}', ds)
        metadata_path = io_paths['raw']['scraping_metadata'].replace('{{ ds }}', ds)
        
        # Ensure directories exist
        os.makedirs(os.path.dirname(articles_path), exist_ok=True)
        
        # Mock scraped data - in production this would call real scrapers
        mock_articles = [
            {
                "id": f"article_{i}",
                "title": f"Sample News Article {i}",
                "content": f"This is the content of news article {i}. It contains important information about current events.",
                "url": f"https://example.com/article-{i}",
                "source": "example.com",
                "publish_date": ds,
                "scraped_at": datetime.now().isoformat(),
                "language": "en"
            }
            for i in range(1, 11)  # 10 sample articles
        ]
        
        # Write articles to JSON
        with open(articles_path, 'w') as f:
            json.dump(mock_articles, f, indent=2)
        
        # Write scraping metadata
        metadata = {
            "scraping_date": ds,
            "total_articles": len(mock_articles),
            "sources": ["example.com"],
            "scraping_duration_seconds": 30,
            "success": True
        }
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"✅ Scraped {len(mock_articles)} articles")
        print(f"📄 Articles saved to: {articles_path}")
        print(f"📊 Metadata saved to: {metadata_path}")
        
        return {
            "articles_path": articles_path,
            "metadata_path": metadata_path,
            "article_count": len(mock_articles)
        }
    
    @task
    def clean(scrape_result: Dict[str, str], **context) -> Dict[str, str]:
        """
        Clean and standardize scraped articles.
        
        SLA: 15 minutes (Issue #190)
        This task should complete within 15 minutes of its scheduled time.
        
        Args:
            scrape_result: Output from scrape task
            
        Returns:
            Dict with paths to cleaned data files
        """
        import os
        import pandas as pd
        from datetime import datetime
        
        # Load IO paths configuration
        io_paths = load_io_paths()
        ds = context['ds']
        
        # Input and output paths
        articles_path = scrape_result["articles_path"]
        clean_articles_path = io_paths['bronze']['clean_articles'].replace('{{ ds }}', ds)
        metadata_path = io_paths['bronze']['article_metadata'].replace('{{ ds }}', ds)
        
        # Ensure directories exist
        os.makedirs(os.path.dirname(clean_articles_path), exist_ok=True)
        
        # Load raw articles
        with open(articles_path, 'r') as f:
            raw_articles = json.load(f)
        
        # Clean and standardize data
        cleaned_articles = []
        for article in raw_articles:
            cleaned = {
                "article_id": article["id"],
                "title": article["title"].strip(),
                "content": article["content"].strip(),
                "url": article["url"],
                "source": article["source"],
                "publish_date": article["publish_date"],
                "scraped_at": article["scraped_at"],
                "language": article["language"],
                "word_count": len(article["content"].split()),
                "title_length": len(article["title"]),
                "cleaned_at": datetime.now().isoformat(),
                "is_valid": len(article["content"]) > 50  # Basic validation
            }
            cleaned_articles.append(cleaned)
        
        # Convert to DataFrame and save as Parquet
        df_articles = pd.DataFrame(cleaned_articles)
        df_articles.to_parquet(clean_articles_path, index=False)
        
        # Create metadata summary
        metadata = {
            "processing_date": ds,
            "total_articles": len(cleaned_articles),
            "valid_articles": sum(1 for a in cleaned_articles if a["is_valid"]),
            "invalid_articles": sum(1 for a in cleaned_articles if not a["is_valid"]),
            "avg_word_count": df_articles["word_count"].mean(),
            "sources": df_articles["source"].unique().tolist(),
            "languages": df_articles["language"].unique().tolist()
        }
        
        df_metadata = pd.DataFrame([metadata])
        df_metadata.to_parquet(metadata_path, index=False)
        
        print(f"✅ Cleaned {len(cleaned_articles)} articles")
        print(f"📄 Clean articles saved to: {clean_articles_path}")
        print(f"📊 Metadata saved to: {metadata_path}")
        print(f"📈 Valid articles: {metadata['valid_articles']}/{metadata['total_articles']}")
        
        return {
            "clean_articles_path": clean_articles_path,
            "metadata_path": metadata_path,
            "valid_article_count": metadata['valid_articles']
        }
    
    @task
    def nlp(clean_result: Dict[str, str], **context) -> Dict[str, str]:
        """
        Perform NLP processing on cleaned articles.
        
        Args:
            clean_result: Output from clean task
            
        Returns:
            Dict with paths to NLP processed files
        """
        import os
        import pandas as pd
        from datetime import datetime
        import re
        
        # Load IO paths configuration
        io_paths = load_io_paths()
        ds = context['ds']
        
        # Input and output paths
        clean_articles_path = clean_result["clean_articles_path"]
        nlp_processed_path = io_paths['silver']['nlp_processed'].replace('{{ ds }}', ds)
        sentiment_path = io_paths['silver']['sentiment_scores'].replace('{{ ds }}', ds)
        entities_path = io_paths['silver']['named_entities'].replace('{{ ds }}', ds)
        keywords_path = io_paths['silver']['keywords'].replace('{{ ds }}', ds)
        
        # Ensure directories exist
        os.makedirs(os.path.dirname(nlp_processed_path), exist_ok=True)
        
        # Load cleaned articles
        df_articles = pd.read_parquet(clean_articles_path)
        
        # Mock NLP processing - in production this would use real NLP models
        nlp_results = []
        sentiment_results = []
        entity_results = []
        keyword_results = []
        
        for _, article in df_articles.iterrows():
            if not article["is_valid"]:
                continue
                
            article_id = article["article_id"]
            content = article["content"]
            
            # Mock sentiment analysis
            sentiment_score = 0.1  # Slightly positive sentiment
            sentiment = "positive" if sentiment_score > 0 else "negative" if sentiment_score < 0 else "neutral"
            
            sentiment_results.append({
                "article_id": article_id,
                "sentiment": sentiment,
                "sentiment_score": sentiment_score,
                "confidence": 0.85
            })
            
            # Mock named entity extraction
            # Simple regex to find capitalized words as mock entities
            entities = re.findall(r'\b[A-Z][a-z]+\b', content)
            for entity in set(entities[:5]):  # Top 5 unique entities
                entity_results.append({
                    "article_id": article_id,
                    "entity": entity,
                    "entity_type": "PERSON",  # Mock type
                    "confidence": 0.9
                })
            
            # Mock keyword extraction
            words = content.lower().split()
            word_freq = {}
            for word in words:
                if len(word) > 4:  # Only consider longer words
                    word_freq[word] = word_freq.get(word, 0) + 1
            
            # Top 5 keywords by frequency
            top_keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
            for keyword, frequency in top_keywords:
                keyword_results.append({
                    "article_id": article_id,
                    "keyword": keyword,
                    "frequency": frequency,
                    "relevance_score": frequency / len(words)
                })
            
            # Comprehensive NLP result
            nlp_results.append({
                "article_id": article_id,
                "processed_at": datetime.now().isoformat(),
                "sentiment": sentiment,
                "sentiment_score": sentiment_score,
                "entity_count": len(set(entities)),
                "keyword_count": len(top_keywords),
                "readability_score": 7.5,  # Mock readability score
                "language_detected": article["language"],
                "processing_time_ms": 150  # Mock processing time
            })
        
        # Save all NLP results as Parquet files
        pd.DataFrame(nlp_results).to_parquet(nlp_processed_path, index=False)
        pd.DataFrame(sentiment_results).to_parquet(sentiment_path, index=False)
        pd.DataFrame(entity_results).to_parquet(entities_path, index=False)
        pd.DataFrame(keyword_results).to_parquet(keywords_path, index=False)
        
        print(f"✅ Processed {len(nlp_results)} articles with NLP")
        print(f"📄 NLP results saved to: {nlp_processed_path}")
        print(f"💭 Sentiment scores saved to: {sentiment_path}")
        print(f"🏷️  Named entities saved to: {entities_path}")
        print(f"🔑 Keywords saved to: {keywords_path}")
        
        return {
            "nlp_processed_path": nlp_processed_path,
            "sentiment_path": sentiment_path,
            "entities_path": entities_path,
            "keywords_path": keywords_path,
            "processed_article_count": len(nlp_results)
        }
    
    @task
    def publish(nlp_result: Dict[str, str], **context) -> Dict[str, str]:
        """
        Create business-ready datasets for analytics.
        
        Args:
            nlp_result: Output from nlp task
            
        Returns:
            Dict with paths to published datasets
        """
        import os
        import pandas as pd
        from datetime import datetime
        
        # Load IO paths configuration
        io_paths = load_io_paths()
        ds = context['ds']
        
        # Input paths
        nlp_processed_path = nlp_result["nlp_processed_path"]
        sentiment_path = nlp_result["sentiment_path"]
        entities_path = nlp_result["entities_path"]
        keywords_path = nlp_result["keywords_path"]
        
        # Output paths
        daily_summary_path = io_paths['gold']['daily_summary'].replace('{{ ds }}', ds)
        trending_topics_path = io_paths['gold']['trending_topics'].replace('{{ ds }}', ds)
        sentiment_trends_path = io_paths['gold']['sentiment_trends'].replace('{{ ds }}', ds)
        
        # Ensure directories exist
        os.makedirs(os.path.dirname(daily_summary_path), exist_ok=True)
        
        # Load processed data
        df_nlp = pd.read_parquet(nlp_processed_path)
        df_sentiment = pd.read_parquet(sentiment_path)
        df_entities = pd.read_parquet(entities_path)
        df_keywords = pd.read_parquet(keywords_path)
        
        # Create daily summary
        sentiment_counts = df_sentiment['sentiment'].value_counts()
        daily_summary = {
            "date": ds,
            "total_articles": len(df_nlp),
            "avg_sentiment_score": df_sentiment['sentiment_score'].mean(),
            "positive_articles": sentiment_counts.get('positive', 0),
            "negative_articles": sentiment_counts.get('negative', 0),
            "neutral_articles": sentiment_counts.get('neutral', 0),
            "total_entities": len(df_entities),
            "unique_entities": df_entities['entity'].nunique(),
            "total_keywords": len(df_keywords),
            "unique_keywords": df_keywords['keyword'].nunique(),
            "avg_readability": df_nlp['readability_score'].mean(),
            "created_at": datetime.now().isoformat()
        }
        
        pd.DataFrame([daily_summary]).to_csv(daily_summary_path, index=False)
        
        # Create trending topics (top entities by frequency)
        trending_entities = (df_entities.groupby('entity')
                           .agg({
                               'article_id': 'count',
                               'confidence': 'mean'
                           })
                           .rename(columns={'article_id': 'mention_count'})
                           .sort_values('mention_count', ascending=False)
                           .head(10)
                           .reset_index())
        
        trending_entities['date'] = ds
        trending_entities['rank'] = range(1, len(trending_entities) + 1)
        trending_entities.to_csv(trending_topics_path, index=False)
        
        # Create sentiment trends
        sentiment_trends = df_sentiment.groupby('sentiment').agg({
            'sentiment_score': ['count', 'mean', 'std'],
            'confidence': 'mean'
        }).round(3)
        
        sentiment_trends.columns = ['article_count', 'avg_score', 'score_std', 'avg_confidence']
        sentiment_trends = sentiment_trends.reset_index()
        sentiment_trends['date'] = ds
        sentiment_trends.to_csv(sentiment_trends_path, index=False)
        
        print(f"✅ Published analytics datasets for {ds}")
        print(f"📊 Daily summary: {daily_summary_path}")
        print(f"📈 Trending topics: {trending_topics_path}")
        print(f"💭 Sentiment trends: {sentiment_trends_path}")
        print(f"📋 Summary: {daily_summary['total_articles']} articles, "
              f"{daily_summary['avg_sentiment_score']:.3f} avg sentiment")
        
        return {
            "daily_summary_path": daily_summary_path,
            "trending_topics_path": trending_topics_path,
            "sentiment_trends_path": sentiment_trends_path,
            "summary": daily_summary
        }
    
    # Define task dependencies using TaskFlow API
    scrape_result = scrape()
    clean_result = clean(scrape_result)
    nlp_result = nlp(clean_result)
    publish_result = publish(nlp_result)


# Create the DAG instance
news_pipeline_dag = news_pipeline()

# Configure SLA for the clean task (Issue #190)
# Set SLA to 15 minutes to demonstrate SLA monitoring
if hasattr(news_pipeline_dag, 'get_task') and news_pipeline_dag.get_task('clean', None):
    clean_task = news_pipeline_dag.get_task('clean')
    clean_task.sla = timedelta(minutes=15)
    
    # Add SLA miss callback for logging
    def sla_miss_callback(dag, task_list, blocking_task_list, slas, blocking_tis):
        """
        Callback function for SLA misses.
        Logs SLA violations for monitoring and alerting.
        """
        from airflow.utils.log.logging_mixin import LoggingMixin
        logger = LoggingMixin().log
        
        for sla in slas:
            logger.warning(
                f"🚨 SLA MISS: Task '{sla.task_id}' in DAG '{sla.dag_id}' "
                f"missed SLA. Expected by: {sla.execution_date + sla.sla}, "
                f"Actual completion: Not completed yet"
            )
            
        for blocking_ti in blocking_tis:
            logger.warning(
                f"⏳ BLOCKING: Task '{blocking_ti.task_id}' is blocking SLA compliance"
            )
    
    # Apply SLA miss callback to the DAG
    news_pipeline_dag.sla_miss_callback = sla_miss_callback
