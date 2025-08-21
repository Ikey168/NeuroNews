"""
Knowledge Graph Population from NLP Data

This module handles the integration between NLP processing results and
the AWS Neptune knowledge graph, populating entities, relationships,
and linking articles to events and policies.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.knowledge_graph.graph_builder import GraphBuilder
from src.nlp.article_processor import ArticleProcessor
from src.nlp.ner_processor import NERProcessor

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Entity:
    """Represents a named entity extracted from NLP."""

    text: str
    label: str
    start: int
    end: int
    confidence: float = 0.0
    normalized_form: str = ""

    def __post_init__(self):
        if not self.normalized_form:
            self.normalized_form = self.text.strip().lower()


@dataclass
class Relationship:
    """Represents a relationship between two entities."""

    source_entity: str
    target_entity: str
    relation_type: str
    confidence: float
    context: str = ""
    article_id: Optional[str] = None


class KnowledgeGraphPopulator:
    """
    Populates AWS Neptune knowledge graph with NLP-extracted entities and relationships.

    This class integrates NLP processing results with the knowledge graph,
    creating entity nodes, relationship edges, and linking articles to
    historical events and policies.
    """

    def __init__(
        self,
        neptune_endpoint: str,
        ner_processor: Optional[NERProcessor] = None,
        article_processor: Optional[ArticleProcessor] = None,
    ):
        """
        Initialize the knowledge graph populator.

        Args:
            neptune_endpoint: AWS Neptune database endpoint
            ner_processor: Named Entity Recognition processor
            article_processor: Article processing component
        """
        self.graph_builder = GraphBuilder(neptune_endpoint)
        self.ner_processor = ner_processor or NERProcessor()
        self.article_processor = article_processor  # Keep as None if not provided

        # Entity type mappings for Neptune
        self.entity_type_mapping = {
            "PERSON": "Person",
            "ORG": "Organization",
            "GPE": "Location",
            "MONEY": "MonetaryValue",
            "DATE": "Date",
            "EVENT": "Event",
            "PRODUCT": "Product",
            "LAW": "Policy",
            "NORP": "Group",
        }

        # Relationship confidence threshold
        self.min_confidence = 0.6

        logger.info("KnowledgeGraphPopulator initialized")

    async def populate_from_article(
        self,
        article_id: str,
        title: str,
        content: str,
        published_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Process an article and populate the knowledge graph with extracted entities and relationships.

        Args:
            article_id: Unique identifier for the article
            title: Article title
            content: Article content
            published_date: When the article was published

        Returns:
            Dictionary containing processing results and statistics
        """
        try:
            logger.info(
                "Processing article {0} for knowledge graph population".format(
                    article_id
                )
            )

            # Ensure connection to Neptune
            await self.graph_builder.connect()

            # Extract entities from title and content
            full_text = "{0}. {1}".format(title, content)
            entities = await self._extract_entities(full_text)

            # Add article node
            await self._add_article_node(article_id, title, content, published_date)

            # Add entity nodes and relationships
            entity_nodes = []
            for entity in entities:
                entity_node = await self._add_entity_node(entity, article_id)
                if entity_node:
                    entity_nodes.append(entity_node)

                    # Link entity to article
                    await self._link_entity_to_article(entity, article_id)

            # Extract and add relationships between entities
            relationships = await self._extract_relationships(
                entities, full_text, article_id
            )
            relationship_edges = []
            for relationship in relationships:
                if relationship.confidence >= self.min_confidence:
                    edge = await self._add_relationship_edge(relationship)
                    if edge:
                        relationship_edges.append(edge)

            # Link to historical events and policies
            historical_links = await self._link_to_historical_data(entities, article_id)

            # Calculate statistics
            stats = {
                "article_id": article_id,
                "entities_found": len(entities),
                "entities_added": len(entity_nodes),
                "relationships_found": len(relationships),
                "relationships_added": len(relationship_edges),
                "historical_links": len(historical_links),
                "processing_timestamp": datetime.utcnow().isoformat(),
            }

            logger.info(
                "Successfully processed article {0}: {1}".format(article_id, stats)
            )
            return stats

        except Exception as e:
            logger.error("Error processing article {0}: {1}".format(article_id, str(e)))
            raise

    async def _extract_entities(self, text: str) -> List[Entity]:
        """Extract named entities from text using NLP processor."""
        try:
            # Use NER processor to extract entities
            ner_results = await self.ner_processor.process_text(text)

            entities = []
            for ent in ner_results.get("entities", []):
                entity = Entity(
                    text=ent.get("text", ""),
                    label=ent.get("label", ""),
                    start=ent.get("start", 0),
                    end=ent.get("end", 0),
                    confidence=ent.get("confidence", 0.0),
                )
                entities.append(entity)

            logger.debug("Extracted {0} entities from text".format(len(entities)))
            return entities

        except Exception as e:
            logger.error("Error extracting entities: {0}".format(str(e)))
            return []

    async def _add_article_node(
        self,
        article_id: str,
        title: str,
        content: str,
        published_date: Optional[datetime],
    ) -> Dict[str, Any]:
        """Add an article node to the knowledge graph."""
        try:
            properties = {
                "id": article_id,
                "title": title,
                "content": content[:1000],  # Truncate for storage
                "content_length": len(content),
                "created_at": datetime.utcnow().isoformat(),
                "type": "article",
            }

            if published_date:
                properties["published_date"] = published_date.isoformat()

            # Add content hash for deduplication
            content_hash = hashlib.md5(content.encode()).hexdigest()
            properties["content_hash"] = content_hash

            result = await self.graph_builder.add_vertex("Article", properties)
            logger.debug("Added article node: {0}".format(article_id))
            return result

        except Exception as e:
            logger.error(
                "Error adding article node {0}: {1}".format(article_id, str(e))
            )
            return None

    async def _add_entity_node(self, entity: Entity, article_id: str) -> Dict[str, Any]:
        """Add an entity node to the knowledge graph."""
        try:
            # Generate unique entity ID
            entity_id = self._generate_entity_id(entity.normalized_form, entity.label)

            # Map entity label to Neptune-friendly type
            entity_type = self.entity_type_mapping.get(entity.label, "Entity")

            properties = {
                "id": entity_id,
                "text": entity.text,
                "normalized_form": entity.normalized_form,
                "entity_type": entity.label,
                "confidence": entity.confidence,
                "first_seen": datetime.utcnow().isoformat(),
                "mention_count": 1,
                "source_article": article_id,
            }

            # Check if entity already exists
            existing = await self._find_entity(entity_id)
            if existing:
                # Update existing entity
                result = await self._update_entity_mentions(entity_id, article_id)
            else:
                # Add new entity
                result = await self.graph_builder.add_vertex(entity_type, properties)

            logger.debug(
                "Added/updated entity: {0} ({1})".format(entity.text, entity.label)
            )
            return result

        except Exception as e:
            logger.error(
                "Error adding entity node {0}: {1}".format(entity.text, str(e))
            )
            return None

    async def _link_entity_to_article(self, entity: Entity, article_id: str):
        """Create a relationship between an entity and the article it appears in."""
        try:
            entity_id = self._generate_entity_id(entity.normalized_form, entity.label)

            edge_properties = {
                "relation_type": "mentioned_in",
                "confidence": entity.confidence,
                "start_position": entity.start,
                "end_position": entity.end,
                "created_at": datetime.utcnow().isoformat(),
            }

            result = await self.graph_builder.add_edge(
                entity_id, article_id, "MENTIONED_IN", edge_properties
            )
            return result

        except Exception as e:
            logger.error(
                "Error linking entity {0} to article {1}: {2}".format(
                    entity.text, article_id, str(e)
                )
            )
            return None

    async def _extract_relationships(
        self, entities: List[Entity], text: str, article_id: str
    ) -> List[Relationship]:
        """Extract relationships between entities using pattern matching and NLP."""
        relationships = []

        try:
            # Simple co-occurrence based relationships
            for i, entity1 in enumerate(entities):
                for entity2 in entities[i + 1:]:
                    # Skip if same entity
                    if entity1.normalized_form == entity2.normalized_form:
                        continue

                    # Check proximity in text
                    distance = abs(entity1.start - entity2.start)
                    if distance < 100:  # Entities are close to each other

                        # Determine relationship type based on entity types
                        relation_type = self._determine_relationship_type(
                            entity1.label, entity2.label
                        )

                        if relation_type:
                            # Extract context around the entities
                            context_start = max(
                                0, min(entity1.start, entity2.start) - 50
                            )
                            context_end = min(
                                len(text), max(entity1.end, entity2.end) + 50
                            )
                            context = text[context_start:context_end]

                            # Calculate confidence based on distance and entity
                            # confidence
                            confidence = min(entity1.confidence, entity2.confidence) * (
                                1 - distance / 200
                            )

                            relationship = Relationship(
                                source_entity=entity1.normalized_form,
                                target_entity=entity2.normalized_form,
                                relation_type=relation_type,
                                confidence=confidence,
                                context=context,
                                article_id=article_id,
                            )
                            relationships.append(relationship)

            logger.debug("Extracted {0} relationships".format(len(relationships)))
            return relationships

        except Exception as e:
            logger.error("Error extracting relationships: {0}".format(str(e)))
            return []

    def _determine_relationship_type(self, label1: str, label2: str) -> Optional[str]:
        """Determine the type of relationship between two entity types."""

        # Define relationship mapping
        relationship_rules = {
            ("PERSON", "ORG"): "works_for",
            ("PERSON", "GPE"): "located_in",
            ("ORG", "GPE"): "based_in",
            ("PERSON", "PERSON"): "associated_with",
            ("ORG", "ORG"): "related_to",
            ("PERSON", "EVENT"): "involved_in",
            ("ORG", "EVENT"): "participated_in",
            ("PERSON", "PRODUCT"): "created",
            ("ORG", "PRODUCT"): "produces",
            ("LAW", "GPE"): "applies_to",
            ("LAW", "ORG"): "regulates",
        }

        # Check both directions
        key1 = (label1, label2)
        key2 = (label2, label1)

        if key1 in relationship_rules:
            return relationship_rules[key1]
        elif key2 in relationship_rules:
            return relationship_rules[key2]
        else:
            return "related_to"  # Default relationship

    async def _add_relationship_edge(
        self, relationship: Relationship
    ) -> Dict[str, Any]:
        """Add a relationship edge between two entities."""
        try:
            source_id = self._generate_entity_id(
                relationship.source_entity,
                self._get_entity_label(relationship.source_entity),
            )
            target_id = self._generate_entity_id(
                relationship.target_entity,
                self._get_entity_label(relationship.target_entity),
            )

            edge_properties = {
                "relation_type": relationship.relation_type,
                "confidence": relationship.confidence,
                "context": relationship.context[:500],  # Truncate context
                "source_article": relationship.article_id,
                "created_at": datetime.utcnow().isoformat(),
            }

            result = await self.graph_builder.add_edge(
                source_id,
                target_id,
                relationship.relation_type.upper(),
                edge_properties,
            )

            logger.debug(
                "Added relationship: {0} -> {1}".format(
                    relationship.source_entity, relationship.target_entity
                )
            )
            return result

        except Exception as e:
            logger.error("Error adding relationship edge: {0}".format(str(e)))
            return None

    async def _link_to_historical_data(
        self, entities: List[Entity], article_id: str
    ) -> List[Dict[str, Any]]:
        """Link current article entities to historical events and policies."""
        historical_links = []

        try:
            for entity in entities:
                # Find historical events related to this entity
                if entity.label in ["PERSON", "ORG", "GPE", "EVENT"]:
                    events = await self._find_related_historical_events(entity)
                    for event in events:
                        link = await self._create_historical_link(
                            entity, event, article_id, "historical_reference"
                        )
                        if link:
                            historical_links.append(link)

                # Find policies related to this entity
                if entity.label in ["LAW", "ORG", "PERSON"]:
                    policies = await self._find_related_policies(entity)
                    for policy in policies:
                        link = await self._create_historical_link(
                            entity, policy, article_id, "policy_reference"
                        )
                        if link:
                            historical_links.append(link)

            logger.debug("Created {0} historical links".format(len(historical_links)))
            return historical_links

        except Exception as e:
            logger.error("Error linking to historical data: {0}".format(str(e)))
            return []

    async def _find_related_historical_events(
        self, entity: Entity
    ) -> List[Dict[str, Any]]:
        """Find historical events related to an entity."""
        try:
            # Query for existing events that mention this entity
            query_result = await self.graph_builder.query_vertices(
                "Event", {"entity_mention": entity.normalized_form}
            )
            return query_result

        except Exception as e:
            logger.error(
                "Error finding historical events for {0}: {1}".format(
                    entity.text, str(e)
                )
            )
            return []

    async def _find_related_policies(self, entity: Entity) -> List[Dict[str, Any]]:
        """Find policies related to an entity."""
        try:
            # Query for existing policies that mention this entity
            query_result = await self.graph_builder.query_vertices(
                "Policy", {"entity_mention": entity.normalized_form}
            )
            return query_result

        except Exception as e:
            logger.error(
                "Error finding policies for {0}: {1}".format(entity.text, str(e))
            )
            return []

    async def _create_historical_link(
        self,
        entity: Entity,
        historical_item: Dict[str, Any],
        article_id: str,
        link_type: str,
    ) -> Dict[str, Any]:
        """Create a link between current entity and historical data."""
        try:
            entity_id = self._generate_entity_id(entity.normalized_form, entity.label)
            historical_id = historical_item.get("id")

            if not historical_id:
                return None

            edge_properties = {
                "link_type": link_type,
                "confidence": entity.confidence,
                "source_article": article_id,
                "created_at": datetime.utcnow().isoformat(),
            }

            result = await self.graph_builder.add_edge(
                entity_id, historical_id, link_type.upper(), edge_properties
            )
            return result

        except Exception as e:
            logger.error("Error creating historical link: {0}".format(str(e)))
            return None

    def _generate_entity_id(self, normalized_form: str, entity_type: str) -> str:
        """Generate a unique ID for an entity."""
        # Create a hash-based ID for consistent entity identification
        content = "{0}:{1}".format(entity_type, normalized_form)
        return hashlib.md5(content.encode()).hexdigest()

    def _get_entity_label(self, entity_text: str) -> str:
        """Get the label for an entity (placeholder - in real implementation,
        this would query the graph or maintain a cache)."""
        # This is a simplified placeholder
        return "ENTITY"

    async def _find_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Check if an entity already exists in the graph."""
        try:
            result = await self.graph_builder.query_vertices(
                None, {"id": entity_id}  # Any vertex type
            )
            return result[0] if result else None

        except Exception as e:
            logger.error("Error finding entity {0}: {1}".format(entity_id, str(e)))
            return None

    async def _update_entity_mentions(
        self, entity_id: str, article_id: str
    ) -> Dict[str, Any]:
        """Update mention count and add source article for existing entity."""
        try:
            # This would increment mention_count and add to source_articles list
            # Placeholder implementation
            result = await self.graph_builder.update_vertex_property(
                entity_id, "mention_count", "increment"
            )
            return result

        except Exception as e:
            logger.error(
                "Error updating entity mentions {0}: {1}".format(entity_id, str(e))
            )
            return None

    async def get_related_entities(
        self, entity_name: str, max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get entities related to a given entity name.
        This implements the /related_entities API functionality.

        Args:
            entity_name: Name of the entity to find relationships for
            max_results: Maximum number of related entities to return

        Returns:
            List of related entities with relationship information
        """
        try:
            logger.info("Finding entities related to: {0}".format(entity_name))

            # Normalize entity name
            normalized_name = entity_name.strip().lower()

            # Find the entity in the graph
            entity = await self._find_entity_by_name(normalized_name)
            if not entity:
                logger.warning("Entity not found: {0}".format(entity_name))
                return []

            entity_id = entity.get("id")

            # Get related entities through relationships
            related_entities = await self.graph_builder.get_related_vertices(
                entity_id, max_results
            )

            # Format results for API response
            formatted_results = []
            for related in related_entities:
                formatted_entity = {
                    "entity_name": related.get("text", ""),
                    "entity_type": related.get("entity_type", ""),
                    "relationship_type": related.get("relationship_type", ""),
                    "confidence": related.get("confidence", 0.0),
                    "mention_count": related.get("mention_count", 0),
                    "first_seen": related.get("first_seen", ""),
                    "last_updated": related.get("last_updated", ""),
                }
                formatted_results.append(formatted_entity)

            logger.info(
                "Found {0} related entities for {1}".format(
                    len(formatted_results), entity_name
                )
            )
            return formatted_results

        except Exception as e:
            logger.error(
                "Error getting related entities for {0}: {1}".format(
                    entity_name, str(e)
                )
            )
            return []

    async def _find_entity_by_name(
        self, normalized_name: str
    ) -> Optional[Dict[str, Any]]:
        """Find an entity by its normalized name."""
        try:
            result = await self.graph_builder.query_vertices(
                None, {"normalized_form": normalized_name}  # Any vertex type
            )
            return result[0] if result else None

        except Exception as e:
            logger.error(
                "Error finding entity by name {0}: {1}".format(normalized_name, str(e))
            )
            return None

    async def batch_populate_articles(
        self, articles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Process multiple articles in batch for knowledge graph population.

        Args:
            articles: List of article dictionaries with 'id', 'title', 'content'

        Returns:
            Batch processing statistics
        """
        try:
            logger.info(
                "Starting batch processing of {0} articles".format(len(articles))
            )

            total_entities = 0
            total_relationships = 0
            total_historical_links = 0
            processed_articles = 0
            failed_articles = 0

            for article in articles:
                try:
                    article_id = article.get("id")
                    title = article.get("title", "")
                    content = article.get("content", "")
                    published_date = article.get("published_date")

                    if published_date and isinstance(published_date, str):
                        published_date = datetime.fromisoformat(
                            published_date.replace("Z", "+00:00")
                        )

                    stats = await self.populate_from_article(
                        article_id, title, content, published_date
                    )

                    total_entities += stats.get("entities_added", 0)
                    total_relationships += stats.get("relationships_added", 0)
                    total_historical_links += stats.get("historical_links", 0)
                    processed_articles += 1

                except Exception as e:
                    logger.error(
                        f"Failed to process article {
                            article.get('id')}: {
                            str(e)}"
                    )
                    failed_articles += 1

            batch_stats = {
                "total_articles": len(articles),
                "processed_articles": processed_articles,
                "failed_articles": failed_articles,
                "total_entities_added": total_entities,
                "total_relationships_added": total_relationships,
                "total_historical_links": total_historical_links,
                "success_rate": processed_articles / len(articles) if articles else 0,
                "batch_completed_at": datetime.utcnow().isoformat(),
            }

            logger.info("Batch processing completed: {0}".format(batch_stats))
            return batch_stats

        except Exception as e:
            logger.error("Error in batch processing: {0}".format(str(e)))
            raise

    async def close(self):
        """Close the connection to the knowledge graph."""
        try:
            if self.graph_builder.connection:
                await self.graph_builder.close()
            logger.info("Knowledge graph connection closed")

        except Exception as e:
            logger.error("Error closing knowledge graph connection: {0}".format(str(e)))


# Utility functions for integration
async def populate_article_to_graph(
    article_data: Dict[str, Any], neptune_endpoint: str
) -> Dict[str, Any]:
    """
    Convenience function to populate a single article into the knowledge graph.

    Args:
        article_data: Dictionary containing article information
        neptune_endpoint: Neptune database endpoint

    Returns:
        Processing statistics
    """
    populator = KnowledgeGraphPopulator(neptune_endpoint)
    try:
        stats = await populator.populate_from_article(
            article_data.get("id"),
            article_data.get("title", ""),
            article_data.get("content", ""),
            article_data.get("published_date"),
        )
        return stats
    finally:
        await populator.close()


async def get_entity_relationships(
    entity_name: str, neptune_endpoint: str, max_results: int = 10
) -> List[Dict[str, Any]]:
    """
    Convenience function to get related entities for API endpoint.

    Args:
        entity_name: Name of the entity to find relationships for
        neptune_endpoint: Neptune database endpoint
        max_results: Maximum number of results to return

    Returns:
        List of related entities
    """
    populator = KnowledgeGraphPopulator(neptune_endpoint)
    try:
        return await populator.get_related_entities(entity_name, max_results)
    finally:
        await populator.close()
