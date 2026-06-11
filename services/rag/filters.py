"""
RAG Filters Service
Issue #237: Filters & ranking fairness (language/date/source)

This module provides structured filtering capabilities for search results
to enforce language, date, source, and publisher constraints.
"""

import logging
from datetime import datetime, date
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class FilterType(Enum):
    """Types of filters available"""
    LANGUAGE = "language"
    DATE_RANGE = "date_range"
    SOURCE = "source"
    PUBLISHER = "publisher"
    DOMAIN = "domain"


@dataclass
class FilterCriteria:
    """Structured filter criteria for search results"""
    languages: Optional[Set[str]] = None  # ISO language codes like 'en', 'de', 'fr'
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    sources: Optional[Set[str]] = None  # Source names
    publishers: Optional[Set[str]] = None  # Publisher names
    domains: Optional[Set[str]] = None  # Domain names
    exclude_sources: Optional[Set[str]] = None
    exclude_publishers: Optional[Set[str]] = None
    exclude_domains: Optional[Set[str]] = None


class RAGFiltersService:
    """
    Service for applying structured filters to search results.
    
    Features:
    - Language filtering (ISO codes)
    - Date range filtering
    - Source/publisher filtering
    - Domain-based filtering
    - Exclusion filters
    """
    
    def __init__(self):
        self.logger = logger
        
    def parse_filter_params(self, **kwargs) -> FilterCriteria:
        """
        Parse filter parameters from various input formats.
        
        Args:
            **kwargs: Filter parameters including:
                - lang/language: str or list of language codes
                - date_from/start_date: str or date
                - date_to/end_date: str or date
                - source/sources: str or list of sources
                - publisher/publishers: str or list of publishers
                - domain/domains: str or list of domains
                - exclude_*: exclusion filters
        
        Returns:
            FilterCriteria: Parsed and validated filter criteria
        """
        criteria = FilterCriteria()
        
        # Language filtering
        lang_input = kwargs.get('lang') or kwargs.get('language')
        if lang_input:
            if isinstance(lang_input, str):
                criteria.languages = {lang_input.lower()}
            elif isinstance(lang_input, (list, tuple, set)):
                criteria.languages = {lang.lower() for lang in lang_input}
        
        # Date filtering
        date_from = kwargs.get('date_from') or kwargs.get('start_date')
        if date_from:
            criteria.date_from = self._parse_date(date_from)
            
        date_to = kwargs.get('date_to') or kwargs.get('end_date')
        if date_to:
            criteria.date_to = self._parse_date(date_to)
        
        # Source filtering
        sources = kwargs.get('source') or kwargs.get('sources')
        if sources:
            criteria.sources = self._parse_string_set(sources)
            
        # Publisher filtering
        publishers = kwargs.get('publisher') or kwargs.get('publishers')
        if publishers:
            criteria.publishers = self._parse_string_set(publishers)
            
        # Domain filtering
        domains = kwargs.get('domain') or kwargs.get('domains')
        if domains:
            criteria.domains = self._parse_string_set(domains)
        
        # Exclusion filters
        exclude_sources = kwargs.get('exclude_sources')
        if exclude_sources:
            criteria.exclude_sources = self._parse_string_set(exclude_sources)
            
        exclude_publishers = kwargs.get('exclude_publishers')
        if exclude_publishers:
            criteria.exclude_publishers = self._parse_string_set(exclude_publishers)
            
        exclude_domains = kwargs.get('exclude_domains')
        if exclude_domains:
            criteria.exclude_domains = self._parse_string_set(exclude_domains)
        
        return criteria
    
    def apply_filters(self, documents: List[Dict[str, Any]], 
                     criteria: FilterCriteria) -> List[Dict[str, Any]]:
        """
        Apply filter criteria to a list of documents.
        
        Args:
            documents: List of document dictionaries
            criteria: FilterCriteria to apply
            
        Returns:
            List of filtered documents
        """
        if not documents:
            return documents
            
        filtered_docs = []
        
        for doc in documents:
            if self._document_matches_criteria(doc, criteria):
                filtered_docs.append(doc)
        
        self.logger.info(f"Filtered {len(documents)} documents to {len(filtered_docs)} "
                        f"using criteria: {self._criteria_summary(criteria)}")
        
        return filtered_docs
    
    def _document_matches_criteria(self, doc: Dict[str, Any], 
                                  criteria: FilterCriteria) -> bool:
        """Check if a document matches the filter criteria"""
        
        # Language filtering
        if criteria.languages:
            doc_lang = self._extract_language(doc)
            if doc_lang and doc_lang.lower() not in criteria.languages:
                return False
        
        # Date filtering
        if criteria.date_from or criteria.date_to:
            doc_date = self._extract_date(doc)
            if doc_date:
                if criteria.date_from and doc_date < criteria.date_from:
                    return False
                if criteria.date_to and doc_date > criteria.date_to:
                    return False
        
        # Source filtering
        if criteria.sources:
            doc_source = self._extract_source(doc)
            if not doc_source or doc_source not in criteria.sources:
                return False
        
        # Publisher filtering
        if criteria.publishers:
            doc_publisher = self._extract_publisher(doc)
            if not doc_publisher or doc_publisher not in criteria.publishers:
                return False
                
        # Domain filtering
        if criteria.domains:
            doc_domain = self._extract_domain(doc)
            if not doc_domain or doc_domain not in criteria.domains:
                return False
        
        # Exclusion filters
        if criteria.exclude_sources:
            doc_source = self._extract_source(doc)
            if doc_source and doc_source in criteria.exclude_sources:
                return False
                
        if criteria.exclude_publishers:
            doc_publisher = self._extract_publisher(doc)
            if doc_publisher and doc_publisher in criteria.exclude_publishers:
                return False
                
        if criteria.exclude_domains:
            doc_domain = self._extract_domain(doc)
            if doc_domain and doc_domain in criteria.exclude_domains:
                return False
        
        return True
    
    def _extract_language(self, doc: Dict[str, Any]) -> Optional[str]:
        """Extract language from document"""
        # Try multiple possible field names
        for field in ['language', 'lang', 'detected_language', 'content_language']:
            if field in doc and doc[field]:
                return str(doc[field]).lower()
        
        # Try to extract from metadata
        metadata = doc.get('metadata', {})
        if isinstance(metadata, dict):
            for field in ['language', 'lang']:
                if field in metadata and metadata[field]:
                    return str(metadata[field]).lower()
        
        return None
    
    def _extract_date(self, doc: Dict[str, Any]) -> Optional[date]:
        """Extract date from document"""
        # Try multiple possible field names
        for field in ['date', 'published_date', 'created_date', 'timestamp']:
            if field in doc and doc[field]:
                return self._parse_date(doc[field])
        
        # Try metadata
        metadata = doc.get('metadata', {})
        if isinstance(metadata, dict):
            for field in ['date', 'published_date', 'created_date']:
                if field in metadata and metadata[field]:
                    return self._parse_date(metadata[field])
        
        return None
    
    def _extract_source(self, doc: Dict[str, Any]) -> Optional[str]:
        """Extract source from document"""
        for field in ['source', 'source_name', 'origin']:
            if field in doc and doc[field]:
                return str(doc[field])
        
        metadata = doc.get('metadata', {})
        if isinstance(metadata, dict):
            for field in ['source', 'source_name']:
                if field in metadata and metadata[field]:
                    return str(metadata[field])
        
        return None
    
    def _extract_publisher(self, doc: Dict[str, Any]) -> Optional[str]:
        """Extract publisher from document"""
        for field in ['publisher', 'publisher_name', 'site_name']:
            if field in doc and doc[field]:
                return str(doc[field])
        
        metadata = doc.get('metadata', {})
        if isinstance(metadata, dict):
            for field in ['publisher', 'publisher_name', 'site_name']:
                if field in metadata and metadata[field]:
                    return str(metadata[field])
        
        return None
    
    def _extract_domain(self, doc: Dict[str, Any]) -> Optional[str]:
        """Extract domain from document"""
        # Try direct domain field
        for field in ['domain', 'site_domain', 'host']:
            if field in doc and doc[field]:
                return str(doc[field])
        
        # Try to extract from URL
        url = doc.get('url') or doc.get('link')
        if url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(str(url))
                return parsed.netloc.lower()
            except Exception:
                pass
        
        # Try metadata
        metadata = doc.get('metadata', {})
        if isinstance(metadata, dict):
            for field in ['domain', 'site_domain']:
                if field in metadata and metadata[field]:
                    return str(metadata[field])
        
        return None
    
    def _parse_date(self, date_input: Any) -> Optional[date]:
        """Parse date from various input formats"""
        if date_input is None:
            return None
            
        if isinstance(date_input, date):
            return date_input
        
        if isinstance(date_input, datetime):
            return date_input.date()
        
        if isinstance(date_input, str):
            # Try common date formats
            for fmt in [
                '%Y-%m-%d',
                '%Y/%m/%d',
                '%d-%m-%Y',
                '%d/%m/%Y',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M:%SZ'
            ]:
                try:
                    return datetime.strptime(date_input, fmt).date()
                except ValueError:
                    continue
        
        return None
    
    def _parse_string_set(self, input_value: Any) -> Set[str]:
        """Parse string or list input into a set of strings"""
        if isinstance(input_value, str):
            return {input_value}
        elif isinstance(input_value, (list, tuple, set)):
            return {str(item) for item in input_value if item}
        else:
            return {str(input_value)} if input_value else set()
    
    def _criteria_summary(self, criteria: FilterCriteria) -> str:
        """Generate a summary string of filter criteria"""
        parts = []
        
        if criteria.languages:
            parts.append(f"lang={list(criteria.languages)}")
        if criteria.date_from:
            parts.append(f"from={criteria.date_from}")
        if criteria.date_to:
            parts.append(f"to={criteria.date_to}")
        if criteria.sources:
            parts.append(f"sources={len(criteria.sources)}")
        if criteria.publishers:
            parts.append(f"publishers={len(criteria.publishers)}")
        if criteria.domains:
            parts.append(f"domains={len(criteria.domains)}")
        
        return ", ".join(parts) if parts else "no filters"


def create_filters_service() -> RAGFiltersService:
    """Factory function to create a filters service instance"""
    return RAGFiltersService()
