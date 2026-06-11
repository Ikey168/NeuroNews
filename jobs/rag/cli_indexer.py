#!/usr/bin/env python3
"""
CLI RAG Indexer for Issue #230
Reads content from parquet/jsonl files, chunks, embeds, and upserts to PostgreSQL.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union, Any

import yaml
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import numpy as np

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from services.rag import normalize_article, chunk_text
from services.embeddings import get_embedding_provider

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CLIIndexer:
    """CLI-focused RAG indexer for content processing and database upsert."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the CLI indexer with configuration."""
        self.config = self._load_config(config_path)
        self.embedding_provider = None
        self.db_connection = None
        
        # Processing statistics
        self.stats = {
            'start_time': None,
            'end_time': None,
            'files_processed': 0,
            'documents_read': 0,
            'documents_filtered': 0,
            'chunks_created': 0,
            'embeddings_generated': 0,
            'records_upserted': 0,
            'errors': 0,
        }
    
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        config_paths = []
        
        if config_path:
            config_paths.append(Path(config_path))
        
        # Default paths to check
        config_paths.extend([
            Path('configs/indexer.yaml'),
            Path('configs/indexer.yml'),
            Path(__file__).parent.parent.parent / 'configs' / 'indexer.yaml',
        ])
        
        for path in config_paths:
            if path.exists():
                logger.info(f"Loading config from: {path}")
                with open(path, 'r') as f:
                    config = yaml.safe_load(f)
                
                # Environment variable substitution
                config = self._substitute_env_vars(config)
                return config
        
        logger.warning("No config file found, using defaults")
        return self._default_config()
    
    def _substitute_env_vars(self, obj):
        """Recursively substitute environment variables in config."""
        if isinstance(obj, dict):
            return {k: self._substitute_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._substitute_env_vars(item) for item in obj]
        elif isinstance(obj, str):
            # Handle ${VAR:default} pattern
            import re
            pattern = r'\$\{([^:}]+)(?::([^}]*))?\}'
            
            def replacer(match):
                var_name = match.group(1)
                default_value = match.group(2) or ''
                return os.getenv(var_name, default_value)
            
            return re.sub(pattern, replacer, obj)
        else:
            return obj
    
    def _default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'database': {
                'host': 'localhost',
                'port': 5433,
                'database': 'neuronews_vector',
                'user': 'neuronews',
                'password': 'neuronews_vector_pass',
                'table_name': 'chunks',
            },
            'embedding': {
                'provider': 'local',
                'model': 'all-MiniLM-L6-v2',
                'batch_size': 32,
            },
            'chunking': {
                'max_chars': 1000,
                'overlap_chars': 100,
                'split_on': 'sentence',
                'min_chunk_chars': 50,
            },
            'processing': {
                'batch_size': 100,
                'progress_interval': 10,
            },
            'filters': {
                'min_content_length': 100,
                'languages': ['en', 'unknown'],
            },
        }
    
    def connect_database(self):
        """Connect to PostgreSQL database."""
        try:
            db_config = self.config['database']
            self.db_connection = psycopg2.connect(
                host=db_config['host'],
                port=db_config['port'],
                database=db_config['database'],
                user=db_config['user'],
                password=db_config['password']
            )
            
            logger.info(f"Connected to database: {db_config['database']}@{db_config['host']}:{db_config['port']}")
            
            # Test pgvector extension
            with self.db_connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                if not cursor.fetchone():
                    logger.warning("pgvector extension not found")
                
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def initialize_embedding_provider(self):
        """Initialize the embedding provider."""
        try:
            embed_config = self.config['embedding']
            self.embedding_provider = get_embedding_provider(
                provider=embed_config['provider'],
                model_name=embed_config['model'],
                batch_size=embed_config.get('batch_size', 32),
            )
            
            logger.info(f"Initialized embedding provider: {self.embedding_provider.name()}")
            logger.info(f"Embedding dimension: {self.embedding_provider.dim()}")
            
        except Exception as e:
            logger.error(f"Failed to initialize embedding provider: {e}")
            raise
    
    def read_content_files(self, source_path: str) -> pd.DataFrame:
        """Read content from parquet/jsonl files."""
        source_path = Path(source_path)
        
        if not source_path.exists():
            raise FileNotFoundError(f"Source path not found: {source_path}")
        
        dataframes = []
        
        if source_path.is_file():
            # Single file
            files = [source_path]
        else:
            # Directory - find all parquet and jsonl files
            files = list(source_path.glob("*.parquet")) + list(source_path.glob("*.jsonl"))
            if not files:
                raise ValueError(f"No parquet or jsonl files found in {source_path}")
        
        for file_path in files:
            logger.info(f"Reading file: {file_path}")
            try:
                if file_path.suffix == '.parquet':
                    df = pd.read_parquet(file_path)
                elif file_path.suffix == '.jsonl':
                    df = pd.read_json(file_path, lines=True)
                else:
                    logger.warning(f"Skipping unsupported file: {file_path}")
                    continue
                
                dataframes.append(df)
                self.stats['files_processed'] += 1
                
            except Exception as e:
                logger.error(f"Failed to read {file_path}: {e}")
                self.stats['errors'] += 1
                continue
        
        if not dataframes:
            raise ValueError("No data loaded from source files")
        
        # Combine all dataframes
        combined_df = pd.concat(dataframes, ignore_index=True)
        self.stats['documents_read'] = len(combined_df)
        
        logger.info(f"Loaded {len(combined_df)} documents from {len(files)} files")
        return combined_df
    
    def filter_content(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply content filters."""
        initial_count = len(df)
        filters = self.config['filters']
        
        # Ensure required columns
        required_columns = ['content']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
        
        # Filter by content length
        min_length = filters.get('min_content_length', 100)
        max_length = filters.get('max_content_length', 500000)
        
        df = df[
            (df['content'].str.len() >= min_length) & 
            (df['content'].str.len() <= max_length)
        ]
        logger.info(f"Content length filter ({min_length}-{max_length} chars): {len(df)}/{initial_count}")
        
        # Filter by language if column exists
        if 'language' in df.columns and filters.get('languages'):
            allowed_languages = filters['languages']
            df = df[df['language'].fillna('unknown').isin(allowed_languages)]
            logger.info(f"Language filter ({allowed_languages}): {len(df)}/{initial_count}")
        
        # Filter by excluded sources if column exists
        if 'source' in df.columns and filters.get('exclude_sources'):
            excluded_sources = filters['exclude_sources']
            df = df[~df['source'].isin(excluded_sources)]
            logger.info(f"Excluded sources filter: {len(df)}/{initial_count}")
        
        self.stats['documents_filtered'] = len(df)
        logger.info(f"Filtering complete: {len(df)}/{initial_count} documents retained")
        
        return df
    
    def process_documents(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Process documents through chunking pipeline."""
        chunk_config = self.config['chunking']
        processed_records = []
        
        for idx, row in df.iterrows():
            try:
                # Extract document metadata
                doc_id = str(row.get('id', row.get('doc_id', f'doc_{idx}')))
                content = row.get('content', '')
                
                if not content:
                    logger.warning(f"Empty content for document {doc_id}")
                    continue
                
                # Build metadata dict
                metadata = {
                    'doc_id': doc_id,
                    'title': row.get('title', ''),
                    'source': row.get('source', ''),
                    'published_at': row.get('published_at', row.get('timestamp')),
                    'url': row.get('url', ''),
                    'language': row.get('language', 'unknown'),
                }
                
                # Normalize article content
                normalized = normalize_article(content, metadata)
                
                # Create chunks
                chunks = chunk_text(
                    normalized['content'],
                    max_chars=chunk_config['max_chars'],
                    overlap_chars=chunk_config['overlap_chars'],
                    split_on=chunk_config['split_on'],
                    metadata=metadata,
                )
                
                # Convert chunks to database records
                for idx, chunk in enumerate(chunks):
                    record = {
                        'doc_id': doc_id,
                        'chunk_id': chunk['chunk_id'],
                        'title': normalized.get('title', metadata.get('title', '')),
                        'content': chunk['text'],
                        'word_count': chunk['word_count'],
                        'char_count': chunk['char_count'],
                        'start_offset': chunk['start_offset'],
                        'end_offset': chunk['end_offset'],
                        'source': metadata['source'],
                        'published_at': metadata['published_at'],
                        'url': metadata['url'],
                        'language': normalized.get('language', metadata['language']),
                        'chunk_metadata': chunk['metadata'],
                        'chunk_index': idx,  # Use enumeration index
                    }
                    processed_records.append(record)
                
                self.stats['chunks_created'] += len(chunks)
                
                # Progress logging
                if (idx + 1) % self.config['processing']['progress_interval'] == 0:
                    logger.info(f"Processed {idx + 1} documents, created {self.stats['chunks_created']} chunks")
                
            except Exception as e:
                logger.error(f"Error processing document {idx}: {e}")
                self.stats['errors'] += 1
                continue
        
        logger.info(f"Document processing complete: {len(processed_records)} chunks from {len(df)} documents")
        return processed_records
    
    def generate_embeddings(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate embeddings for chunk records."""
        if not records:
            return records
        
        texts = [record['content'] for record in records]
        batch_size = self.config['embedding']['batch_size']
        
        logger.info(f"Generating embeddings for {len(texts)} chunks in batches of {batch_size}")
        
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            
            try:
                batch_embeddings = self.embedding_provider.embed_texts(batch_texts)
                all_embeddings.extend(batch_embeddings)
                
                self.stats['embeddings_generated'] += len(batch_embeddings)
                
                if (i // batch_size) % 5 == 0:
                    logger.info(f"Generated embeddings for batch {i // batch_size + 1}")
                
            except Exception as e:
                logger.error(f"Error generating embeddings for batch {i // batch_size}: {e}")
                # Add zero embeddings for failed batch
                zero_embedding = np.zeros(self.embedding_provider.dim())
                all_embeddings.extend([zero_embedding.tolist()] * len(batch_texts))
                self.stats['errors'] += 1
        
        # Add embeddings to records
        for record, embedding in zip(records, all_embeddings):
            if isinstance(embedding, np.ndarray):
                embedding = embedding.tolist()
            record['embedding'] = embedding
        
        logger.info(f"Embedding generation complete: {len(all_embeddings)} embeddings")
        return records
    
    def upsert_to_database(self, records: List[Dict[str, Any]]):
        """Upsert records to PostgreSQL chunks table."""
        if not records:
            logger.info("No records to upsert")
            return
        
        table_name = self.config['database'].get('table_name', 'chunks')
        batch_size = self.config['processing']['batch_size']
        
        logger.info(f"Upserting {len(records)} records to {table_name} table")
        
        try:
            with self.db_connection.cursor() as cursor:
                # Upsert query with conflict resolution on (doc_id, chunk_id)
                upsert_query = f"""
                INSERT INTO {table_name} (
                    doc_id, chunk_id, title, content, word_count, char_count,
                    start_position, end_position, source, published_at, url, language,
                    embedding, metadata, created_at, updated_at, chunk_index
                ) VALUES %s
                ON CONFLICT (doc_id, chunk_id) 
                DO UPDATE SET
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    word_count = EXCLUDED.word_count,
                    char_count = EXCLUDED.char_count,
                    start_position = EXCLUDED.start_position,
                    end_position = EXCLUDED.end_position,
                    source = EXCLUDED.source,
                    published_at = EXCLUDED.published_at,
                    url = EXCLUDED.url,
                    language = EXCLUDED.language,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at,
                    chunk_index = EXCLUDED.chunk_index
                """
                
                # Process in batches
                for i in range(0, len(records), batch_size):
                    batch_records = records[i:i + batch_size]
                    
                    # Prepare values for this batch
                    current_time = datetime.now()
                    values = []
                    
                    for record in batch_records:
                        # Handle published_at conversion
                        published_at = record.get('published_at')
                        if isinstance(published_at, str):
                            try:
                                from dateutil.parser import parse
                                published_at = parse(published_at)
                            except:
                                published_at = None
                        elif hasattr(published_at, 'to_pydatetime'):
                            # Handle pandas Timestamp
                            published_at = published_at.to_pydatetime()
                        
                        # Convert chunk_metadata to JSON string if needed
                        chunk_metadata = record['chunk_metadata']
                        if not isinstance(chunk_metadata, str):
                            chunk_metadata = json.dumps(chunk_metadata, default=str)
                        
                        values.append((
                            record['doc_id'],
                            record['chunk_id'],
                            record['title'],
                            record['content'],
                            record['word_count'],
                            record['char_count'],
                            record['start_offset'],
                            record['end_offset'],
                            record['source'],
                            published_at,
                            record['url'],
                            record['language'],
                            record['embedding'],
                            chunk_metadata,
                            current_time,
                            current_time,
                            record['chunk_index'],
                        ))
                    
                    # Execute batch upsert
                    execute_values(
                        cursor,
                        upsert_query,
                        values,
                        template=None,
                        page_size=100
                    )
                    
                    self.stats['records_upserted'] += len(batch_records)
                    
                    if (i // batch_size) % 10 == 0:
                        logger.info(f"Upserted batch {i // batch_size + 1}, total: {self.stats['records_upserted']}")
                
                # Commit all changes
                self.db_connection.commit()
                logger.info(f"Successfully upserted {self.stats['records_upserted']} records")
                
        except Exception as e:
            logger.error(f"Error during database upsert: {e}")
            self.db_connection.rollback()
            raise
    
    def log_progress(self, operation: str):
        """Log progress to search_logs table."""
        if not self.config.get('logging', {}).get('progress_to_db', False):
            return
        
        try:
            log_table = self.config['logging'].get('log_table', 'search_logs')
            
            # Create a JSON-serializable copy of stats
            serializable_stats = {}
            for key, value in self.stats.items():
                if isinstance(value, datetime):
                    serializable_stats[key] = value.isoformat() if value else None
                else:
                    serializable_stats[key] = value
            
            with self.db_connection.cursor() as cursor:
                cursor.execute(f"""
                    INSERT INTO {log_table} (
                        query_text, query_type, results_count, processing_time_ms,
                        metadata, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    operation,
                    'indexer_progress',
                    self.stats.get('records_upserted', 0),
                    0,  # processing_time_ms
                    json.dumps(serializable_stats),
                    datetime.now()
                ))
                
                self.db_connection.commit()
                
        except Exception as e:
            logger.warning(f"Failed to log progress: {e}")
    
    def run(self, source_path: str, dry_run: bool = False):
        """Run the complete indexing pipeline."""
        self.stats['start_time'] = datetime.now()
        
        try:
            logger.info(f"Starting CLI indexer for: {source_path}")
            logger.info(f"Dry run mode: {dry_run}")
            
            # Initialize components
            if not dry_run:
                self.connect_database()
            self.initialize_embedding_provider()
            
            # Load content
            content_df = self.read_content_files(source_path)
            
            # Apply filters
            filtered_df = self.filter_content(content_df)
            
            if len(filtered_df) == 0:
                logger.warning("No content remains after filtering")
                return
            
            # Process documents into chunks
            chunk_records = self.process_documents(filtered_df)
            
            if not chunk_records:
                logger.warning("No chunks created from documents")
                return
            
            # Generate embeddings
            records_with_embeddings = self.generate_embeddings(chunk_records)
            
            # Upsert to database
            if not dry_run:
                self.upsert_to_database(records_with_embeddings)
                self.log_progress("indexing_complete")
            else:
                logger.info(f"DRY RUN: Would upsert {len(records_with_embeddings)} records")
            
            self.stats['end_time'] = datetime.now()
            self._print_final_stats()
            
        except Exception as e:
            logger.error(f"Indexing pipeline failed: {e}")
            self.stats['end_time'] = datetime.now()
            if not dry_run and self.db_connection:
                self.log_progress("indexing_failed")
            raise
        finally:
            if self.db_connection:
                self.db_connection.close()
    
    def _print_final_stats(self):
        """Print final processing statistics."""
        duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        
        print("\n" + "="*60)
        print("INDEXING PIPELINE COMPLETE")
        print("="*60)
        print(f"Duration: {duration:.2f} seconds")
        print(f"Files processed: {self.stats['files_processed']}")
        print(f"Documents read: {self.stats['documents_read']}")
        print(f"Documents filtered: {self.stats['documents_filtered']}")
        print(f"Chunks created: {self.stats['chunks_created']}")
        print(f"Embeddings generated: {self.stats['embeddings_generated']}")
        print(f"Records upserted: {self.stats['records_upserted']}")
        print(f"Errors: {self.stats['errors']}")
        
        if self.stats['documents_read'] > 0:
            docs_per_sec = self.stats['documents_read'] / duration
            print(f"Processing rate: {docs_per_sec:.2f} documents/second")
        
        if self.stats['chunks_created'] > 0:
            chunks_per_doc = self.stats['chunks_created'] / self.stats['documents_filtered']
            print(f"Average chunks per document: {chunks_per_doc:.1f}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="CLI RAG Indexer - Read, chunk, embed, and upsert content",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process parquet files in directory
  python jobs/rag/cli_indexer.py data/silver/news/

  # Process single jsonl file
  python jobs/rag/cli_indexer.py data/raw/articles.jsonl

  # Dry run with custom config
  python jobs/rag/cli_indexer.py data/ --config configs/indexer.yaml --dry-run

  # Debug mode
  python jobs/rag/cli_indexer.py data/ --log-level DEBUG
        """
    )
    
    parser.add_argument(
        "source_path",
        help="Path to source files (parquet/jsonl) or directory containing them"
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to configuration YAML file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without database operations (for testing)"
    )
    parser.add_argument(
        "--log-level",
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Run indexer
    try:
        indexer = CLIIndexer(args.config)
        indexer.run(args.source_path, args.dry_run)
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Indexer failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
