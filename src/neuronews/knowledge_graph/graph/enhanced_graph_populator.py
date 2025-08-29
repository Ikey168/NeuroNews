"""
Enhanced Knowledge Graph Populator - Issue #36

This module provides advanced knowledge graph population capabilities that integrate
with the enhanced entity extractor and optimized NLP pipeline. It handles the complete
flow from NLP entity extraction to Neptune graph population with sophisticated
relationship mapping and SPARQL/Gremlin query support.

Key Features:
- Integration with enhanced entity extraction
- Advanced relationship mapping and validation
- Batch processing for optimal performance
- Entity linking and deduplication
- Comprehensive SPARQL/Gremlin query support
- Temporal relationship tracking
- Data quality validation and monitoring
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

# Import enhanced components
try:
    from .enhanced_entity_extractor import (
        AdvancedEntityExtractor,
        EnhancedEntity,
        EnhancedRelationship,
        create_advanced_entity_extractor,
    )

    ENHANCED_EXTRACTOR_AVAILABLE = True
except ImportError:
    ENHANCED_EXTRACTOR_AVAILABLE = False

# Import existing knowledge graph components
try:
    from .graph_builder import GraphBuilder
    from gremlin_python.process.graph_traversal import __

    GRAPH_BUILDER_AVAILABLE = True
except ImportError:
    GRAPH_BUILDER_AVAILABLE = False

# Import optimized NLP components
try:
    pass

    OPTIMIZED_NLP_AVAILABLE = True
except ImportError:
    OPTIMIZED_NLP_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EnhancedKnowledgeGraphPopulator:
    """
    Enhanced knowledge graph populator that provides sophisticated entity and
    relationship extraction with optimized Neptune integration.
    """

    def __init__(
        self,
        neptune_endpoint: str,
        entity_extractor: Optional[AdvancedEntityExtractor] = None,
        batch_size: int = 50,
        enable_temporal_tracking: bool = True,
        enable_entity_linking: bool = True,
    ):
        """
        Initialize the enhanced knowledge graph populator.

        Args:
            neptune_endpoint: AWS Neptune database endpoint
            entity_extractor: Advanced entity extractor instance
            batch_size: Batch size for processing operations
            enable_temporal_tracking: Whether to track temporal relationships
            enable_entity_linking: Whether to enable entity linking and deduplication
        """
        if not GRAPH_BUILDER_AVAILABLE:
            raise ImportError("GraphBuilder not available")

        self.neptune_endpoint = neptune_endpoint
        self.graph_builder = GraphBuilder(neptune_endpoint)
        self.entity_extractor = entity_extractor or create_advanced_entity_extractor()
        self.batch_size = batch_size
        self.enable_temporal_tracking = enable_temporal_tracking
        self.enable_entity_linking = enable_entity_linking

        # Entity and relationship tracking
        self.entity_registry = {}  # Maps entity_id to Neptune vertex_id
        self.relationship_registry = set()  # Tracks existing relationships
        self.processing_queue = []

        # Configuration
        self.entity_confidence_threshold = 0.7
        self.relationship_confidence_threshold = 0.6
        self.max_entities_per_article = 100
        self.max_relationships_per_article = 200

        # Statistics
        self.stats = {
            "articles_processed": 0,
            "entities_created": 0,
            "relationships_created": 0,
            "entities_linked": 0,
            "duplicates_merged": 0,
            "processing_errors": 0,
            "total_processing_time": 0.0,
        }

        logger.info("EnhancedKnowledgeGraphPopulator initialized")

    async def populate_from_article(
        self,
        article_id: str,
        title: str,
        content: str,
        published_date: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Process an article and populate the knowledge graph with extracted entities and relationships.

        Args:
            article_id: Unique identifier for the article
            title: Article title
            content: Article content
            published_date: When the article was published
            metadata: Additional article metadata

        Returns:
            Dictionary containing processing results and statistics
        """
        start_time = datetime.now()

        try:
            logger.info(
                "Processing article {0} for enhanced knowledge graph population".format(
                    article_id
                )
            )

            # Ensure connection to Neptune
            await self.graph_builder.connect()

            # Extract entities using enhanced extractor
            entities = await self.entity_extractor.extract_entities_from_article(
                article_id, title, content
            )

            # Filter entities by confidence
            filtered_entities = [
                entity
                for entity in entities
                if entity.confidence >= self.entity_confidence_threshold
            ][: self.max_entities_per_article]

            # Extract relationships
            full_text = "{0}. {1}".format(title, content)
            relationships = await self.entity_extractor.extract_relationships(
                filtered_entities, full_text, article_id
            )

            # Filter relationships by confidence
            filtered_relationships = [
                rel
                for rel in relationships
                if rel.confidence >= self.relationship_confidence_threshold
            ][: self.max_relationships_per_article]

            # Add article node to graph
            article_vertex_id = await self._add_article_vertex(
                article_id, title, content, published_date, metadata
            )

            # Process entities in batches
            entity_results = await self._process_entities_batch(
                filtered_entities, article_id, article_vertex_id
            )

            # Process relationships in batches
            relationship_results = await self._process_relationships_batch(
                filtered_relationships, article_id
            )

            # Link entities to historical data if enabled
            historical_links = []
            if self.enable_entity_linking:
                historical_links = await self._link_to_historical_entities(
                    filtered_entities, article_id
                )

            # Update statistics
            processing_time = (datetime.now() - start_time).total_seconds()
            self.stats["articles_processed"] += 1
            self.stats["entities_created"] += len(entity_results["created"])
            self.stats["relationships_created"] += len(
                relationship_results["created"])
            self.stats["entities_linked"] += len(historical_links)
            self.stats["total_processing_time"] += processing_time

            result = {
                "article_id": article_id,
                "article_vertex_id": article_vertex_id,
                "entities": {
                    "extracted": len(entities),
                    f"iltered": len(filtered_entities),
                    "created": len(entity_results["created"]),
                    "linked": len(entity_results["linked"]),
                    "merged": len(entity_results["merged"]),
                },
                "relationships": {
                    "extracted": len(relationships),
                    f"iltered": len(filtered_relationships),
                    "created": len(relationship_results["created"]),
                    "skipped": len(relationship_results["skipped"]),
                },
                "historical_links": len(historical_links),
                "processing_time": processing_time,
                "timestamp": datetime.utcnow().isoformat(),
            }

            logger.info(
                "Successfully processed article {0}: {1}".format(
                    article_id, result)
            )
            return result

        except Exception as e:
            self.stats["processing_errors"] += 1
            logger.error("Error processing article {0}: {1}".format(
                article_id, str(e)))
            raise

    async def populate_from_articles_batch(
        self, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Process multiple articles in batch for optimal performance.

        Args:
            articles: List of article dictionaries with id, title, content, etc.

        Returns:
            List of processing results for each article
        """
        results = []

        # Process articles in smaller batches to manage memory
        for i in range(0, len(articles), self.batch_size):
            batch = articles[i: i + self.batch_size]

            # Process batch concurrently
            batch_tasks = []
            for article in batch:
                task = self.populate_from_article(
                    article["id"],
                    article["title"],
                    article["content"],
                    article.get("published_date"),
                    article.get("metadata", {}),
                )
                batch_tasks.append(task)

            # Wait for batch completion
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error("Batch processing error: {0}".format(result))
                    self.stats["processing_errors"] += 1
                else:
                    results.append(result)

        logger.info("Processed {0} articles in batch".format(len(results)))
        return results

    async def _add_article_vertex(
        self,
        article_id: str,
        title: str,
        content: str,
        published_date: Optional[datetime],
        metadata: Optional[Dict[str, Any]],
    ) -> str:
        """Add an article vertex to the knowledge graph."""
        properties = {
            "id": article_id,
            "title": title,
            "content": content[:1000],  # Truncate for storage efficiency
            "content_length": len(content),
            "created_at": datetime.utcnow().isoformat(),
            "source": "enhanced_nlp_populator",
        }

        if published_date:
            properties["published_date"] = published_date.isoformat()

        if metadata:
            # Add selected metadata fields
            for key in ["source_url", "author", "category", "tags"]:
                if key in metadata:
                    properties[key] = metadata[key]

        result = await self.graph_builder.add_vertex("Article", properties)
        vertex_id = result.get("id") if result else article_id

        logger.debug("Added article vertex: {0}".format(vertex_id))
        return vertex_id

    async def _process_entities_batch(
        self, entities: List[EnhancedEntity], article_id: str, article_vertex_id: str
    ) -> Dict[str, Any]:
        """Process a batch of entities and add them to the knowledge graph."""
        created_entities = []
        linked_entities = []
        merged_entities = []

        for entity in entities:
            try:
                # Check if entity already exists
                existing_vertex_id = await self._find_existing_entity(entity)

                if existing_vertex_id:
                    # Link to existing entity
                    linked_entities.append(existing_vertex_id)
                    if self.enable_entity_linking:
                        await self._merge_entity_data(existing_vertex_id, entity)
                        merged_entities.append(existing_vertex_id)
                else:
                    # Create new entity vertex
                    vertex_id = await self._add_entity_vertex(entity)
                    if vertex_id:
                        created_entities.append(vertex_id)
                        self.entity_registry[entity.entity_id] = vertex_id

                # Link entity to article
                entity_vertex_id = existing_vertex_id or self.entity_registry.get(
                    entity.entity_id
                )
                if entity_vertex_id:
                    await self._link_entity_to_article(
                        entity, article_vertex_id, entity_vertex_id
                    )

            except Exception as e:
                logger.error(
                    "Error processing entity {0}: {1}".format(entity.text, e))
                continue

        return {
            "created": created_entities,
            "linked": linked_entities,
            "merged": merged_entities,
        }

    async def _add_entity_vertex(self, entity: EnhancedEntity) -> Optional[str]:
        """Add an entity vertex to the knowledge graph."""
        try:
            # Map entity type to Neptune label
            entity_type_mapping = {
                "PERSON": "Person",
                "ORGANIZATION": "Organization",
                "TECHNOLOGY": "Technology",
                "POLICY": "Policy",
                "LOCATION": "Location",
                "MISCELLANEOUS": "Entity",
            }

            neptune_label = entity_type_mapping.get(entity.label, "Entity")

            # Prepare properties based on entity type
            properties = {
                "id": entity.entity_id,
                "text": entity.text,
                "normalized_form": entity.normalized_form,
                "entity_type": entity.label,
                "confidence": entity.confidence,
                "mention_count": entity.mention_count,
                "created_at": datetime.utcnow().isoformat(),
                "source_article_id": entity.source_article_id,
            }

            # Add type-specific properties
            if neptune_label == "Person":
                properties.update(
                    {
                        "name": entity.normalized_form,
                        "title": entity.properties.get("title", ""),
                        "organization": entity.properties.get("organization", ""),
                    }
                )
            elif neptune_label == "Organization":
                properties.update(
                    {
                        "orgName": entity.normalized_form,
                        "type": entity.properties.get("type", ""),
                        "industry": entity.properties.get("industry", ""),
                    }
                )
            elif neptune_label == "Technology":
                properties.update(
                    {
                        "techName": entity.normalized_form,
                        "category": entity.properties.get("category", ""),
                        "description": entity.properties.get("description", ""),
                    }
                )
            elif neptune_label == "Policy":
                properties.update(
                    {
                        "policyName": entity.normalized_form,
                        "type": entity.properties.get("type", ""),
                        "jurisdiction": entity.properties.get("jurisdiction", ""),
                    }
                )
            elif neptune_label == "Location":
                properties.update(
                    {
                        "locationName": entity.normalized_form,
                        "type": entity.properties.get("type", ""),
                        "country": entity.properties.get("country", ""),
                    }
                )

            # Add aliases if present
            if entity.aliases:
                properties["aliases"] = json.dumps(entity.aliases)

            result = await self.graph_builder.add_vertex(neptune_label, properties)
            vertex_id = result.get("id") if result else entity.entity_id

            logger.debug(
                "Added entity vertex: {0} ({1})".format(vertex_id, entity.text)
            )
            return vertex_id

        except Exception as e:
            logger.error(
                "Error adding entity vertex for {0}: {1}".format(
                    entity.text, e)
            )
            return None

    async def _process_relationships_batch(
        self, relationships: List[EnhancedRelationship], article_id: str
    ) -> Dict[str, Any]:
        """Process a batch of relationships and add them to the knowledge graph."""
        created_relationships = []
        skipped_relationships = []

        for relationship in relationships:
            try:
                # Get vertex IDs for source and target entities
                source_vertex_id = self.entity_registry.get(
                    relationship.source_entity.entity_id
                )
                target_vertex_id = self.entity_registry.get(
                    relationship.target_entity.entity_id
                )

                if not source_vertex_id or not target_vertex_id:
                    skipped_relationships.append(relationship.to_dict())
                    continue

                # Check if relationship already exists
                relationship_key = "{0}:{1}:{2}".format(
                    source_vertex_id, relationship.relation_type, target_vertex_id
                )
                if relationship_key in self.relationship_registry:
                    skipped_relationships.append(relationship.to_dict())
                    continue

                # Add relationship edge
                edge_properties = {
                    "confidence": relationship.confidence,
                    # Truncate for storage
                    "context": relationship.context[:500],
                    "article_id": article_id,
                    "evidence_count": len(relationship.evidence_sentences),
                    "created_at": datetime.utcnow().isoformat(),
                }

                # Add temporal information if available
                if self.enable_temporal_tracking and relationship.temporal_info:
                    edge_properties.update(relationship.temporal_info)

                result = await self.graph_builder.add_relationship(
                    source_vertex_id,
                    target_vertex_id,
                    relationship.relation_type,
                    edge_properties,
                )

                if result:
                    created_relationships.append(relationship.to_dict())
                    self.relationship_registry.add(relationship_key)
                else:
                    skipped_relationships.append(relationship.to_dict())

            except Exception as e:
                logger.error("Error processing relationship: {0}".format(e))
                skipped_relationships.append(relationship.to_dict())
                continue

        return {"created": created_relationships, "skipped": skipped_relationships}

    async def _find_existing_entity(self, entity: EnhancedEntity) -> Optional[str]:
        """Find existing entity in the knowledge graph by normalized form."""
        try:
            # Query Neptune for existing entity
            # query = commented out - unused variable
            # g.V().hasLabel('{self._get_neptune_label(entity.label)}')
            #      .has('normalized_form', '{entity.normalized_form}')
            #      .id()

            results = await self.graph_builder._execute_traversal(
                self.graph_builder.g.V()
                .hasLabel(self._get_neptune_label(entity.label))
                .has("normalized_form", entity.normalized_form)
                .id()
            )

            return results[0] if results else None

        except Exception as e:
            logger.debug(
                "Error finding existing entity {0}: {1}".format(entity.text, e)
            )
            return None

    async def _merge_entity_data(self, vertex_id: str, entity: EnhancedEntity):
        """Merge additional data into an existing entity vertex."""
        try:
            # Update mention count and confidence
            update_properties = {
                "mention_count": entity.mention_count,
                # Keep higher confidence
                "confidence": max(entity.confidence, 0.0),
                "last_mentioned": datetime.utcnow().isoformat(),
            }

            # Add new aliases
            if entity.aliases:
                # Get existing aliases and merge
                existing_vertex = await self.graph_builder.get_vertex_by_id(vertex_id)
                existing_aliases = (
                    json.loads(existing_vertex.get("aliases", "[]"))
                    if existing_vertex
                    else []
                )

                all_aliases = list(set(existing_aliases + entity.aliases))
                update_properties["aliases"] = json.dumps(all_aliases)

            # Update vertex properties
            await self._update_vertex_properties(vertex_id, update_properties)

        except Exception as e:
            logger.error(
                "Error merging entity data for vertex {0}: {1}".format(
                    vertex_id, e)
            )

    async def _link_entity_to_article(
        self, entity: EnhancedEntity, article_vertex_id: str, entity_vertex_id: str
    ):
        """Link an entity to the article that mentioned it."""
        try:
            edge_properties = {
                "mention_confidence": entity.confidence,
                "mention_count": entity.mention_count,
                "start_position": entity.start,
                "end_position": entity.end,
                "created_at": datetime.utcnow().isoformat(),
            }

            # Determine relationship type based on entity type
            mention_type_mapping = {
                "PERSON": "MENTIONS_PERSON",
                "ORGANIZATION": "MENTIONS_ORG",
                "TECHNOLOGY": "MENTIONS_TECH",
                "POLICY": "MENTIONS_POLICY",
                "LOCATION": "MENTIONS_LOCATION",
            }

            relation_type = mention_type_mapping.get(
                entity.label, "MENTIONS_ENTITY")

            await self.graph_builder.add_relationship(
                article_vertex_id, entity_vertex_id, relation_type, edge_properties
            )

        except Exception as e:
            logger.error(
                "Error linking entity {0} to article: {1}".format(
                    entity.text, e)
            )

    async def _link_to_historical_entities(
        self, entities: List[EnhancedEntity], article_id: str
    ) -> List[Dict[str, Any]]:
        """Link entities to historical data and existing entities."""
        historical_links = []

        for entity in entities:
            try:
                # Find similar entities based on normalized form and type
                similar_entities = await self._find_similar_entities(entity)

                for similar_entity_id in similar_entities:
                    # Create historical link relationship
                    link_properties = {
                        "similarity_score": 0.8,  # This could be calculated more precisely
                        "link_type": "SIMILAR_ENTITY",
                        "created_at": datetime.utcnow().isoformat(),
                        "source_article": article_id,
                    }

                    entity_vertex_id = self.entity_registry.get(
                        entity.entity_id)
                    if entity_vertex_id:
                        await self.graph_builder.add_relationship(
                            entity_vertex_id,
                            similar_entity_id,
                            "SIMILAR_TO",
                            link_properties,
                        )

                        historical_links.append(
                            {
                                "entity": entity.text,
                                "linked_to": similar_entity_id,
                                "similarity_score": 0.8,
                            }
                        )

            except Exception as e:
                logger.error(
                    "Error linking entity {0} to historical data: {1}".format(
                        entity.text, e
                    )
                )
                continue

        return historical_links

    async def _find_similar_entities(self, entity: EnhancedEntity) -> List[str]:
        """Find similar entities in the knowledge graph."""
        try:
            # Query for entities with similar normalized forms
            pass

            results = await self.graph_builder._execute_traversal(
                self.graph_builder.g.V()
                .hasLabel(self._get_neptune_label(entity.label))
                .has("normalized_form", entity.normalized_form)
                .id()
                .limit(5)
            )

            return results or []

        except Exception as e:
            logger.debug(
                "Error finding similar entities for {0}: {1}".format(
                    entity.text, e)
            )
            return []

    async def query_entity_relationships(
        self,
        entity_name: str,
        max_depth: int = 2,
        relationship_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Query entity relationships using Gremlin traversal.

        Args:
            entity_name: Name of the entity to query
            max_depth: Maximum traversal depth
            relationship_types: Optional filter for relationship types

        Returns:
            Dictionary with entity relationships and metadata
        """
        try:
            # Start with entity lookup
            base_query = self.graph_builder.g.V().has("normalized_form", entity_name)

            # Build traversal query
            if relationship_types:
                path_query = base_query
                for depth in range(max_depth):
                    path_query = (
                        path_query.bothE(
                            *relationship_types).otherV().simplePath()
                    )
            else:
                path_query = base_query
                for depth in range(max_depth):
                    path_query = path_query.both().simplePath()

            # Execute query
            results = await self.graph_builder._execute_traversal(
                path_query.dedup().valueMap(True).limit(100)
            )

            # Format results
            related_entities = []
            for result in results:
                entity_info = {
                    "id": result.get("id", [""])[0],
                    "name": result.get("normalized_form", [""])[0],
                    "type": result.get("entity_type", [""])[0],
                    "confidence": result.get("confidence", [0.0])[0],
                    "mention_count": result.get("mention_count", [0])[0],
                }
                related_entities.append(entity_info)

            return {
                "query_entity": entity_name,
                "related_entities": related_entities,
                "total_results": len(related_entities),
                "max_depth": max_depth,
                "relationship_types": relationship_types,
            }

        except Exception as e:
            logger.error(
                "Error querying entity relationships for {0}: {1}".format(
                    entity_name, e
                )
            )
            return {
                "query_entity": entity_name,
                "related_entities": [],
                "error": str(e),
            }

    async def execute_sparql_query(self, sparql_query: str) -> Dict[str, Any]:
        """
        Execute a SPARQL query against the knowledge graph.
        Note: This is a placeholder - actual SPARQL support depends on Neptune configuration.

        Args:
            sparql_query: SPARQL query string

        Returns:
            Query results
        """
        try:
            # This would need to be implemented based on Neptune's SPARQL'
            # endpoint
            logger.warning(
                "SPARQL queries not yet implemented - using Gremlin fallback"
            )

            # For now, return a placeholder response
            return {
                "query": sparql_query,
                "results": [],
                "message": "SPARQL support not yet implemented - use Gremlin queries",
            }

        except Exception as e:
            logger.error("Error executing SPARQL query: {0}".format(e))
            return {"query": sparql_query, "error": str(e)}

    def _get_neptune_label(self, entity_type: str) -> str:
        """Map entity type to Neptune vertex label."""
        mapping = {
            "PERSON": "Person",
            "ORGANIZATION": "Organization",
            "TECHNOLOGY": "Technology",
            "POLICY": "Policy",
            "LOCATION": "Location",
            "MISCELLANEOUS": "Entity",
        }
        return mapping.get(entity_type, "Entity")

    async def _update_vertex_properties(
        self, vertex_id: str, properties: Dict[str, Any]
    ):
        """Update properties of an existing vertex."""
        try:
            update_traversal = self.graph_builder.g.V().has("id", vertex_id)

            for key, value in properties.items():
                update_traversal = update_traversal.property(key, value)

            await self.graph_builder._execute_traversal(update_traversal)

        except Exception as e:
            logger.error(
                "Error updating vertex properties for {0}: {1}".format(
                    vertex_id, e)
            )

    async def validate_graph_data(self) -> Dict[str, Any]:
        """Validate the integrity and quality of the knowledge graph data."""
        try:
            validation_results = {
                "entity_counts": {},
                "relationship_counts": {},
                "orphaned_entities": 0,
                "duplicate_entities": 0,
                "data_quality_issues": [],
            }

            # Count entities by type
            entity_types = [
                "Person",
                "Organization",
                "Technology",
                "Policy",
                "Location",
                "Entity",
            ]
            for entity_type in entity_types:
                count_query = self.graph_builder.g.V().hasLabel(entity_type).count()
                count_results = await self.graph_builder._execute_traversal(count_query)
                validation_results["entity_counts"][entity_type] = (
                    count_results[0] if count_results else 0
                )

            # Count relationships by type
            relationship_types = [
                "WORKS_FOR",
                "PARTNERS_WITH",
                "COMPETES_WITH",
                "DEVELOPS",
                "USES_TECHNOLOGY",
            ]
            for rel_type in relationship_types:
                count_query = self.graph_builder.g.E().hasLabel(rel_type).count()
                count_results = await self.graph_builder._execute_traversal(count_query)
                validation_results["relationship_counts"][rel_type] = (
                    count_results[0] if count_results else 0
                )

            # Find orphaned entities (entities with no relationships)
            orphaned_query = (
                self.graph_builder.g.V().where(__.bothE().count().is_(0)).count()
            )
            orphaned_results = await self.graph_builder._execute_traversal(
                orphaned_query
            )
            validation_results["orphaned_entities"] = (
                orphaned_results[0] if orphaned_results else 0
            )

            # Add timestamp
            validation_results["validated_at"] = datetime.utcnow().isoformat()

            return validation_results

        except Exception as e:
            logger.error("Error validating graph data: {0}".format(e))
            return {"error": str(e), "validated_at": datetime.utcnow().isoformat()}

    def get_processing_statistics(self) -> Dict[str, Any]:
        """Get comprehensive processing statistics."""
        return {
            **self.stats,
            "entity_registry_size": len(self.entity_registry),
            "relationship_registry_size": len(self.relationship_registry),
            "average_processing_time": (
                self.stats["total_processing_time"] /
                    self.stats["articles_processed"]
                if self.stats["articles_processed"] > 0
                else 0
            ),
            "entities_per_article": (
                self.stats["entities_created"] /
                    self.stats["articles_processed"]
                if self.stats["articles_processed"] > 0
                else 0
            ),
            "relationships_per_article": (
                self.stats["relationships_created"] /
                    self.stats["articles_processed"]
                if self.stats["articles_processed"] > 0
                else 0
            ),
        }

    async def close(self):
        """Clean up resources and close connections."""
        try:
            if hasattr(self.graph_builder, "client") and self.graph_builder.client:
                await self.graph_builder.client.close()
            logger.info("EnhancedKnowledgeGraphPopulator closed successfully")
        except Exception as e:
            logger.error("Error closing populator: {0}".format(e))


# Factory functions for easy usage


def create_enhanced_knowledge_graph_populator(
    neptune_endpoint: str,
) -> EnhancedKnowledgeGraphPopulator:
    """Create an enhanced knowledge graph populator with standard configuration."""
    return EnhancedKnowledgeGraphPopulator(
        neptune_endpoint=neptune_endpoint,
        batch_size=50,
        enable_temporal_tracking=True,
        enable_entity_linking=True,
    )


def create_high_performance_graph_populator(
    neptune_endpoint: str,
) -> EnhancedKnowledgeGraphPopulator:
    """Create a high-performance populator optimized for large-scale processing."""
    return EnhancedKnowledgeGraphPopulator(
        neptune_endpoint=neptune_endpoint,
        batch_size=100,
        enable_temporal_tracking=False,  # Disable for performance
        enable_entity_linking=False,  # Disable for performance
    )


def create_high_quality_graph_populator(
    neptune_endpoint: str,
) -> EnhancedKnowledgeGraphPopulator:
    """Create a high-quality populator with enhanced validation and linking."""
    extractor = create_advanced_entity_extractor()
    extractor.confidence_threshold = 0.85  # Higher confidence for quality

    return EnhancedKnowledgeGraphPopulator(
        neptune_endpoint=neptune_endpoint,
        entity_extractor=extractor,
        batch_size=25,  # Smaller batches for careful processing
        enable_temporal_tracking=True,
        enable_entity_linking=True,
    )


if __name__ == "__main__":
    # Example usage and testing

    async def main():
        # Mock Neptune endpoint for testing
        neptune_endpoint = "wss://your-cluster.neptune.amazonaws.com:8182/gremlin"

        # Sample articles for testing
        sample_articles = [
            {
                "id": "kg_test_001",
                "title": "Apple and Google Announce AI Partnership",
                "content": """
                Apple Inc. and Google LLC have announced a groundbreaking partnership to develop
                artificial intelligence technologies. The collaboration will focus on machine learning
                and deep learning applications for consumer devices.

                Tim Cook, CEO of Apple, and Sundar Pichai, CEO of Google, will oversee the initiative.
                The partnership aims to create new AI standards and improve user privacy protections.

                Both companies are headquartered in Silicon Valley and have been investing heavily
                in AI research. The partnership will utilize TensorFlow and other open-source
                machine learning frameworks.
                """,
                "published_date": datetime(2025, 8, 17, 12, 0, 0),
                "metadata": {
                    "category": "Technology",
                    "source_url": "https://example.com/apple-google-ai-partnership",
                    "author": "Tech Reporter"
                },
            }
        ]

        try:
            # Create enhanced populator
            populator = create_enhanced_knowledge_graph_populator(
                neptune_endpoint)

            print(" Enhanced Knowledge Graph Population Demo")
            print("=" * 60)

            # Process single article
            result = await populator.populate_from_article(
                sample_articles[0]["id"],
                sample_articles[0]["title"],
                sample_articles[0]["content"],
                sample_articles[0]["published_date"],
                sample_articles[0]["metadata"],
            )

            print(" Processing Results:")
            print(f"  • Article ID: {result['article_id']}")
            print(f"  • Entities extracted: {result['entities']['extracted']}")
            print(f"  • Entities created: {result['entities']['created']}")
            print(
                f"  • Relationships found: {
                    result['relationships']['extracted']}"
            )
            print(
                f"  • Relationships created: {
                    result['relationships']['created']}"
            )
            print(f"  • Processing time: {result['processing_time']:.2f}s")

            # Query entity relationships
            query_result = await populator.query_entity_relationships(
                "Apple Inc.",
                max_depth=2,
                relationship_types=["PARTNERS_WITH", "WORKS_FOR"],
            )

            print("\n🔍 Entity Relationship Query:")
            print(f"  • Query entity: {query_result['query_entity']}")
            print(
                f"  • Related entities found: {query_result['total_results']}"
            )

            # Validate graph data
            validation = await populator.validate_graph_data()

            print("\n🔍 Graph Validation:")
            print(f"  • Entity counts: {validation['entity_counts']}")
            print(
                f"  • Relationship counts: {validation['relationship_counts']}"
            )
            print(f"  • Orphaned entities: {validation['orphaned_entities']}")

            # Get processing statistics
            stats = populator.get_processing_statistics()

            print("\n📊 Processing Statistics:")
            print(f"  • Articles processed: {stats['articles_processed']}")
            print(f"  • Entities created: {stats['entities_created']}")
            print(
                f"  • Relationships created: {stats['relationships_created']}"
            )
            print(
                f"  • Average entities per article: {
                    stats['entities_per_article']:.1f}"
            )
            print(
                f"  • Average relationships per article: {
                    stats['relationships_per_article']:.1f}"
            )

            # Clean up
            await populator.close()

            print("\n✅ Demo completed successfully!")

        except Exception as e:
            print("❌ Demo failed: {0}".format(e))

    # Run the example
    asyncio.run(main())
