"""
Tests for structure-aware chunking (#518).

Verifies the new STRUCTURED strategy tags each chunk with its section/chapter
path (so RAG can cite a location), supports hierarchical trees, integrates with
the paper PDF section splitter, and keeps the existing flat strategies
backward compatible.
"""

import importlib.util
from pathlib import Path

import pytest

# Load chunking.py in isolation. The services.rag package __init__ eagerly
# imports the full RAG stack (numpy, psycopg2, qdrant, ...), which this
# stdlib-only chunking module does not need; loading the file directly keeps
# this a true unit test.
_CHUNKING_PATH = Path(__file__).resolve().parents[2] / "services" / "rag" / "chunking.py"
_spec = importlib.util.spec_from_file_location("rag_chunking_standalone", _CHUNKING_PATH)
chunking = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chunking)

ChunkConfig = chunking.ChunkConfig
DocumentSection = chunking.DocumentSection
SplitStrategy = chunking.SplitStrategy
TextChunk = chunking.TextChunk
TextChunker = chunking.TextChunker
chunk_document = chunking.chunk_document
chunk_text = chunking.chunk_text


# --------------------------------------------------------------------------- #
# Backward compatibility
# --------------------------------------------------------------------------- #


def test_flat_chunking_still_works_and_path_is_empty():
    text = "This is the first sentence. Here is a second, somewhat longer sentence."
    chunks = chunk_text(text, max_chars=1000, split_on="sentence")
    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk["path"] == []  # flat chunks carry no section path


def test_textchunk_path_defaults_empty():
    chunk = TextChunk(
        text="x", start_offset=0, end_offset=1, chunk_id=0,
        word_count=1, char_count=1, metadata={},
    )
    assert chunk.path == []
    assert chunk.to_dict()["path"] == []


# --------------------------------------------------------------------------- #
# Structured chunking
# --------------------------------------------------------------------------- #


def test_structured_chunks_carry_section_path():
    sections = DocumentSection.from_pairs([
        ("1 Introduction", "We introduce the problem. It matters for many reasons across fields."),
        ("4.2 Methods", "We use a transformer model. The attention mechanism is central to it."),
    ])
    chunks = chunk_document(sections, max_chars=1000)

    methods = [c for c in chunks if c["path"] == ["4.2 Methods"]]
    assert methods, "expected a chunk located at section 4.2 Methods"
    assert "transformer" in methods[0]["text"].lower()
    assert methods[0]["metadata"]["chunk_strategy"] == "structured"
    assert methods[0]["metadata"]["section_path"] == ["4.2 Methods"]
    # chunk ids are sequential across the whole document
    assert [c["chunk_id"] for c in chunks] == list(range(len(chunks)))


def test_structured_hierarchical_path_breadcrumb():
    tree = [
        DocumentSection("Part II", "", children=[
            DocumentSection("Chapter 5", "", children=[
                DocumentSection(
                    "5.1 Overview",
                    "This section explains the core idea. It spans several sentences for chunking.",
                ),
            ]),
        ]),
    ]
    chunker = TextChunker(ChunkConfig(split_on=SplitStrategy.STRUCTURED, min_chunk_chars=10))
    chunks = chunker.chunk_document(tree)

    assert chunks, "expected chunks from the leaf section"
    for chunk in chunks:
        assert chunk.path == ["Part II", "Chapter 5", "5.1 Overview"]


def test_container_sections_without_body_produce_no_chunks():
    tree = [DocumentSection("Empty Part", "", children=[DocumentSection("Heading only", "")])]
    chunker = TextChunker(ChunkConfig(split_on=SplitStrategy.STRUCTURED, min_chunk_chars=10))
    assert chunker.chunk_document(tree) == []


def test_structured_string_fallback_treats_text_as_one_section():
    # Plain string through the STRUCTURED strategy still yields chunks.
    chunker = TextChunker(ChunkConfig(split_on=SplitStrategy.STRUCTURED, min_chunk_chars=10))
    chunks = chunker.chunk_text("A standalone passage. With two sentences to split on here.")
    assert chunks
    assert all(c.path == [] for c in chunks)  # untitled root -> empty path


def test_leaf_split_on_paragraph():
    section = DocumentSection("Body", "Para one is here.\n\nPara two follows after a blank line.")
    chunks = chunk_document([section], max_chars=1000, leaf_split_on="paragraph")
    assert chunks
    assert all(c["path"] == ["Body"] for c in chunks)


# --------------------------------------------------------------------------- #
# Integration with the paper PDF section splitter (#517)
# --------------------------------------------------------------------------- #


def test_structured_chunking_over_paper_sections():
    from src.ingestion.connectors.paper.pdf_parser import split_sections

    paper_text = (
        "title preamble\n"
        "Abstract\nWe present a new approach to sequence modeling that is simple and effective.\n"
        "Introduction\nRecurrent models dominate but are slow to train on long sequences.\n"
        "Methods\nWe use a transformer. The attention mechanism replaces recurrence entirely.\n"
        "References\n[1] Some cited work."
    )
    sections = [DocumentSection(s.heading, s.body) for s in split_sections(paper_text)]
    chunks = chunk_document(sections, max_chars=1000)

    paths = {tuple(c["path"]) for c in chunks}
    assert ("methods",) in paths
    methods_chunk = next(c for c in chunks if c["path"] == ["methods"])
    assert "attention" in methods_chunk["text"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
