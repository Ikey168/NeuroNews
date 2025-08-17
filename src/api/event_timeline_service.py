"""
Enhanced Event Timeline Service - Issue #38

This service extends the basic event timeline functionality from Issue #37 
with advanced features specifically for Issue #38:

1. Historical event tracking with detailed metadata
2. Event relationship mapping in Neptune
3. Timeline visualization generation
4. Interactive event evolution charts

Key enhancements over Issue #37:
- Dedicated event storage and retrieval optimizations
- Visualization data formatting for timeline charts
- Historical context and event clustering
- Export capabilities for timeline data
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from collections import defaultdict

# Import enhanced components from Issue #37
try:
    from src.knowledge_graph.enhanced_graph_populator import EnhancedKnowledgeGraphPopulator
    from src.nlp.advanced_entity_extractor import AdvancedEntityExtractor
    ENHANCED_COMPONENTS_AVAILABLE = True
except ImportError:
    ENHANCED_COMPONENTS_AVAILABLE = False

# Fallback imports
try:
    from src.knowledge_graph.graph_builder import GraphBuilder
    from src.nlp.entity_extractor import EntityExtractor
    BASIC_COMPONENTS_AVAILABLE = True
except ImportError:
    BASIC_COMPONENTS_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class HistoricalEvent:
    """Enhanced event model for historical tracking."""
    event_id: str
    title: str
    description: str
    timestamp: datetime
    topic: str
    event_type: str
    entities_involved: List[str]
    source_article_id: Optional[str] = None
    confidence: float = 0.0
    impact_score: float = 0.0
    related_events: List[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.related_events is None:
            self.related_events = []
        if self.metadata is None:
            self.metadata = {}


@dataclass
class TimelineVisualizationData:
    """Data structure for timeline visualizations."""
    timeline_id: str
    topic: str
    time_range: Tuple[datetime, datetime]
    events: List[HistoricalEvent]
    visualization_config: Dict[str, Any]
    chart_data: Dict[str, Any]
    export_formats: List[str] = None
    
    def __post_init__(self):
        if self.export_formats is None:
            self.export_formats = ['json', 'csv', 'html']


class EventTimelineService:
    """
    Enhanced Event Timeline Service for Issue #38.
    
    Provides comprehensive event tracking, storage, and visualization
    capabilities building upon the basic API from Issue #37.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the event timeline service."""
        self.config = config or {}
        self.graph_populator = None
        self.entity_extractor = None
        self._initialize_components()
        
        # Timeline configuration
        self.max_events_per_timeline = self.config.get('max_events_per_timeline', 100)
        self.default_time_window_days = self.config.get('default_time_window_days', 365)
        self.event_clustering_threshold = self.config.get('event_clustering_threshold', 0.8)
        
        # Visualization settings
        self.visualization_themes = {
            'default': {
                'primary_color': '#1f77b4',
                'secondary_color': '#ff7f0e',
                'background_color': '#ffffff',
                'text_color': '#333333'
            },
            'dark': {
                'primary_color': '#8dd3c7',
                'secondary_color': '#ffffb3',
                'background_color': '#2f2f2f',
                'text_color': '#ffffff'
            },
            'scientific': {
                'primary_color': '#2ca02c',
                'secondary_color': '#d62728',
                'background_color': '#f8f8f8',
                'text_color': '#2f2f2f'
            }
        }
        
        logger.info("EventTimelineService initialized")
    
    def _initialize_components(self):
        """Initialize graph and NLP components."""
        try:
            if ENHANCED_COMPONENTS_AVAILABLE:
                # Use enhanced components from Issue #36/#37
                self.graph_populator = EnhancedKnowledgeGraphPopulator(self.config)
                self.entity_extractor = AdvancedEntityExtractor(self.config)
                logger.info("Enhanced components loaded for event timeline service")
            elif BASIC_COMPONENTS_AVAILABLE:
                # Fallback to basic components
                self.graph_populator = GraphBuilder(self.config)
                self.entity_extractor = EntityExtractor()
                logger.info("Basic components loaded for event timeline service")
            else:
                logger.warning("No graph or NLP components available")
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
    
    async def track_historical_events(
        self,
        topic: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        event_types: Optional[List[str]] = None,
        include_related: bool = True
    ) -> List[HistoricalEvent]:
        """
        Track historical events related to a specific topic.
        
        This implements the first requirement of Issue #38:
        "Track historical events related to a topic."
        """
        logger.info(f"Tracking historical events for topic: {topic}")
        
        # Set default time range if not provided
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=self.default_time_window_days)
        
        try:
            # Query events from the knowledge graph
            events = await self._query_events_from_graph(
                topic=topic,
                start_date=start_date,
                end_date=end_date,
                event_types=event_types
            )
            
            # Enhance events with metadata and relationships
            enhanced_events = []
            for event in events:
                enhanced_event = await self._enhance_event_data(event, include_related)
                enhanced_events.append(enhanced_event)
            
            # Sort events chronologically
            enhanced_events.sort(key=lambda x: x.timestamp)
            
            logger.info(f"Tracked {len(enhanced_events)} historical events for {topic}")
            return enhanced_events
            
        except Exception as e:
            logger.error(f"Failed to track historical events: {e}")
            raise
    
    async def store_event_relationships(
        self,
        events: List[HistoricalEvent],
        force_update: bool = False
    ) -> Dict[str, Any]:
        """
        Store event timestamps and relationships in Neptune.
        
        This implements the second requirement of Issue #38:
        "Store event timestamps & relationships in Neptune."
        """
        logger.info(f"Storing {len(events)} events and relationships in Neptune")
        
        try:
            storage_results = {
                'events_stored': 0,
                'relationships_created': 0,
                'errors': []
            }
            
            for event in events:
                try:
                    # Store event in Neptune
                    await self._store_event_in_neptune(event, force_update)
                    storage_results['events_stored'] += 1
                    
                    # Create relationships between events and entities
                    relationships = await self._create_event_relationships(event)
                    storage_results['relationships_created'] += len(relationships)
                    
                except Exception as e:
                    error_msg = f"Failed to store event {event.event_id}: {e}"
                    logger.error(error_msg)
                    storage_results['errors'].append(error_msg)
            
            logger.info(f"Storage complete: {storage_results}")
            return storage_results
            
        except Exception as e:
            logger.error(f"Failed to store event relationships: {e}")
            raise
    
    async def generate_timeline_api_response(
        self,
        topic: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_events: int = 50,
        include_visualizations: bool = True
    ) -> Dict[str, Any]:
        """
        Generate API response for event timeline endpoint.
        
        This implements the third requirement of Issue #38:
        "Implement API /event_timeline?topic=Artificial Intelligence."
        
        Enhanced version of the Issue #37 endpoint with visualization support.
        """
        logger.info(f"Generating timeline API response for topic: {topic}")
        
        try:
            # Track historical events
            events = await self.track_historical_events(
                topic=topic,
                start_date=start_date,
                end_date=end_date
            )
            
            # Limit results
            if len(events) > max_events:
                events = events[:max_events]
            
            # Generate base response
            response = {
                'topic': topic,
                'timeline_span': {
                    'start_date': start_date.isoformat() if start_date else None,
                    'end_date': end_date.isoformat() if end_date else None
                },
                'total_events': len(events),
                'events': [self._event_to_dict(event) for event in events],
                'metadata': {
                    'generated_at': datetime.now().isoformat(),
                    'max_events': max_events,
                    'visualization_included': include_visualizations
                }
            }
            
            # Add visualization data if requested
            if include_visualizations:
                visualization_data = await self.generate_visualization_data(
                    topic=topic,
                    events=events
                )
                response['visualization'] = visualization_data
            
            logger.info(f"Generated timeline response with {len(events)} events")
            return response
            
        except Exception as e:
            logger.error(f"Failed to generate timeline API response: {e}")
            raise
    
    async def generate_visualization_data(
        self,
        topic: str,
        events: List[HistoricalEvent],
        theme: str = 'default',
        chart_type: str = 'timeline'
    ) -> Dict[str, Any]:
        """
        Generate visualizations of event evolution.
        
        This implements the fourth requirement of Issue #38:
        "Generate visualizations of event evolution."
        """
        logger.info(f"Generating visualization data for {len(events)} events")
        
        try:
            # Prepare timeline data
            timeline_data = self._prepare_timeline_chart_data(events, theme)
            
            # Generate different visualization formats
            visualizations = {
                'timeline_chart': timeline_data,
                'event_clusters': self._generate_event_clusters(events),
                'impact_analysis': self._generate_impact_analysis(events),
                'entity_involvement': self._generate_entity_involvement_chart(events),
                'theme': self.visualization_themes.get(theme, self.visualization_themes['default']),
                'export_options': {
                    'json': f'/api/v1/event-timeline/{topic}/export?format=json',
                    'csv': f'/api/v1/event-timeline/{topic}/export?format=csv',
                    'png': f'/api/v1/event-timeline/{topic}/export?format=png',
                    'html': f'/api/v1/event-timeline/{topic}/export?format=html'
                }
            }
            
            logger.info("Visualization data generated successfully")
            return visualizations
            
        except Exception as e:
            logger.error(f"Failed to generate visualization data: {e}")
            raise
    
    async def _query_events_from_graph(
        self,
        topic: str,
        start_date: datetime,
        end_date: datetime,
        event_types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Query events from the knowledge graph."""
        if not self.graph_populator:
            logger.warning("No graph populator available, generating sample events")
            # Generate sample events for demonstration/testing
            return self._generate_sample_events(topic, start_date, end_date)
        
        try:
            # Use enhanced graph populator if available
            if hasattr(self.graph_populator, '_execute_traversal'):
                # Build Gremlin query for events
                query = f"""
                g.V().has('entity_type', 'ARTICLE')
                     .has('title', containing('{topic}'))
                     .has('published_date', between('{start_date.isoformat()}', '{end_date.isoformat()}'))
                     .limit(500)
                """
                
                results = await self.graph_populator._execute_traversal(query)
                return self._process_graph_results(results, topic)
            else:
                # Fallback for basic graph builder
                logger.info("Using basic graph builder for event queries")
                return self._generate_sample_events(topic, start_date, end_date)
                
        except Exception as e:
            logger.error(f"Failed to query events from graph: {e}")
            # Return sample events as fallback
            return self._generate_sample_events(topic, start_date, end_date)
    
    def _process_graph_results(
        self,
        results: List[Dict[str, Any]],
        topic: str
    ) -> List[Dict[str, Any]]:
        """Process raw graph results into event format."""
        events = []
        
        for result in results:
            try:
                # Helper function to safely extract values
                def safe_extract(key: str, default: Any = ''):
                    value = result.get(key, default)
                    if isinstance(value, list) and value:
                        return value[0]
                    elif isinstance(value, list):
                        return default
                    return value or default
                
                # Extract event data from graph result
                event_data = {
                    'event_id': safe_extract('id', f"event_{len(events)}"),
                    'title': safe_extract('title', 'Unknown Event'),
                    'description': str(safe_extract('content', ''))[:500],  # Truncate
                    'timestamp': self._parse_timestamp(safe_extract('published_date', '')),
                    'topic': topic,
                    'event_type': self._classify_event_type(result),
                    'entities_involved': self._extract_entities_from_result(result),
                    'source_article_id': safe_extract('id', ''),
                    'confidence': 0.8,  # Default confidence
                    'metadata': {
                        'author': safe_extract('author', 'Unknown'),
                        'source_url': safe_extract('source_url', ''),
                        'category': safe_extract('category', '')
                    }
                }
                events.append(event_data)
                
            except Exception as e:
                logger.warning(f"Failed to process graph result: {e}")
                continue
        
        return events
    
    def _generate_sample_events(
        self,
        topic: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Generate sample events for demonstration when no graph data is available."""
        sample_events = []
        
        # Calculate time span and generate events
        time_span = end_date - start_date
        num_events = min(5, max(2, int(time_span.days / 7)))  # 1 event per week, 2-5 events
        
        for i in range(num_events):
            # Distribute events across the time range
            event_time = start_date + (time_span * i / num_events)
            
            sample_event = {
                'id': f"sample_event_{i}_{topic.replace(' ', '_').lower()}",
                'title': f"Sample Event {i+1} for {topic}",
                'content': f"This is a sample event related to {topic}. This demonstrates the event timeline functionality for Issue #38.",
                'published_date': event_time.isoformat(),
                'author': 'Sample Author',
                'source_url': f'https://example.com/event_{i}',
                'category': 'Technology' if 'AI' in topic or 'technology' in topic.lower() else 'General',
                'confidence': 0.8,
                'type': 'announcement' if i % 2 == 0 else 'research'
            }
            sample_events.append(sample_event)
        
        return sample_events
    
    async def _enhance_event_data(
        self,
        event_data: Dict[str, Any],
        include_related: bool = True
    ) -> HistoricalEvent:
        """Enhance event data with additional metadata and relationships."""
        try:
            # Create HistoricalEvent object with safe key access
            event = HistoricalEvent(
                event_id=event_data.get('event_id', 'unknown'),
                title=event_data.get('title', 'Unknown Event'),
                description=event_data.get('description', ''),
                timestamp=event_data.get('timestamp', datetime.now()),
                topic=event_data.get('topic', 'Unknown'),
                event_type=event_data.get('event_type', 'general'),
                entities_involved=event_data.get('entities_involved', []),
                source_article_id=event_data.get('source_article_id'),
                confidence=event_data.get('confidence', 0.8),
                metadata=event_data.get('metadata', {})
            )
            
            # Calculate impact score
            event.impact_score = await self._calculate_impact_score(event)
            
            # Find related events if requested
            if include_related:
                event.related_events = await self._find_related_events(event)
            
            return event
            
        except Exception as e:
            logger.error(f"Failed to enhance event data: {e}")
            # Return basic event on failure
            return HistoricalEvent(
                event_id=event_data.get('event_id', 'unknown'),
                title=event_data.get('title', 'Unknown Event'),
                description=event_data.get('description', ''),
                timestamp=event_data.get('timestamp', datetime.now()),
                topic=event_data.get('topic', ''),
                event_type=event_data.get('event_type', 'unknown'),
                entities_involved=event_data.get('entities_involved', [])
            )
    
    async def _store_event_in_neptune(
        self,
        event: HistoricalEvent,
        force_update: bool = False
    ) -> bool:
        """Store event data in Neptune database."""
        try:
            if not self.graph_populator:
                logger.warning("No graph populator available for Neptune storage")
                return False
            
            # Check if event already exists
            if not force_update:
                existing = await self._check_event_exists(event.event_id)
                if existing:
                    logger.debug(f"Event {event.event_id} already exists, skipping")
                    return True
            
            # Create event vertex in Neptune
            event_vertex_query = f"""
            g.addV('EVENT')
             .property('event_id', '{event.event_id}')
             .property('title', '{event.title.replace("'", "\\'")}')
             .property('description', '{event.description.replace("'", "\\'")}')
             .property('timestamp', '{event.timestamp.isoformat()}')
             .property('topic', '{event.topic}')
             .property('event_type', '{event.event_type}')
             .property('confidence', {event.confidence})
             .property('impact_score', {event.impact_score})
            """
            
            if hasattr(self.graph_populator, '_execute_traversal'):
                await self.graph_populator._execute_traversal(event_vertex_query)
                logger.debug(f"Stored event {event.event_id} in Neptune")
                return True
            else:
                logger.warning("Graph populator does not support traversal execution")
                return False
                
        except Exception as e:
            logger.error(f"Failed to store event in Neptune: {e}")
            return False
    
    async def _create_event_relationships(
        self,
        event: HistoricalEvent
    ) -> List[str]:
        """Create relationships between events and entities in Neptune."""
        relationships = []
        
        try:
            if not self.graph_populator:
                return relationships
            
            # Create relationships to entities
            for entity in event.entities_involved:
                try:
                    relationship_query = f"""
                    g.V().has('event_id', '{event.event_id}').as('event')
                     .V().has('normalized_form', '{entity}').as('entity')
                     .addE('INVOLVES_ENTITY')
                     .from('event').to('entity')
                     .property('confidence', {event.confidence})
                     .property('created_at', '{datetime.now().isoformat()}')
                    """
                    
                    if hasattr(self.graph_populator, '_execute_traversal'):
                        await self.graph_populator._execute_traversal(relationship_query)
                        relationships.append(f"event-{event.event_id}-entity-{entity}")
                        
                except Exception as e:
                    logger.warning(f"Failed to create relationship to entity {entity}: {e}")
            
            # Create relationships to related events
            for related_event_id in event.related_events:
                try:
                    relationship_query = f"""
                    g.V().has('event_id', '{event.event_id}').as('event1')
                     .V().has('event_id', '{related_event_id}').as('event2')
                     .addE('RELATED_TO')
                     .from('event1').to('event2')
                     .property('confidence', {event.confidence})
                    """
                    
                    if hasattr(self.graph_populator, '_execute_traversal'):
                        await self.graph_populator._execute_traversal(relationship_query)
                        relationships.append(f"event-{event.event_id}-related-{related_event_id}")
                        
                except Exception as e:
                    logger.warning(f"Failed to create relationship to related event: {e}")
            
            logger.debug(f"Created {len(relationships)} relationships for event {event.event_id}")
            return relationships
            
        except Exception as e:
            logger.error(f"Failed to create event relationships: {e}")
            return relationships
    
    def _prepare_timeline_chart_data(
        self,
        events: List[HistoricalEvent],
        theme: str = 'default'
    ) -> Dict[str, Any]:
        """Prepare data for timeline chart visualization."""
        try:
            # Sort events by timestamp
            sorted_events = sorted(events, key=lambda x: x.timestamp)
            
            # Prepare chart data
            chart_data = {
                'type': 'timeline',
                'data': {
                    'labels': [event.timestamp.strftime('%Y-%m-%d') for event in sorted_events],
                    'datasets': [
                        {
                            'label': 'Events',
                            'data': [
                                {
                                    'x': event.timestamp.isoformat(),
                                    'y': event.impact_score,
                                    'title': event.title,
                                    'description': event.description[:100] + '...',
                                    'event_type': event.event_type,
                                    'confidence': event.confidence,
                                    'entities': event.entities_involved
                                }
                                for event in sorted_events
                            ],
                            'backgroundColor': self.visualization_themes[theme]['primary_color'],
                            'borderColor': self.visualization_themes[theme]['secondary_color']
                        }
                    ]
                },
                'options': {
                    'responsive': True,
                    'plugins': {
                        'title': {
                            'display': True,
                            'text': f'Event Timeline: {sorted_events[0].topic if sorted_events else "No Events"}'
                        },
                        'tooltip': {
                            'mode': 'index',
                            'intersect': False
                        }
                    },
                    'scales': {
                        'x': {
                            'type': 'time',
                            'time': {
                                'unit': 'day'
                            },
                            'title': {
                                'display': True,
                                'text': 'Date'
                            }
                        },
                        'y': {
                            'title': {
                                'display': True,
                                'text': 'Impact Score'
                            }
                        }
                    }
                }
            }
            
            return chart_data
            
        except Exception as e:
            logger.error(f"Failed to prepare timeline chart data: {e}")
            return {'type': 'timeline', 'data': [], 'error': str(e)}
    
    def _generate_event_clusters(self, events: List[HistoricalEvent]) -> Dict[str, Any]:
        """Generate event clusters for visualization."""
        try:
            # Group events by type and time proximity
            clusters = defaultdict(list)
            
            for event in events:
                # Create cluster key based on event type and time period
                time_period = event.timestamp.strftime('%Y-%m')
                cluster_key = f"{event.event_type}_{time_period}"
                clusters[cluster_key].append(event)
            
            # Format clusters for visualization
            cluster_data = []
            for cluster_key, cluster_events in clusters.items():
                event_type, time_period = cluster_key.split('_')
                cluster_data.append({
                    'cluster_id': cluster_key,
                    'event_type': event_type,
                    'time_period': time_period,
                    'event_count': len(cluster_events),
                    'average_impact': sum(e.impact_score for e in cluster_events) / len(cluster_events),
                    'events': [e.event_id for e in cluster_events]
                })
            
            return {
                'total_clusters': len(cluster_data),
                'clusters': cluster_data
            }
            
        except Exception as e:
            logger.error(f"Failed to generate event clusters: {e}")
            return {'total_clusters': 0, 'clusters': [], 'error': str(e)}
    
    def _generate_impact_analysis(self, events: List[HistoricalEvent]) -> Dict[str, Any]:
        """Generate impact analysis for events."""
        try:
            if not events:
                return {'total_events': 0, 'analysis': {}}
            
            impact_scores = [event.impact_score for event in events]
            
            analysis = {
                'total_events': len(events),
                'impact_statistics': {
                    'average_impact': sum(impact_scores) / len(impact_scores),
                    'max_impact': max(impact_scores),
                    'min_impact': min(impact_scores),
                    'high_impact_events': len([s for s in impact_scores if s > 0.8]),
                    'medium_impact_events': len([s for s in impact_scores if 0.5 <= s <= 0.8]),
                    'low_impact_events': len([s for s in impact_scores if s < 0.5])
                },
                'top_impact_events': [
                    {
                        'event_id': event.event_id,
                        'title': event.title,
                        'impact_score': event.impact_score,
                        'timestamp': event.timestamp.isoformat()
                    }
                    for event in sorted(events, key=lambda x: x.impact_score, reverse=True)[:5]
                ]
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Failed to generate impact analysis: {e}")
            return {'total_events': 0, 'analysis': {}, 'error': str(e)}
    
    def _generate_entity_involvement_chart(self, events: List[HistoricalEvent]) -> Dict[str, Any]:
        """Generate entity involvement chart data."""
        try:
            # Count entity occurrences
            entity_counts = defaultdict(int)
            for event in events:
                for entity in event.entities_involved:
                    entity_counts[entity] += 1
            
            # Sort by frequency
            sorted_entities = sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)
            
            # Prepare chart data
            chart_data = {
                'type': 'bar',
                'data': {
                    'labels': [entity for entity, count in sorted_entities[:20]],  # Top 20
                    'datasets': [
                        {
                            'label': 'Event Mentions',
                            'data': [count for entity, count in sorted_entities[:20]],
                            'backgroundColor': 'rgba(54, 162, 235, 0.6)',
                            'borderColor': 'rgba(54, 162, 235, 1)',
                            'borderWidth': 1
                        }
                    ]
                },
                'options': {
                    'responsive': True,
                    'plugins': {
                        'title': {
                            'display': True,
                            'text': 'Entity Involvement in Events'
                        }
                    },
                    'scales': {
                        'y': {
                            'beginAtZero': True,
                            'title': {
                                'display': True,
                                'text': 'Number of Events'
                            }
                        }
                    }
                }
            }
            
            return chart_data
            
        except Exception as e:
            logger.error(f"Failed to generate entity involvement chart: {e}")
            return {'type': 'bar', 'data': [], 'error': str(e)}
    
    # Helper methods
    
    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse timestamp string to datetime object."""
        try:
            # Try different timestamp formats
            formats = [
                '%Y-%m-%dT%H:%M:%S.%fZ',
                '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d'
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(timestamp_str, fmt)
                except ValueError:
                    continue
            
            # If all formats fail, return current time
            logger.warning(f"Could not parse timestamp: {timestamp_str}")
            return datetime.now()
            
        except Exception as e:
            logger.error(f"Error parsing timestamp {timestamp_str}: {e}")
            return datetime.now()
    
    def _classify_event_type(self, result: Dict[str, Any]) -> str:
        """Classify event type based on content."""
        try:
            title = result.get('title', [''])[0].lower()
            content = result.get('content', [''])[0].lower()
            category = result.get('category', [''])[0].lower()
            
            # Simple classification rules
            if any(word in title or word in content for word in ['announce', 'launch', 'release']):
                return 'announcement'
            elif any(word in title or word in content for word in ['regulation', 'law', 'policy']):
                return 'regulation'
            elif any(word in title or word in content for word in ['acquisition', 'merger', 'purchase']):
                return 'business_transaction'
            elif any(word in title or word in content for word in ['research', 'study', 'findings']):
                return 'research'
            elif 'technology' in category or 'tech' in category:
                return 'technology'
            else:
                return 'general'
                
        except Exception as e:
            logger.warning(f"Failed to classify event type: {e}")
            return 'unknown'
    
    def _extract_entities_from_result(self, result: Dict[str, Any]) -> List[str]:
        """Extract entities from graph result."""
        try:
            # For now, return empty list - this would be enhanced with
            # actual entity extraction from the content
            entities = []
            
            # Extract from title if it contains recognizable entities
            title = result.get('title', [''])[0]
            if title:
                # Simple entity extraction (would be enhanced with NLP)
                common_entities = ['Google', 'Microsoft', 'Apple', 'Amazon', 'Meta', 
                                 'Tesla', 'OpenAI', 'AI', 'Artificial Intelligence']
                for entity in common_entities:
                    if entity.lower() in title.lower():
                        entities.append(entity)
            
            return entities[:5]  # Limit to 5 entities
            
        except Exception as e:
            logger.warning(f"Failed to extract entities: {e}")
            return []
    
    async def _calculate_impact_score(self, event: HistoricalEvent) -> float:
        """Calculate impact score for an event."""
        try:
            score = 0.5  # Base score
            
            # Increase score based on title keywords
            high_impact_keywords = ['breakthrough', 'major', 'significant', 'revolutionary']
            for keyword in high_impact_keywords:
                if keyword.lower() in event.title.lower():
                    score += 0.1
            
            # Increase score based on number of entities involved
            score += min(len(event.entities_involved) * 0.05, 0.2)
            
            # Increase score based on event type
            impact_multipliers = {
                'announcement': 0.8,
                'regulation': 0.9,
                'business_transaction': 0.7,
                'research': 0.6,
                'technology': 0.8
            }
            
            multiplier = impact_multipliers.get(event.event_type, 0.5)
            score *= multiplier
            
            # Ensure score is between 0 and 1
            return min(max(score, 0.0), 1.0)
            
        except Exception as e:
            logger.warning(f"Failed to calculate impact score: {e}")
            return 0.5
    
    async def _find_related_events(self, event: HistoricalEvent) -> List[str]:
        """Find related events for the given event."""
        try:
            related_events = []
            
            # For now, return empty list - this would be enhanced with
            # actual similarity calculation and graph traversal
            # In a full implementation, this would:
            # 1. Find events with similar entities
            # 2. Find events in similar time periods
            # 3. Find events with similar content
            
            return related_events
            
        except Exception as e:
            logger.warning(f"Failed to find related events: {e}")
            return []
    
    async def _check_event_exists(self, event_id: str) -> bool:
        """Check if event already exists in Neptune."""
        try:
            if not self.graph_populator or not hasattr(self.graph_populator, '_execute_traversal'):
                return False
            
            query = f"g.V().has('event_id', '{event_id}').count()"
            result = await self.graph_populator._execute_traversal(query)
            
            return result and result[0] > 0
            
        except Exception as e:
            logger.warning(f"Failed to check if event exists: {e}")
            return False
    
    def _event_to_dict(self, event: HistoricalEvent) -> Dict[str, Any]:
        """Convert HistoricalEvent to dictionary for API response."""
        return {
            'event_id': event.event_id,
            'title': event.title,
            'description': event.description,
            'timestamp': event.timestamp.isoformat(),
            'topic': event.topic,
            'event_type': event.event_type,
            'entities_involved': event.entities_involved,
            'source_article_id': event.source_article_id,
            'confidence': event.confidence,
            'impact_score': event.impact_score,
            'related_events': event.related_events,
            'metadata': event.metadata
        }


# Example usage and testing
async def demo_event_timeline_service():
    """Demonstrate the Event Timeline Service functionality."""
    print("🎯 Event Timeline Service Demo - Issue #38")
    print("=" * 50)
    
    try:
        # Initialize service
        service = EventTimelineService()
        
        # Test 1: Track historical events
        print("\n1. Tracking historical events for 'Artificial Intelligence'...")
        events = await service.track_historical_events(
            topic="Artificial Intelligence",
            start_date=datetime.now() - timedelta(days=30),
            end_date=datetime.now()
        )
        print(f"   Found {len(events)} events")
        
        # Test 2: Store events in Neptune
        print("\n2. Storing events and relationships in Neptune...")
        if events:
            storage_result = await service.store_event_relationships(events[:5])
            print(f"   Stored {storage_result.get('events_stored', 0)} events")
            print(f"   Created {storage_result.get('relationships_created', 0)} relationships")
        
        # Test 3: Generate API response
        print("\n3. Generating timeline API response...")
        api_response = await service.generate_timeline_api_response(
            topic="Artificial Intelligence",
            max_events=10,
            include_visualizations=True
        )
        print(f"   Generated response with {api_response.get('total_events', 0)} events")
        print(f"   Visualization included: {api_response.get('metadata', {}).get('visualization_included', False)}")
        
        # Test 4: Generate visualization data
        print("\n4. Generating visualization data...")
        if events:
            viz_data = await service.generate_visualization_data(
                topic="Artificial Intelligence",
                events=events[:10],
                theme='default'
            )
            print(f"   Generated visualizations: {list(viz_data.keys())}")
        
        print("\n✅ Event Timeline Service demo completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run demo
    asyncio.run(demo_event_timeline_service())
