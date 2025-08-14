"""
DynamoDB Article Metadata Manager - Issue #23 Implementation

This module provides comprehensive article metadata indexing in DynamoDB for quick lookups
and full-text search capabilities. It indexes article metadata (title, source, published_date, tags)
and provides efficient query APIs.

Features:
- Store article metadata in DynamoDB with optimized indexing
- Quick lookups by various fields (source, date, tags)
- Full-text search capabilities on title and content
- Batch operations for efficient bulk indexing
- Integration with existing S3 and Redshift storage systems
"""

import boto3
import json
import logging
import time
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict, field
from enum import Enum
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError, BotoCoreError


class IndexType(Enum):
    """Types of metadata indexes."""
    PRIMARY = "primary"
    SOURCE_DATE = "source-date-index"
    TAGS = "tags-index"
    FULLTEXT = "fulltext-index"


class SearchMode(Enum):
    """Search operation modes."""
    EXACT = "exact"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    FUZZY = "fuzzy"


@dataclass
class ArticleMetadataIndex:
    """Article metadata for DynamoDB indexing."""
    
    # Primary identifiers
    article_id: str  # Primary key
    content_hash: str  # Secondary identifier
    
    # Core metadata (Issue #23 requirements)
    title: str
    source: str
    published_date: str  # ISO format: YYYY-MM-DD
    tags: List[str] = field(default_factory=list)
    
    # Extended metadata for comprehensive indexing
    url: str = ""
    author: str = ""
    category: str = ""
    language: str = "en"
    
    # Storage and processing info
    s3_key: str = ""
    redshift_loaded: bool = False
    processing_status: str = "indexed"
    
    # Search and analytics
    title_tokens: List[str] = field(default_factory=list)  # For full-text search
    content_summary: str = ""  # Brief content excerpt for search
    word_count: int = 0
    sentiment_score: Optional[float] = None
    
    # Timestamps
    scraped_date: str = ""  # ISO format with timezone
    indexed_date: str = ""  # When indexed in DynamoDB
    last_updated: str = ""
    
    # Quality and validation
    validation_score: int = 0
    content_quality: str = "unknown"
    
    def __post_init__(self):
        """Initialize computed fields."""
        if not self.indexed_date:
            self.indexed_date = datetime.now(timezone.utc).isoformat()
        
        if not self.last_updated:
            self.last_updated = self.indexed_date
            
        # Generate title tokens for full-text search
        if self.title and not self.title_tokens:
            self.title_tokens = self._tokenize_text(self.title)
    
    def _tokenize_text(self, text: str) -> List[str]:
        """Tokenize text for full-text search."""
        import re
        # Remove punctuation and convert to lowercase
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        # Split and filter short words
        tokens = [word.strip() for word in text.split() if len(word.strip()) > 2]
        return list(set(tokens))  # Remove duplicates
    
    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Convert to DynamoDB item format."""
        return {
            'article_id': self.article_id,
            'content_hash': self.content_hash,
            'title': self.title,
            'source': self.source,
            'published_date': self.published_date,
            'tags': self.tags,
            'url': self.url,
            'author': self.author,
            'category': self.category,
            'language': self.language,
            's3_key': self.s3_key,
            'redshift_loaded': self.redshift_loaded,
            'processing_status': self.processing_status,
            'title_tokens': self.title_tokens,
            'content_summary': self.content_summary,
            'word_count': self.word_count,
            'sentiment_score': self.sentiment_score,
            'scraped_date': self.scraped_date,
            'indexed_date': self.indexed_date,
            'last_updated': self.last_updated,
            'validation_score': self.validation_score,
            'content_quality': self.content_quality,
            
            # Computed fields for efficient querying
            'source_date': f"{self.source}#{self.published_date}",
            'date_source': f"{self.published_date}#{self.source}",
            'category_date': f"{self.category}#{self.published_date}",
            'year_month': self.published_date[:7] if len(self.published_date) >= 7 else "",
            'tags_string': '#'.join(sorted(self.tags)) if self.tags else "",
        }
    
    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> 'ArticleMetadataIndex':
        """Create from DynamoDB item."""
        return cls(
            article_id=item.get('article_id', ''),
            content_hash=item.get('content_hash', ''),
            title=item.get('title', ''),
            source=item.get('source', ''),
            published_date=item.get('published_date', ''),
            tags=item.get('tags', []),
            url=item.get('url', ''),
            author=item.get('author', ''),
            category=item.get('category', ''),
            language=item.get('language', 'en'),
            s3_key=item.get('s3_key', ''),
            redshift_loaded=item.get('redshift_loaded', False),
            processing_status=item.get('processing_status', 'indexed'),
            title_tokens=item.get('title_tokens', []),
            content_summary=item.get('content_summary', ''),
            word_count=item.get('word_count', 0),
            sentiment_score=item.get('sentiment_score'),
            scraped_date=item.get('scraped_date', ''),
            indexed_date=item.get('indexed_date', ''),
            last_updated=item.get('last_updated', ''),
            validation_score=item.get('validation_score', 0),
            content_quality=item.get('content_quality', 'unknown'),
        )


@dataclass
class QueryResult:
    """Result of a metadata query."""
    items: List[ArticleMetadataIndex]
    count: int
    total_count: Optional[int] = None
    next_token: Optional[str] = None
    execution_time_ms: Optional[float] = None
    query_info: Optional[Dict[str, Any]] = None


@dataclass
class SearchQuery:
    """Full-text search query configuration."""
    query_text: str
    fields: List[str] = field(default_factory=lambda: ['title', 'content_summary'])
    search_mode: SearchMode = SearchMode.CONTAINS
    limit: int = 50
    filters: Optional[Dict[str, Any]] = None
    date_range: Optional[Dict[str, str]] = None  # {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}


@dataclass
class DynamoDBMetadataConfig:
    """Configuration for DynamoDB metadata indexing."""
    table_name: str = "neuronews-article-metadata"
    region: str = "us-east-1"
    
    # Performance settings
    read_capacity_units: int = 10
    write_capacity_units: int = 10
    
    # Batch settings
    batch_size: int = 25  # DynamoDB batch limit
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # Search settings
    search_limit: int = 100
    enable_full_text_search: bool = True
    
    # Index settings
    create_indexes: bool = True
    enable_point_in_time_recovery: bool = True


class DynamoDBMetadataManager:
    """
    DynamoDB Article Metadata Manager for Issue #23.
    
    Provides comprehensive article metadata indexing with:
    - Quick lookups by title, source, published_date, tags
    - Full-text search capabilities
    - Batch operations for efficient bulk indexing
    - Integration with S3 and Redshift storage
    """
    
    def __init__(self, 
                 config: DynamoDBMetadataConfig,
                 aws_credentials: Optional[Dict[str, str]] = None):
        """
        Initialize DynamoDB metadata manager.
        
        Args:
            config: DynamoDB configuration
            aws_credentials: Optional AWS credentials
        """
        self.config = config
        self.table_name = config.table_name
        self.logger = logging.getLogger(__name__)
        
        # Initialize AWS clients
        session_kwargs = {'region_name': config.region}
        if aws_credentials:
            session_kwargs.update(aws_credentials)
            
        self.session = boto3.Session(**session_kwargs)
        self.dynamodb = self.session.resource('dynamodb')
        self.dynamodb_client = self.session.client('dynamodb')
        
        # Initialize table
        self.table = None
        self._initialize_table()
    
    def _initialize_table(self):
        """Initialize DynamoDB table and indexes."""
        try:
            self.table = self.dynamodb.Table(self.table_name)
            self.table.meta.client.describe_table(TableName=self.table_name)
            self.logger.info(f"DynamoDB table exists: {self.table_name}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                self.logger.info(f"Creating DynamoDB table: {self.table_name}")
                self._create_table()
            else:
                raise
    
    def _create_table(self):
        """Create DynamoDB table with optimized indexes."""
        try:
            # Global Secondary Indexes for efficient querying
            global_secondary_indexes = []
            
            if self.config.create_indexes:
                global_secondary_indexes = [
                    {
                        'IndexName': 'source-date-index',
                        'KeySchema': [
                            {'AttributeName': 'source', 'KeyType': 'HASH'},
                            {'AttributeName': 'published_date', 'KeyType': 'RANGE'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'ProvisionedThroughput': {
                            'ReadCapacityUnits': self.config.read_capacity_units,
                            'WriteCapacityUnits': self.config.write_capacity_units
                        }
                    },
                    {
                        'IndexName': 'date-source-index',
                        'KeySchema': [
                            {'AttributeName': 'published_date', 'KeyType': 'HASH'},
                            {'AttributeName': 'source', 'KeyType': 'RANGE'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'ProvisionedThroughput': {
                            'ReadCapacityUnits': self.config.read_capacity_units,
                            'WriteCapacityUnits': self.config.write_capacity_units
                        }
                    },
                    {
                        'IndexName': 'category-date-index',
                        'KeySchema': [
                            {'AttributeName': 'category', 'KeyType': 'HASH'},
                            {'AttributeName': 'published_date', 'KeyType': 'RANGE'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'ProvisionedThroughput': {
                            'ReadCapacityUnits': self.config.read_capacity_units,
                            'WriteCapacityUnits': self.config.write_capacity_units
                        }
                    }
                ]
            
            # Create table
            table = self.dynamodb.create_table(
                TableName=self.table_name,
                KeySchema=[
                    {'AttributeName': 'article_id', 'KeyType': 'HASH'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'article_id', 'AttributeType': 'S'},
                    {'AttributeName': 'source', 'AttributeType': 'S'},
                    {'AttributeName': 'published_date', 'AttributeType': 'S'},
                    {'AttributeName': 'category', 'AttributeType': 'S'},
                ],
                BillingMode='PROVISIONED',
                ProvisionedThroughput={
                    'ReadCapacityUnits': self.config.read_capacity_units,
                    'WriteCapacityUnits': self.config.write_capacity_units
                },
                GlobalSecondaryIndexes=global_secondary_indexes
            )
            
            # Wait for table to be created
            table.meta.client.get_waiter('table_exists').wait(
                TableName=self.table_name,
                WaiterConfig={'Delay': 2, 'MaxAttempts': 30}
            )
            
            # Enable Point-in-Time Recovery if configured
            if self.config.enable_point_in_time_recovery:
                self.dynamodb_client.update_continuous_backups(
                    TableName=self.table_name,
                    PointInTimeRecoverySpecification={'PointInTimeRecoveryEnabled': True}
                )
            
            self.table = table
            self.logger.info(f"Created DynamoDB table with indexes: {self.table_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to create DynamoDB table: {e}")
            raise
    
    async def index_article_metadata(self, article_data: Dict[str, Any]) -> ArticleMetadataIndex:
        """
        Index single article metadata in DynamoDB.
        
        Args:
            article_data: Article data dictionary
            
        Returns:
            ArticleMetadataIndex: Indexed metadata record
        """
        start_time = time.time()
        
        try:
            # Create metadata record
            metadata = self._create_metadata_from_article(article_data)
            
            # Store in DynamoDB
            self.table.put_item(Item=metadata.to_dynamodb_item())
            
            execution_time = (time.time() - start_time) * 1000
            self.logger.debug(f"Indexed article metadata: {metadata.article_id} ({execution_time:.2f}ms)")
            
            return metadata
            
        except Exception as e:
            self.logger.error(f"Failed to index article metadata: {e}")
            raise
    
    async def batch_index_articles(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Batch index multiple articles for efficiency.
        
        Args:
            articles: List of article data dictionaries
            
        Returns:
            Dict with indexing results and statistics
        """
        start_time = time.time()
        indexed_count = 0
        failed_count = 0
        failed_articles = []
        
        try:
            # Process in batches (DynamoDB limit is 25)
            for i in range(0, len(articles), self.config.batch_size):
                batch = articles[i:i + self.config.batch_size]
                batch_result = await self._process_batch(batch)
                
                indexed_count += batch_result['indexed']
                failed_count += batch_result['failed']
                failed_articles.extend(batch_result['failed_items'])
            
            execution_time = (time.time() - start_time) * 1000
            
            result = {
                'status': 'completed',
                'total_articles': len(articles),
                'indexed_count': indexed_count,
                'failed_count': failed_count,
                'failed_articles': failed_articles,
                'execution_time_ms': execution_time,
                'indexing_rate': len(articles) / (execution_time / 1000) if execution_time > 0 else 0
            }
            
            self.logger.info(f"Batch indexed {indexed_count}/{len(articles)} articles ({execution_time:.2f}ms)")
            return result
            
        except Exception as e:
            self.logger.error(f"Batch indexing failed: {e}")
            raise
    
    async def _process_batch(self, batch: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process a single batch of articles."""
        indexed = 0
        failed = 0
        failed_items = []
        
        try:
            with self.table.batch_writer() as batch_writer:
                for article in batch:
                    try:
                        metadata = self._create_metadata_from_article(article)
                        batch_writer.put_item(Item=metadata.to_dynamodb_item())
                        indexed += 1
                    except Exception as e:
                        failed += 1
                        failed_items.append({
                            'article_id': article.get('id', 'unknown'),
                            'error': str(e)
                        })
                        self.logger.warning(f"Failed to index article: {e}")
            
        except Exception as e:
            self.logger.error(f"Batch write failed: {e}")
            failed = len(batch)
            failed_items = [{'article_id': article.get('id', 'unknown'), 'error': str(e)} for article in batch]
        
        return {
            'indexed': indexed,
            'failed': failed,
            'failed_items': failed_items
        }
    
    def _create_metadata_from_article(self, article_data: Dict[str, Any]) -> ArticleMetadataIndex:
        """Create metadata record from article data."""
        # Generate article ID if not present
        article_id = article_data.get('id') or article_data.get('article_id')
        if not article_id:
            content_for_id = f"{article_data.get('url', '')}{article_data.get('title', '')}"
            article_id = hashlib.md5(content_for_id.encode()).hexdigest()
        
        # Generate content hash
        content_hash = article_data.get('content_hash')
        if not content_hash:
            content_for_hash = article_data.get('content', '') or article_data.get('title', '')
            content_hash = hashlib.sha256(content_for_hash.encode()).hexdigest()
        
        # Extract tags from various sources
        tags = []
        if 'tags' in article_data:
            tags = article_data['tags'] if isinstance(article_data['tags'], list) else [article_data['tags']]
        elif 'category' in article_data:
            tags = [article_data['category']]
        
        # Create metadata record
        return ArticleMetadataIndex(
            article_id=article_id,
            content_hash=content_hash,
            title=article_data.get('title', ''),
            source=article_data.get('source', ''),
            published_date=article_data.get('published_date', ''),
            tags=tags,
            url=article_data.get('url', ''),
            author=article_data.get('author', ''),
            category=article_data.get('category', ''),
            language=article_data.get('language', 'en'),
            s3_key=article_data.get('s3_key', ''),
            redshift_loaded=article_data.get('redshift_loaded', False),
            content_summary=article_data.get('content', '')[:200] if article_data.get('content') else '',
            word_count=article_data.get('word_count', 0),
            sentiment_score=article_data.get('sentiment_score'),
            scraped_date=article_data.get('scraped_date', ''),
            validation_score=article_data.get('validation_score', 0),
            content_quality=article_data.get('content_quality', 'unknown'),
        )
    
    # ============================================
    # Query API Methods (Issue #23 Requirement 2)
    # ============================================
    
    async def get_article_by_id(self, article_id: str) -> Optional[ArticleMetadataIndex]:
        """Get article metadata by ID."""
        try:
            response = self.table.get_item(Key={'article_id': article_id})
            if 'Item' in response:
                return ArticleMetadataIndex.from_dynamodb_item(response['Item'])
            return None
        except Exception as e:
            self.logger.error(f"Failed to get article by ID {article_id}: {e}")
            raise
    
    async def get_articles_by_source(self, 
                                   source: str, 
                                   limit: int = 50,
                                   start_date: Optional[str] = None,
                                   end_date: Optional[str] = None) -> QueryResult:
        """Get articles by source with optional date filtering."""
        start_time = time.time()
        
        try:
            query_kwargs = {
                'IndexName': 'source-date-index',
                'KeyConditionExpression': Key('source').eq(source),
                'Limit': limit
            }
            
            # Add date range filtering
            if start_date or end_date:
                filter_expressions = []
                if start_date:
                    filter_expressions.append(Attr('published_date').gte(start_date))
                if end_date:
                    filter_expressions.append(Attr('published_date').lte(end_date))
                
                if filter_expressions:
                    query_kwargs['FilterExpression'] = filter_expressions[0]
                    for expr in filter_expressions[1:]:
                        query_kwargs['FilterExpression'] = query_kwargs['FilterExpression'] & expr
            
            response = self.table.query(**query_kwargs)
            
            items = [ArticleMetadataIndex.from_dynamodb_item(item) for item in response['Items']]
            execution_time = (time.time() - start_time) * 1000
            
            return QueryResult(
                items=items,
                count=len(items),
                execution_time_ms=execution_time,
                next_token=response.get('LastEvaluatedKey'),
                query_info={'source': source, 'date_range': {'start': start_date, 'end': end_date}}
            )
            
        except Exception as e:
            self.logger.error(f"Failed to query articles by source {source}: {e}")
            raise
    
    async def get_articles_by_date_range(self,
                                       start_date: str,
                                       end_date: str,
                                       limit: int = 100) -> QueryResult:
        """Get articles within a date range."""
        start_time = time.time()
        
        try:
            # Use scan with filter for date range queries
            response = self.table.scan(
                FilterExpression=Attr('published_date').between(start_date, end_date),
                Limit=limit
            )
            
            items = [ArticleMetadataIndex.from_dynamodb_item(item) for item in response['Items']]
            execution_time = (time.time() - start_time) * 1000
            
            return QueryResult(
                items=items,
                count=len(items),
                execution_time_ms=execution_time,
                query_info={'date_range': {'start': start_date, 'end': end_date}}
            )
            
        except Exception as e:
            self.logger.error(f"Failed to query articles by date range: {e}")
            raise
    
    async def get_articles_by_tags(self, 
                                 tags: List[str],
                                 match_all: bool = False,
                                 limit: int = 50) -> QueryResult:
        """Get articles by tags."""
        start_time = time.time()
        
        try:
            # Build filter expression for tags
            if match_all:
                # All tags must be present
                filter_expr = None
                for tag in tags:
                    tag_expr = Attr('tags').contains(tag)
                    filter_expr = tag_expr if filter_expr is None else filter_expr & tag_expr
            else:
                # Any tag matches
                filter_expr = None
                for tag in tags:
                    tag_expr = Attr('tags').contains(tag)
                    filter_expr = tag_expr if filter_expr is None else filter_expr | tag_expr
            
            response = self.table.scan(
                FilterExpression=filter_expr,
                Limit=limit
            )
            
            items = [ArticleMetadataIndex.from_dynamodb_item(item) for item in response['Items']]
            execution_time = (time.time() - start_time) * 1000
            
            return QueryResult(
                items=items,
                count=len(items),
                execution_time_ms=execution_time,
                query_info={'tags': tags, 'match_all': match_all}
            )
            
        except Exception as e:
            self.logger.error(f"Failed to query articles by tags: {e}")
            raise
    
    async def get_articles_by_category(self,
                                     category: str,
                                     limit: int = 50,
                                     start_date: Optional[str] = None) -> QueryResult:
        """Get articles by category."""
        start_time = time.time()
        
        try:
            query_kwargs = {
                'IndexName': 'category-date-index',
                'KeyConditionExpression': Key('category').eq(category),
                'Limit': limit
            }
            
            if start_date:
                query_kwargs['KeyConditionExpression'] = query_kwargs['KeyConditionExpression'] & Key('published_date').gte(start_date)
            
            response = self.table.query(**query_kwargs)
            
            items = [ArticleMetadataIndex.from_dynamodb_item(item) for item in response['Items']]
            execution_time = (time.time() - start_time) * 1000
            
            return QueryResult(
                items=items,
                count=len(items),
                execution_time_ms=execution_time,
                query_info={'category': category, 'start_date': start_date}
            )
            
        except Exception as e:
            self.logger.error(f"Failed to query articles by category: {e}")
            raise
    
    # ============================================
    # Full-text Search API (Issue #23 Requirement 3)
    # ============================================
    
    async def search_articles(self, search_query: SearchQuery) -> QueryResult:
        """
        Perform full-text search on article metadata.
        
        Args:
            search_query: Search configuration
            
        Returns:
            QueryResult with matching articles
        """
        start_time = time.time()
        
        try:
            # Tokenize search query
            search_tokens = self._tokenize_search_query(search_query.query_text)
            
            if not search_tokens:
                return QueryResult(items=[], count=0, execution_time_ms=0)
            
            # Build search filter based on search mode
            filter_expr = self._build_search_filter(search_tokens, search_query)
            
            # Add additional filters
            if search_query.filters:
                additional_filters = self._build_additional_filters(search_query.filters)
                if additional_filters and filter_expr:
                    filter_expr = filter_expr & additional_filters
                elif additional_filters:
                    filter_expr = additional_filters
            
            # Add date range filter
            if search_query.date_range:
                date_filter = self._build_date_range_filter(search_query.date_range)
                if date_filter and filter_expr:
                    filter_expr = filter_expr & date_filter
                elif date_filter:
                    filter_expr = date_filter
            
            # Execute search
            scan_kwargs = {'Limit': search_query.limit}
            if filter_expr:
                scan_kwargs['FilterExpression'] = filter_expr
            
            response = self.table.scan(**scan_kwargs)
            
            # Create result items
            items = [ArticleMetadataIndex.from_dynamodb_item(item) for item in response['Items']]
            
            # Score and sort results
            if search_tokens:
                items = self._score_and_sort_results(items, search_tokens, search_query)
            
            execution_time = (time.time() - start_time) * 1000
            
            return QueryResult(
                items=items,
                count=len(items),
                execution_time_ms=execution_time,
                query_info={
                    'query': search_query.query_text,
                    'tokens': search_tokens,
                    'search_mode': search_query.search_mode.value,
                    'fields': search_query.fields
                }
            )
            
        except Exception as e:
            self.logger.error(f"Full-text search failed: {e}")
            raise
    
    def _tokenize_search_query(self, query_text: str) -> List[str]:
        """Tokenize search query text."""
        import re
        # Common stop words to filter out
        stop_words = {'in', 'on', 'at', 'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'to', 'of', 'for', 'with', 'by', 'from', 'as', 'if', 'then', 'than', 'this', 'that', 'these', 'those'}
        
        # Remove punctuation and convert to lowercase
        query_text = re.sub(r'[^\w\s]', ' ', query_text.lower())
        # Split and filter stop words and very short words (but keep important acronyms)
        tokens = []
        for word in query_text.split():
            word = word.strip()
            if word and word not in stop_words and len(word) >= 1:
                tokens.append(word)
        return tokens
    
    def _build_search_filter(self, search_tokens: List[str], search_query: SearchQuery):
        """Build DynamoDB filter expression for search."""
        if not search_tokens:
            return None
        
        field_filters = []
        
        for field in search_query.fields:
            field_token_filters = []
            
            for token in search_tokens:
                if search_query.search_mode == SearchMode.EXACT:
                    if field == 'title':
                        field_token_filters.append(Attr('title').eq(search_query.query_text))
                    else:
                        field_token_filters.append(Attr(field).contains(token))
                elif search_query.search_mode == SearchMode.CONTAINS:
                    if field == 'title':
                        field_token_filters.append(Attr('title').contains(token))
                    elif field == 'title_tokens':
                        field_token_filters.append(Attr('title_tokens').contains(token))
                    else:
                        field_token_filters.append(Attr(field).contains(token))
                elif search_query.search_mode == SearchMode.STARTS_WITH:
                    field_token_filters.append(Attr(field).begins_with(token))
            
            # Combine tokens for this field (AND logic within field)
            if field_token_filters:
                field_filter = field_token_filters[0]
                for token_filter in field_token_filters[1:]:
                    field_filter = field_filter & token_filter
                field_filters.append(field_filter)
        
        # Combine fields (OR logic between fields)
        if not field_filters:
            return None
        
        final_filter = field_filters[0]
        for field_filter in field_filters[1:]:
            final_filter = final_filter | field_filter
        
        return final_filter
    
    def _build_additional_filters(self, filters: Dict[str, Any]):
        """Build additional filter expressions."""
        filter_expr = None
        
        for field, value in filters.items():
            if isinstance(value, list):
                # Multiple values (OR logic)
                value_filters = [Attr(field).eq(v) for v in value]
                value_filter = value_filters[0]
                for vf in value_filters[1:]:
                    value_filter = value_filter | vf
            else:
                value_filter = Attr(field).eq(value)
            
            filter_expr = value_filter if filter_expr is None else filter_expr & value_filter
        
        return filter_expr
    
    def _build_date_range_filter(self, date_range: Dict[str, str]):
        """Build date range filter expression."""
        filter_expr = None
        
        if 'start' in date_range:
            start_filter = Attr('published_date').gte(date_range['start'])
            filter_expr = start_filter
        
        if 'end' in date_range:
            end_filter = Attr('published_date').lte(date_range['end'])
            filter_expr = end_filter if filter_expr is None else filter_expr & end_filter
        
        return filter_expr
    
    def _score_and_sort_results(self, 
                               items: List[ArticleMetadataIndex], 
                               search_tokens: List[str],
                               search_query: SearchQuery) -> List[ArticleMetadataIndex]:
        """Score and sort search results by relevance."""
        scored_items = []
        
        for item in items:
            score = self._calculate_relevance_score(item, search_tokens, search_query.fields)
            scored_items.append((score, item))
        
        # Sort by score (descending) and return items
        scored_items.sort(key=lambda x: x[0], reverse=True)
        return [item for score, item in scored_items]
    
    def _calculate_relevance_score(self, 
                                 item: ArticleMetadataIndex, 
                                 search_tokens: List[str],
                                 search_fields: List[str]) -> float:
        """Calculate relevance score for search result."""
        score = 0.0
        
        # Field weights
        field_weights = {
            'title': 3.0,
            'title_tokens': 2.5,
            'content_summary': 1.5,
            'tags': 2.0,
            'source': 1.0,
            'author': 1.0
        }
        
        for field in search_fields:
            weight = field_weights.get(field, 1.0)
            field_value = getattr(item, field, '')
            
            if isinstance(field_value, list):
                field_text = ' '.join(field_value).lower()
            else:
                field_text = str(field_value).lower()
            
            # Count token matches
            for token in search_tokens:
                if token in field_text:
                    score += weight
                    # Bonus for exact word matches
                    if f' {token} ' in f' {field_text} ':
                        score += weight * 0.5
        
        return score
    
    # ============================================
    # Analytics and Statistics Methods
    # ============================================
    
    async def get_metadata_statistics(self) -> Dict[str, Any]:
        """Get comprehensive metadata statistics."""
        start_time = time.time()
        
        try:
            # Get total count
            response = self.table.scan(Select='COUNT')
            total_articles = response['Count']
            
            # Get source distribution
            sources = {}
            categories = {}
            monthly_counts = {}
            
            # Sample scan for statistics (limit for performance)
            sample_response = self.table.scan(Limit=1000)
            
            for item in sample_response['Items']:
                metadata = ArticleMetadataIndex.from_dynamodb_item(item)
                
                # Source distribution
                sources[metadata.source] = sources.get(metadata.source, 0) + 1
                
                # Category distribution
                categories[metadata.category] = categories.get(metadata.category, 0) + 1
                
                # Monthly distribution
                if metadata.published_date:
                    month_key = metadata.published_date[:7]  # YYYY-MM
                    monthly_counts[month_key] = monthly_counts.get(month_key, 0) + 1
            
            execution_time = (time.time() - start_time) * 1000
            
            return {
                'total_articles': total_articles,
                'sample_size': len(sample_response['Items']),
                'source_distribution': dict(sorted(sources.items(), key=lambda x: x[1], reverse=True)[:10]),
                'category_distribution': dict(sorted(categories.items(), key=lambda x: x[1], reverse=True)),
                'monthly_distribution': dict(sorted(monthly_counts.items(), reverse=True)[:12]),
                'execution_time_ms': execution_time,
                'table_info': {
                    'table_name': self.table_name,
                    'region': self.config.region,
                    'indexes_enabled': self.config.create_indexes
                }
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get metadata statistics: {e}")
            raise
    
    async def update_article_metadata(self, 
                                    article_id: str, 
                                    updates: Dict[str, Any]) -> bool:
        """Update article metadata."""
        try:
            # Build update expression
            update_expr = "SET last_updated = :timestamp"
            expr_values = {':timestamp': datetime.now(timezone.utc).isoformat()}
            
            for field, value in updates.items():
                if field not in ['article_id', 'indexed_date']:  # Prevent updating primary key
                    update_expr += f", {field} = :{field}"
                    expr_values[f':{field}'] = value
            
            self.table.update_item(
                Key={'article_id': article_id},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values
            )
            
            self.logger.debug(f"Updated metadata for article: {article_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update article metadata {article_id}: {e}")
            return False
    
    async def delete_article_metadata(self, article_id: str) -> bool:
        """Delete article metadata."""
        try:
            self.table.delete_item(Key={'article_id': article_id})
            self.logger.debug(f"Deleted metadata for article: {article_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete article metadata {article_id}: {e}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on DynamoDB table."""
        try:
            # Test table accessibility
            response = self.table.meta.client.describe_table(TableName=self.table_name)
            table_status = response['Table']['TableStatus']
            
            # Test read operation
            test_response = self.table.scan(Limit=1)
            read_success = True
            
            return {
                'status': 'healthy' if table_status == 'ACTIVE' and read_success else 'unhealthy',
                'table_status': table_status,
                'table_name': self.table_name,
                'region': self.config.region,
                'read_capacity': response['Table']['ProvisionedThroughput']['ReadCapacityUnits'],
                'write_capacity': response['Table']['ProvisionedThroughput']['WriteCapacityUnits'],
                'item_count': response['Table']['ItemCount'],
                'table_size_bytes': response['Table']['TableSizeBytes'],
                'indexes': len(response['Table'].get('GlobalSecondaryIndexes', [])),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }


# ============================================
# Integration Functions
# ============================================

async def integrate_with_s3_storage(s3_metadata: Dict[str, Any], 
                                  dynamodb_manager: DynamoDBMetadataManager) -> ArticleMetadataIndex:
    """
    Integrate S3 storage with DynamoDB metadata indexing.
    
    Args:
        s3_metadata: Metadata from S3 storage
        dynamodb_manager: DynamoDB manager instance
        
    Returns:
        ArticleMetadataIndex: Indexed metadata
    """
    # Convert S3 metadata to DynamoDB format
    article_data = {
        'id': s3_metadata.get('article_id'),
        'title': s3_metadata.get('title', ''),
        'source': s3_metadata.get('source', ''),
        'published_date': s3_metadata.get('published_date', ''),
        'url': s3_metadata.get('url', ''),
        's3_key': s3_metadata.get('s3_key', ''),
        'content_hash': s3_metadata.get('content_hash', ''),
        'scraped_date': s3_metadata.get('scraped_date', ''),
        'processing_status': s3_metadata.get('processing_status', 'stored')
    }
    
    return await dynamodb_manager.index_article_metadata(article_data)


async def integrate_with_redshift_etl(redshift_record: Dict[str, Any],
                                    dynamodb_manager: DynamoDBMetadataManager) -> bool:
    """
    Update DynamoDB metadata when article is loaded to Redshift.
    
    Args:
        redshift_record: Article record from Redshift ETL
        dynamodb_manager: DynamoDB manager instance
        
    Returns:
        bool: Success status
    """
    article_id = redshift_record.get('article_id')
    if not article_id:
        return False
    
    updates = {
        'redshift_loaded': True,
        'processing_status': 'processed'
    }
    
    return await dynamodb_manager.update_article_metadata(article_id, updates)


async def sync_metadata_from_scraper(articles: List[Dict[str, Any]], 
                                   dynamodb_manager: DynamoDBMetadataManager) -> Dict[str, Any]:
    """
    Sync article metadata from scraper to DynamoDB.
    
    Args:
        articles: List of scraped articles
        dynamodb_manager: DynamoDB manager instance
        
    Returns:
        Dict with sync results
    """
    return await dynamodb_manager.batch_index_articles(articles)
