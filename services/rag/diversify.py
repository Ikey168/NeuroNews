"""
RAG Result Diversification Service
Issue #237: Filters & ranking fairness (language/date/source)

This module provides result diversification to avoid single-source dominance
and ensure fair representation across domains and sources.
"""

import logging
import math
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass
from collections import defaultdict, Counter
from enum import Enum

logger = logging.getLogger(__name__)


class DiversificationStrategy(Enum):
    """Diversification strategies available"""
    MMR = "maximal_marginal_relevance"  # Maximal Marginal Relevance
    DOMAIN_CAP = "per_domain_cap"       # Cap results per domain
    SOURCE_CAP = "per_source_cap"       # Cap results per source
    ROUND_ROBIN = "round_robin"         # Round-robin selection
    HYBRID = "hybrid"                   # Combination of strategies


@dataclass
class DiversificationConfig:
    """Configuration for result diversification"""
    strategy: DiversificationStrategy = DiversificationStrategy.HYBRID
    max_per_domain: int = 3             # Maximum results per domain
    max_per_source: int = 2             # Maximum results per source
    lambda_param: float = 0.7           # MMR lambda parameter (relevance vs diversity)
    min_similarity_threshold: float = 0.1  # Minimum similarity for MMR
    ensure_diversity: bool = True        # Force diversity even if it reduces relevance


class RAGDiversificationService:
    """
    Service for diversifying search results to ensure fair representation
    and avoid single-source dominance.
    
    Features:
    - Maximal Marginal Relevance (MMR) for content diversity
    - Per-domain result capping
    - Per-source result capping
    - Round-robin selection across sources
    - Hybrid diversification strategies
    """
    
    def __init__(self, config: Optional[DiversificationConfig] = None):
        self.config = config or DiversificationConfig()
        self.logger = logger
        
    def diversify_results(self, documents: List[Dict[str, Any]], 
                         target_count: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Diversify search results according to the configured strategy.
        
        Args:
            documents: List of document dictionaries with relevance scores
            target_count: Target number of results (None = no limit)
            
        Returns:
            List of diversified documents
        """
        if not documents:
            return documents
            
        target_count = target_count or len(documents)
        original_count = len(documents)
        
        self.logger.info(f"Diversifying {original_count} documents to {target_count} "
                        f"using strategy: {self.config.strategy.value}")
        
        if self.config.strategy == DiversificationStrategy.MMR:
            result = self._apply_mmr(documents, target_count)
        elif self.config.strategy == DiversificationStrategy.DOMAIN_CAP:
            result = self._apply_domain_cap(documents, target_count)
        elif self.config.strategy == DiversificationStrategy.SOURCE_CAP:
            result = self._apply_source_cap(documents, target_count)
        elif self.config.strategy == DiversificationStrategy.ROUND_ROBIN:
            result = self._apply_round_robin(documents, target_count)
        elif self.config.strategy == DiversificationStrategy.HYBRID:
            result = self._apply_hybrid(documents, target_count)
        else:
            result = documents[:target_count]
        
        self.logger.info(f"Diversification complete: {len(result)} documents selected")
        return result
    
    def _apply_mmr(self, documents: List[Dict[str, Any]], 
                   target_count: int) -> List[Dict[str, Any]]:
        """Apply Maximal Marginal Relevance diversification"""
        if len(documents) <= target_count:
            return documents
            
        # Sort by relevance score initially
        sorted_docs = sorted(documents, 
                           key=lambda x: x.get('score', 0), 
                           reverse=True)
        
        selected = []
        remaining = sorted_docs.copy()
        
        # Select the most relevant document first
        if remaining:
            selected.append(remaining.pop(0))
        
        # Select remaining documents using MMR
        while len(selected) < target_count and remaining:
            best_doc = None
            best_score = -float('inf')
            best_idx = -1
            
            for i, doc in enumerate(remaining):
                # Calculate MMR score
                relevance = doc.get('score', 0)
                
                # Calculate maximum similarity to already selected documents
                max_similarity = 0
                for selected_doc in selected:
                    similarity = self._calculate_similarity(doc, selected_doc)
                    max_similarity = max(max_similarity, similarity)
                
                # MMR formula: λ * relevance - (1-λ) * max_similarity
                mmr_score = (self.config.lambda_param * relevance - 
                           (1 - self.config.lambda_param) * max_similarity)
                
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_doc = doc
                    best_idx = i
            
            if best_doc and best_idx >= 0:
                selected.append(best_doc)
                remaining.pop(best_idx)
            else:
                break
        
        return selected
    
    def _apply_domain_cap(self, documents: List[Dict[str, Any]], 
                         target_count: int) -> List[Dict[str, Any]]:
        """Apply per-domain result capping"""
        domain_counts = defaultdict(int)
        selected = []
        
        # Sort by relevance first
        sorted_docs = sorted(documents, 
                           key=lambda x: x.get('score', 0), 
                           reverse=True)
        
        for doc in sorted_docs:
            if len(selected) >= target_count:
                break
                
            domain = self._extract_domain(doc)
            if domain is None:
                domain = "unknown"
            
            if domain_counts[domain] < self.config.max_per_domain:
                selected.append(doc)
                domain_counts[domain] += 1
        
        return selected
    
    def _apply_source_cap(self, documents: List[Dict[str, Any]], 
                         target_count: int) -> List[Dict[str, Any]]:
        """Apply per-source result capping"""
        source_counts = defaultdict(int)
        selected = []
        
        # Sort by relevance first
        sorted_docs = sorted(documents, 
                           key=lambda x: x.get('score', 0), 
                           reverse=True)
        
        for doc in sorted_docs:
            if len(selected) >= target_count:
                break
                
            source = self._extract_source(doc)
            if source is None:
                source = "unknown"
            
            if source_counts[source] < self.config.max_per_source:
                selected.append(doc)
                source_counts[source] += 1
        
        return selected
    
    def _apply_round_robin(self, documents: List[Dict[str, Any]], 
                          target_count: int) -> List[Dict[str, Any]]:
        """Apply round-robin selection across sources"""
        # Group documents by source
        source_groups = defaultdict(list)
        
        for doc in documents:
            source = self._extract_source(doc) or "unknown"
            source_groups[source].append(doc)
        
        # Sort each group by relevance
        for source in source_groups:
            source_groups[source].sort(key=lambda x: x.get('score', 0), reverse=True)
        
        # Round-robin selection
        selected = []
        source_indices = {source: 0 for source in source_groups}
        
        while len(selected) < target_count:
            added_any = False
            
            for source in sorted(source_groups.keys()):
                if len(selected) >= target_count:
                    break
                    
                idx = source_indices[source]
                if idx < len(source_groups[source]):
                    selected.append(source_groups[source][idx])
                    source_indices[source] += 1
                    added_any = True
            
            if not added_any:
                break
        
        return selected
    
    def _apply_hybrid(self, documents: List[Dict[str, Any]], 
                     target_count: int) -> List[Dict[str, Any]]:
        """Apply hybrid diversification strategy"""
        # First apply domain capping to ensure no domain dominance
        domain_capped = self._apply_domain_cap(documents, target_count * 2)
        
        # Then apply source capping
        source_capped = self._apply_source_cap(domain_capped, target_count * 2)
        
        # Finally apply MMR for content diversity
        final_result = self._apply_mmr(source_capped, target_count)
        
        return final_result
    
    def _calculate_similarity(self, doc1: Dict[str, Any], 
                            doc2: Dict[str, Any]) -> float:
        """Calculate similarity between two documents"""
        # Simple text-based similarity using common words
        text1 = self._extract_text(doc1).lower()
        text2 = self._extract_text(doc2).lower()
        
        if not text1 or not text2:
            return 0.0
        
        # Simple word overlap similarity
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        if not union:
            return 0.0
        
        return len(intersection) / len(union)
    
    def _extract_text(self, doc: Dict[str, Any]) -> str:
        """Extract text content from document for similarity calculation"""
        # Try multiple possible text fields in order of preference
        for field in ['content', 'text', 'body', 'description']:
            if field in doc and doc[field]:
                return str(doc[field])
        
        # Fallback to concatenating multiple fields
        text_parts = []
        if 'title' in doc and doc['title']:
            text_parts.append(str(doc['title']))
        if 'summary' in doc and doc['summary']:
            text_parts.append(str(doc['summary']))
        if 'description' in doc and doc['description']:
            text_parts.append(str(doc['description']))
        
        return " ".join(text_parts)
    
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
    
    def _extract_source(self, doc: Dict[str, Any]) -> Optional[str]:
        """Extract source from document"""
        for field in ['source', 'source_name', 'origin', 'publisher']:
            if field in doc and doc[field]:
                return str(doc[field])
        
        metadata = doc.get('metadata', {})
        if isinstance(metadata, dict):
            for field in ['source', 'source_name', 'publisher']:
                if field in metadata and metadata[field]:
                    return str(metadata[field])
        
        return None
    
    def get_diversity_stats(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get diversity statistics for a set of documents"""
        if not documents:
            return {}
        
        domain_counts = Counter()
        source_counts = Counter()
        
        for doc in documents:
            domain = self._extract_domain(doc) or "unknown"
            source = self._extract_source(doc) or "unknown"
            
            domain_counts[domain] += 1
            source_counts[source] += 1
        
        return {
            "total_documents": len(documents),
            "unique_domains": len(domain_counts),
            "unique_sources": len(source_counts),
            "domain_distribution": dict(domain_counts),
            "source_distribution": dict(source_counts),
            "max_per_domain": max(domain_counts.values()) if domain_counts else 0,
            "max_per_source": max(source_counts.values()) if source_counts else 0,
            "domain_diversity_ratio": len(domain_counts) / len(documents) if documents else 0,
            "source_diversity_ratio": len(source_counts) / len(documents) if documents else 0
        }


def create_diversification_service(config: Optional[DiversificationConfig] = None) -> RAGDiversificationService:
    """Factory function to create a diversification service instance"""
    return RAGDiversificationService(config)
