"""
Knowledge Graph Query Processing Module

This module provides graph query processing and optimization:
- Complex graph query construction
- Query optimization and execution
- Result formatting and pagination
- Query caching and performance monitoring
"""

import logging
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
from datetime import datetime
import json
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class QueryFilter:
    """Filter criteria for graph queries."""
    property_name: str
    operator: str  # eq, ne, gt, lt, gte, lte, contains, in
    value: Any
    
    
@dataclass
class QuerySort:
    """Sort criteria for query results."""
    property_name: str
    direction: str = "asc"  # asc, desc


@dataclass
class QueryPagination:
    """Pagination parameters for query results."""
    offset: int = 0
    limit: int = 100
    

@dataclass
class QueryParams:
    """Parameters for graph queries."""
    node_labels: Optional[List[str]] = None
    edge_labels: Optional[List[str]] = None
    filters: Optional[List[QueryFilter]] = None
    sort: Optional[List[QuerySort]] = None
    pagination: Optional[QueryPagination] = None
    include_properties: bool = True
    include_edges: bool = False


@dataclass
class QueryResult:
    """Result of a graph query."""
    query_id: str
    execution_time: float
    total_results: int
    returned_results: int
    has_more: bool
    data: List[Dict[str, Any]]
    metadata: Dict[str, Any]


@dataclass
class QueryStatistics:
    """Statistics for query performance."""
    query_count: int = 0
    avg_execution_time: float = 0.0
    cache_hit_rate: float = 0.0
    most_frequent_queries: List[str] = None
    

class GraphQueries:
    """Graph query processing and optimization."""

    def __init__(self, graph_builder=None):
        """Initialize graph queries with graph builder."""
        self.graph = graph_builder
        self.query_cache = {}
        self.cache_timestamps = {}
        self.query_stats = QueryStatistics()
        self.query_history = []
        logger.info("GraphQueries initialized")

    def _generate_query_id(self, query_type: str, params: Dict[str, Any]) -> str:
        """Generate unique query ID for caching."""
        query_data = {
            'type': query_type,
            'params': params,
            'timestamp': datetime.now().isoformat()
        }
        query_string = json.dumps(query_data, sort_keys=True, default=str)
        return hashlib.md5(query_string.encode()).hexdigest()[:16]

    def _generate_cache_key(self, query_type: str, params: Dict[str, Any]) -> str:
        """Generate cache key for query results."""
        cache_data = {
            'type': query_type,
            'params': params
        }
        cache_string = json.dumps(cache_data, sort_keys=True, default=str)
        return f"query_cache:{hashlib.md5(cache_string.encode()).hexdigest()}"

    async def execute_node_query(self, params: QueryParams) -> QueryResult:
        """
        Execute a node query with filters and pagination.
        
        Args:
            params: Query parameters
            
        Returns:
            QueryResult with matching nodes
        """
        start_time = datetime.now()
        query_id = self._generate_query_id("node_query", params.__dict__)
        
        try:
            if not self.graph:
                # Mock implementation for testing
                mock_data = [
                    {
                        'id': f"node_{i}",
                        'label': params.node_labels[0] if params.node_labels else 'MockNode',
                        'properties': {
                            'name': f"Node {i}",
                            'value': i * 10,
                            'category': 'test'
                        }
                    } for i in range(min(20, params.pagination.limit if params.pagination else 10))
                ]
                
                # Apply mock filtering
                if params.filters:
                    filtered_data = []
                    for item in mock_data:
                        match = True
                        for filter_item in params.filters:
                            prop_value = item['properties'].get(filter_item.property_name)
                            if not self._apply_filter(prop_value, filter_item):
                                match = False
                                break
                        if match:
                            filtered_data.append(item)
                    mock_data = filtered_data
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                return QueryResult(
                    query_id=query_id,
                    execution_time=execution_time,
                    total_results=len(mock_data),
                    returned_results=len(mock_data),
                    has_more=False,
                    data=mock_data,
                    metadata={'query_type': 'node_query', 'mock': True}
                )

            g = self.graph.g
            
            # Build query
            query = g.V()
            
            # Apply label filters
            if params.node_labels:
                query = query.hasLabel(*params.node_labels)
            
            # Apply property filters
            if params.filters:
                for filter_item in params.filters:
                    query = self._apply_gremlin_filter(query, filter_item)
            
            # Get total count before pagination
            count_query = query.count()
            total_count = await count_query.next()
            
            # Apply sorting
            if params.sort:
                for sort_item in params.sort:
                    if sort_item.direction == "desc":
                        query = query.order().by(sort_item.property_name, "desc")
                    else:
                        query = query.order().by(sort_item.property_name, "asc")
            
            # Apply pagination
            if params.pagination:
                query = query.skip(params.pagination.offset).limit(params.pagination.limit)
            else:
                query = query.limit(100)  # Default limit
            
            # Get results
            if params.include_properties:
                results = await query.valueMap(True).toList()
            else:
                results = await query.id().toList()
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # Format results
            formatted_results = []
            for result in results:
                if params.include_properties:
                    formatted_results.append(dict(result))
                else:
                    formatted_results.append({'id': result})
            
            # Update statistics
            self._update_query_stats(execution_time)
            
            return QueryResult(
                query_id=query_id,
                execution_time=execution_time,
                total_results=total_count,
                returned_results=len(formatted_results),
                has_more=total_count > len(formatted_results),
                data=formatted_results,
                metadata={'query_type': 'node_query', 'filters_applied': len(params.filters or [])}
            )

        except Exception as e:
            logger.error(f"Node query execution failed: {e}")
            raise

    async def execute_relationship_query(self, params: QueryParams) -> QueryResult:
        """
        Execute a relationship/edge query.
        
        Args:
            params: Query parameters
            
        Returns:
            QueryResult with matching relationships
        """
        start_time = datetime.now()
        query_id = self._generate_query_id("relationship_query", params.__dict__)
        
        try:
            if not self.graph:
                # Mock implementation for testing
                mock_data = [
                    {
                        'id': f"edge_{i}",
                        'label': params.edge_labels[0] if params.edge_labels else 'CONNECTS',
                        'from_node': f"node_{i}",
                        'to_node': f"node_{i+1}",
                        'properties': {
                            'weight': i * 0.1,
                            'created_at': datetime.now().isoformat()
                        }
                    } for i in range(min(15, params.pagination.limit if params.pagination else 10))
                ]
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                return QueryResult(
                    query_id=query_id,
                    execution_time=execution_time,
                    total_results=len(mock_data),
                    returned_results=len(mock_data),
                    has_more=False,
                    data=mock_data,
                    metadata={'query_type': 'relationship_query', 'mock': True}
                )

            g = self.graph.g
            
            # Build edge query
            query = g.E()
            
            # Apply label filters
            if params.edge_labels:
                query = query.hasLabel(*params.edge_labels)
            
            # Apply property filters
            if params.filters:
                for filter_item in params.filters:
                    query = self._apply_gremlin_filter(query, filter_item)
            
            # Get total count
            total_count = await query.count().next()
            
            # Apply sorting
            if params.sort:
                for sort_item in params.sort:
                    if sort_item.direction == "desc":
                        query = query.order().by(sort_item.property_name, "desc")
                    else:
                        query = query.order().by(sort_item.property_name, "asc")
            
            # Apply pagination
            if params.pagination:
                query = query.skip(params.pagination.offset).limit(params.pagination.limit)
            
            # Get results with source and target info
            if params.include_properties:
                results = await query.project('edge', 'from', 'to').by(__.valueMap(True)).by(__.inV().valueMap(True)).by(__.outV().valueMap(True)).toList()
            else:
                results = await query.id().toList()
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # Format results
            formatted_results = []
            for result in results:
                if params.include_properties:
                    formatted_results.append({
                        'edge': dict(result.get('edge', {})),
                        'from_node': dict(result.get('from', {})),
                        'to_node': dict(result.get('to', {}))
                    })
                else:
                    formatted_results.append({'id': result})
            
            self._update_query_stats(execution_time)
            
            return QueryResult(
                query_id=query_id,
                execution_time=execution_time,
                total_results=total_count,
                returned_results=len(formatted_results),
                has_more=total_count > len(formatted_results),
                data=formatted_results,
                metadata={'query_type': 'relationship_query'}
            )

        except Exception as e:
            logger.error(f"Relationship query execution failed: {e}")
            raise

    async def execute_pattern_query(self, pattern: str, params: Dict[str, Any] = None) -> QueryResult:
        """
        Execute a pattern-based query (e.g., Cypher-like patterns).
        
        Args:
            pattern: Query pattern string
            params: Query parameters
            
        Returns:
            QueryResult with matching patterns
        """
        start_time = datetime.now()
        query_id = self._generate_query_id("pattern_query", {'pattern': pattern, 'params': params})
        params = params or {}
        
        try:
            if not self.graph:
                # Mock implementation for testing
                mock_data = [
                    {
                        'pattern': pattern,
                        'match_id': f"match_{i}",
                        'nodes': [f"node_{i}", f"node_{i+1}"],
                        'relationships': [f"rel_{i}"]
                    } for i in range(5)
                ]
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                return QueryResult(
                    query_id=query_id,
                    execution_time=execution_time,
                    total_results=len(mock_data),
                    returned_results=len(mock_data),
                    has_more=False,
                    data=mock_data,
                    metadata={'query_type': 'pattern_query', 'pattern': pattern, 'mock': True}
                )

            # This would implement pattern matching logic
            # For now, return basic traversal results
            g = self.graph.g
            
            # Simple pattern interpretation (would be more complex in reality)
            if "Person" in pattern and "KNOWS" in pattern:
                # Example: (p1:Person)-[:KNOWS]->(p2:Person)
                results = await (g.V().hasLabel('Person')
                               .outE('KNOWS')
                               .inV().hasLabel('Person')
                               .path()
                               .limit(10)
                               .toList())
            else:
                # Generic pattern - return some connected nodes
                results = await (g.V().limit(5).both().path().toList())
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # Format path results
            formatted_results = []
            for i, path in enumerate(results):
                formatted_results.append({
                    'pattern': pattern,
                    'match_id': f"match_{i}",
                    'path': [str(obj) for obj in path.objects] if hasattr(path, 'objects') else [str(path)]
                })
            
            self._update_query_stats(execution_time)
            
            return QueryResult(
                query_id=query_id,
                execution_time=execution_time,
                total_results=len(formatted_results),
                returned_results=len(formatted_results),
                has_more=False,
                data=formatted_results,
                metadata={'query_type': 'pattern_query', 'pattern': pattern}
            )

        except Exception as e:
            logger.error(f"Pattern query execution failed: {e}")
            raise

    async def execute_aggregation_query(self, aggregation_type: str, params: QueryParams) -> QueryResult:
        """
        Execute aggregation queries (count, sum, avg, etc.).
        
        Args:
            aggregation_type: Type of aggregation (count, sum, avg, min, max)
            params: Query parameters
            
        Returns:
            QueryResult with aggregation results
        """
        start_time = datetime.now()
        query_id = self._generate_query_id("aggregation_query", {'type': aggregation_type, 'params': params.__dict__})
        
        try:
            if not self.graph:
                # Mock implementation for testing
                mock_result = {
                    'aggregation_type': aggregation_type,
                    'result': 42 if aggregation_type == 'count' else 123.45,
                    'property': params.filters[0].property_name if params.filters else 'mock_property'
                }
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                return QueryResult(
                    query_id=query_id,
                    execution_time=execution_time,
                    total_results=1,
                    returned_results=1,
                    has_more=False,
                    data=[mock_result],
                    metadata={'query_type': 'aggregation_query', 'aggregation_type': aggregation_type, 'mock': True}
                )

            g = self.graph.g
            
            # Build base query
            if params.node_labels:
                query = g.V().hasLabel(*params.node_labels)
            else:
                query = g.V()
            
            # Apply filters
            if params.filters:
                for filter_item in params.filters:
                    query = self._apply_gremlin_filter(query, filter_item)
            
            # Apply aggregation
            if aggregation_type == 'count':
                result = await query.count().next()
            elif aggregation_type == 'sum' and params.filters:
                prop = params.filters[0].property_name
                result = await query.values(prop).sum().next()
            elif aggregation_type == 'avg' and params.filters:
                prop = params.filters[0].property_name
                result = await query.values(prop).mean().next()
            elif aggregation_type == 'min' and params.filters:
                prop = params.filters[0].property_name
                result = await query.values(prop).min().next()
            elif aggregation_type == 'max' and params.filters:
                prop = params.filters[0].property_name
                result = await query.values(prop).max().next()
            else:
                result = await query.count().next()
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            result_data = {
                'aggregation_type': aggregation_type,
                'result': result,
                'property': params.filters[0].property_name if params.filters else None
            }
            
            self._update_query_stats(execution_time)
            
            return QueryResult(
                query_id=query_id,
                execution_time=execution_time,
                total_results=1,
                returned_results=1,
                has_more=False,
                data=[result_data],
                metadata={'query_type': 'aggregation_query', 'aggregation_type': aggregation_type}
            )

        except Exception as e:
            logger.error(f"Aggregation query execution failed: {e}")
            raise

    def _apply_filter(self, value: Any, filter_item: QueryFilter) -> bool:
        """Apply filter logic for mock data."""
        if filter_item.operator == 'eq':
            return value == filter_item.value
        elif filter_item.operator == 'ne':
            return value != filter_item.value
        elif filter_item.operator == 'gt':
            return value > filter_item.value
        elif filter_item.operator == 'lt':
            return value < filter_item.value
        elif filter_item.operator == 'gte':
            return value >= filter_item.value
        elif filter_item.operator == 'lte':
            return value <= filter_item.value
        elif filter_item.operator == 'contains':
            return filter_item.value in str(value)
        elif filter_item.operator == 'in':
            return value in filter_item.value
        return True

    def _apply_gremlin_filter(self, query, filter_item: QueryFilter):
        """Apply Gremlin filter to query."""
        from gremlin_python.process.traversal import P
        
        prop_name = filter_item.property_name
        value = filter_item.value
        
        if filter_item.operator == 'eq':
            return query.has(prop_name, P.eq(value))
        elif filter_item.operator == 'ne':
            return query.has(prop_name, P.neq(value))
        elif filter_item.operator == 'gt':
            return query.has(prop_name, P.gt(value))
        elif filter_item.operator == 'lt':
            return query.has(prop_name, P.lt(value))
        elif filter_item.operator == 'gte':
            return query.has(prop_name, P.gte(value))
        elif filter_item.operator == 'lte':
            return query.has(prop_name, P.lte(value))
        elif filter_item.operator == 'contains':
            return query.has(prop_name, P.containing(value))
        elif filter_item.operator == 'in':
            return query.has(prop_name, P.within(value))
        
        return query

    def _update_query_stats(self, execution_time: float):
        """Update query execution statistics."""
        self.query_stats.query_count += 1
        
        # Update average execution time
        if self.query_stats.avg_execution_time == 0:
            self.query_stats.avg_execution_time = execution_time
        else:
            self.query_stats.avg_execution_time = (
                (self.query_stats.avg_execution_time * (self.query_stats.query_count - 1) + execution_time) /
                self.query_stats.query_count
            )

    def get_query_statistics(self) -> Dict[str, Any]:
        """Get query execution statistics."""
        return {
            'total_queries': self.query_stats.query_count,
            'average_execution_time': self.query_stats.avg_execution_time,
            'cache_hit_rate': self.query_stats.cache_hit_rate,
            'query_history_size': len(self.query_history),
            'last_updated': datetime.now().isoformat()
        }

    def optimize_query(self, query_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Provide query optimization recommendations.
        
        Args:
            query_type: Type of query to optimize
            params: Query parameters
            
        Returns:
            Dictionary with optimization recommendations
        """
        recommendations = []
        estimated_performance = 'medium'
        
        # Analyze query complexity
        if params.get('filters'):
            if len(params['filters']) > 5:
                recommendations.append("Consider reducing number of filters for better performance")
                estimated_performance = 'slow'
        
        if params.get('pagination'):
            if params['pagination'].get('limit', 0) > 1000:
                recommendations.append("Large result sets may impact performance - consider smaller page sizes")
                estimated_performance = 'slow'
        
        if not params.get('filters') and not params.get('node_labels'):
            recommendations.append("Add filters or node labels to improve query selectivity")
            estimated_performance = 'slow'
        
        # Check for indexes (mock)
        if params.get('sort'):
            recommendations.append("Ensure indexes exist on sorted properties for optimal performance")
        
        if not recommendations:
            recommendations.append("Query is well-optimized")
            estimated_performance = 'fast'
        
        return {
            'query_type': query_type,
            'estimated_performance': estimated_performance,
            'recommendations': recommendations,
            'analysis_time': datetime.now().isoformat()
        }

    async def explain_query_plan(self, query_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Explain query execution plan.
        
        Args:
            query_type: Type of query
            params: Query parameters
            
        Returns:
            Dictionary with query execution plan
        """
        # Mock implementation of query plan explanation
        steps = []
        
        if query_type == 'node_query':
            steps.append("1. Scan all vertices")
            if params.get('node_labels'):
                steps.append(f"2. Filter by labels: {params['node_labels']}")
            if params.get('filters'):
                steps.append(f"3. Apply property filters: {len(params['filters'])} conditions")
            if params.get('sort'):
                steps.append("4. Sort results")
            if params.get('pagination'):
                steps.append("5. Apply pagination")
        
        elif query_type == 'relationship_query':
            steps.append("1. Scan all edges")
            if params.get('edge_labels'):
                steps.append(f"2. Filter by edge labels: {params['edge_labels']}")
            steps.append("3. Get source and target vertices")
        
        return {
            'query_type': query_type,
            'execution_steps': steps,
            'estimated_cost': len(steps) * 10,  # Mock cost
            'index_usage': 'none',  # Mock index info
            'plan_generated_at': datetime.now().isoformat()
        }
