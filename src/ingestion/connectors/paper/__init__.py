"""
Papers connector: arXiv ingestion, PDF parsing, and citation-graph construction.

Importing this package registers the ``paper`` connector.
"""

from src.ingestion.connectors.paper.arxiv import ArxivClient, parse_atom
from src.ingestion.connectors.paper.citation_graph import build_citation_graph
from src.ingestion.connectors.paper.connector import (
    PaperConnector,
    paper_metadata_to_document,
)
from src.ingestion.connectors.paper.models import PaperMetadata, Reference, paper_id
from src.ingestion.connectors.paper.references import (
    ReferencesProvider,
    SemanticScholarReferences,
    StaticReferencesProvider,
    parse_s2_references,
)

__all__ = [
    "ArxivClient",
    "parse_atom",
    "PaperConnector",
    "paper_metadata_to_document",
    "build_citation_graph",
    "PaperMetadata",
    "Reference",
    "paper_id",
    "ReferencesProvider",
    "StaticReferencesProvider",
    "SemanticScholarReferences",
    "parse_s2_references",
]
