"""
Tests for the papers connector and citation graph (#517).

Uses recorded fixtures (an arXiv Atom response and a Semantic-Scholar-style
references payload) so nothing hits the network. Covers the exit criterion:
ingest a paper by id and its references appear as CITES edges in the KG.
"""

import json
from pathlib import Path

import pytest

from services.ingest.common.document_contracts import DocumentIngestValidator
from src.ingestion.connectors import get_connector, is_registered
from src.ingestion.connectors.paper import (
    ArxivClient,
    PaperConnector,
    StaticReferencesProvider,
    parse_atom,
    parse_s2_references,
)
from src.ingestion.connectors.paper.models import PaperMetadata, Reference, paper_id
from src.ingestion.connectors.paper.pdf_parser import parse_pdf, split_sections
from src.knowledge_graph.foundation import (
    EntityType,
    KnowledgeGraphStore,
    RelationType,
)

FIXTURES = Path(__file__).parent / "fixtures"
ARXIV_ID = "1706.03762"


def _atom_bytes() -> bytes:
    return (FIXTURES / "arxiv_1706.03762.xml").read_bytes()


def _references():
    payload = (FIXTURES / "s2_references_1706.03762.json").read_bytes()
    return parse_s2_references(payload)


def _connector_with_refs() -> PaperConnector:
    meta = parse_atom(_atom_bytes())[0]
    provider = StaticReferencesProvider({meta.document_id: _references()})
    client = ArxivClient(http_get=lambda url: _atom_bytes())
    return PaperConnector(arxiv_client=client, references_provider=provider)


# --------------------------------------------------------------------------- #
# arXiv parsing
# --------------------------------------------------------------------------- #


def test_parse_atom_extracts_metadata():
    meta = parse_atom(_atom_bytes())[0]
    assert meta.arxiv_id == "1706.03762"  # version stripped
    assert meta.title == "Attention Is All You Need"
    assert meta.doi == "10.48550/arXiv.1706.03762"
    assert meta.primary_category == "cs.CL"
    assert "cs.LG" in meta.categories
    assert meta.authors[0] == "Ashish Vaswani"
    assert len(meta.authors) == 8
    assert meta.pdf_url.endswith(".pdf") or "pdf" in meta.pdf_url
    assert meta.published.year == 2017


def test_paper_id_prefers_arxiv_then_doi_then_title():
    assert paper_id(arxiv_id="1706.03762") == "arxiv:1706.03762"
    assert paper_id(doi="10.1/X") == "doi:10.1/x"
    assert paper_id(title="Some Title").startswith("paper:")


def test_parse_s2_references():
    refs = _references()
    assert len(refs) == 3
    assert refs[0].arxiv_id == "1409.0473"
    assert refs[0].document_id == "arxiv:1409.0473"
    assert refs[1].document_id == "doi:10.5555/2969033.2969173"
    assert refs[2].document_id.startswith("paper:")  # no external ids


# --------------------------------------------------------------------------- #
# Connector -> Document
# --------------------------------------------------------------------------- #


def test_paper_connector_is_registered():
    assert is_registered("paper")
    assert isinstance(get_connector("paper"), PaperConnector)


def test_connector_parse_produces_valid_paper_document():
    connector = _connector_with_refs()
    ref = next(iter(connector.discover(ARXIV_ID)))
    raw = connector.fetch(ref)
    docs = connector.parse(raw)

    assert len(docs) == 1
    payload = docs[0].to_dict()
    DocumentIngestValidator().validate_document(payload)  # contract-valid
    assert payload["source_type"] == "paper"
    assert payload["document_id"] == "arxiv:1706.03762"
    assert payload["content_ref"].endswith("pdf") or "pdf" in payload["content_ref"]
    assert payload["metadata"]["reference_count"] == 3
    assert payload["metadata"]["arxiv_id"] == "1706.03762"
    assert "arxiv:1409.0473" in payload["metadata"]["reference_ids"]


def test_connector_harvest_yields_documents():
    connector = _connector_with_refs()
    docs = list(connector.harvest(ARXIV_ID))
    assert len(docs) == 1
    assert docs[0].title == "Attention Is All You Need"


# --------------------------------------------------------------------------- #
# Citation graph (exit criterion)
# --------------------------------------------------------------------------- #


def test_ingest_to_kg_creates_cites_edges():
    connector = _connector_with_refs()
    store = KnowledgeGraphStore()

    paper_node = connector.ingest_to_kg(store, ARXIV_ID)

    assert paper_node.node_id == "arxiv:1706.03762"
    assert paper_node.type == EntityType.DOCUMENT

    # Exit criterion: references appear as CITES edges from the paper.
    cites = store.triples(subject=paper_node.node_id, predicate=RelationType.CITES)
    assert len(cites) == 3
    cited_ids = {t.object for t in cites}
    assert "arxiv:1409.0473" in cited_ids
    assert "doi:10.5555/2969033.2969173" in cited_ids

    # Every CITES edge is cited back to the paper (provenance).
    for t in cites:
        assert t.provenance.source_doc == paper_node.node_id

    # Authors became AUTHORED_BY edges to Person nodes.
    authored = store.triples(subject=paper_node.node_id, predicate=RelationType.AUTHORED_BY)
    assert len(authored) == 8
    assert len(store.nodes_by_type(EntityType.PERSON)) == 8
    # Cited works plus the paper are Document nodes.
    assert len(store.nodes_by_type(EntityType.DOCUMENT)) == 4


def test_citation_graph_ignores_self_citation():
    meta = PaperMetadata(title="Self", arxiv_id="9999.99999")
    meta.references = [Reference(title="Self", arxiv_id="9999.99999")]  # cites itself
    store = KnowledgeGraphStore()
    from src.ingestion.connectors.paper import build_citation_graph

    node = build_citation_graph(store, meta)
    assert store.triples(subject=node.node_id, predicate=RelationType.CITES) == []


# --------------------------------------------------------------------------- #
# PDF section splitting (pure, no PDF backend needed)
# --------------------------------------------------------------------------- #


def test_split_sections_recognizes_headings():
    text = "title line\nAbstract\nwe present\n1. Introduction\nbackground here\nReferences\n[1] foo"
    sections = split_sections(text)
    headings = [s.heading for s in sections]
    assert "abstract" in headings
    assert "introduction" in headings
    assert "references" in headings


def test_parse_pdf_extracts_text_or_degrades_gracefully():
    # parse_pdf uses PyMuPDF (fitz) when installed and returns extractor="none"
    # when it is not. Build a real, valid PDF so the installed backend has
    # something parseable rather than malformed bytes (which fitz rejects).
    try:
        import fitz  # PyMuPDF
    except ImportError:
        # Backend absent -> graceful degradation to an empty, no-crash parse.
        parsed = parse_pdf(b"%PDF-1.4 not really a pdf")
        assert parsed.extractor == "none"
        assert parsed.text == ""
        return

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Abstract\nwe present a method.\nReferences\n[1] foo")
    pdf_bytes = doc.tobytes()
    doc.close()

    parsed = parse_pdf(pdf_bytes)
    assert parsed.extractor == "pymupdf"
    assert "Abstract" in parsed.text
    assert "abstract" in [s.heading for s in parsed.sections]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
