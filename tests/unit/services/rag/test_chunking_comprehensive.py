"""Comprehensive tests for services/rag/chunking.py."""

import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.rag.chunking import (  # noqa: E402
    ChunkConfig,
    SplitStrategy,
    TextChunk,
    TextChunker,
    chunk_text,
)


class TestEnumAndConfig:
    def test_strategies(self):
        assert SplitStrategy.SENTENCE.value == "sentence"
        assert SplitStrategy.CHARACTER.value == "character"

    def test_config_defaults(self):
        c = ChunkConfig()
        assert c.max_chars == 1000
        assert c.overlap_chars == 100
        assert c.split_on == SplitStrategy.SENTENCE


class TestTextChunk:
    def test_to_dict(self):
        chunk = TextChunk(
            text="hello world", start_offset=0, end_offset=11, chunk_id=0,
            word_count=2, char_count=11, metadata={"k": "v"},
        )
        d = chunk.to_dict()
        assert d["text"] == "hello world"
        assert d["word_count"] == 2
        assert d["metadata"] == {"k": "v"}


def chunker(strategy=SplitStrategy.SENTENCE, **over):
    cfg = ChunkConfig(split_on=strategy, preserve_sentences=False, **over)
    return TextChunker(cfg)


class TestChunkText:
    def test_empty(self):
        assert chunker().chunk_text("") == []
        assert chunker().chunk_text("   ") == []

    def test_sentence_chunks(self):
        text = "First sentence here. Second sentence follows. Third one too. " * 20
        chunks = chunker(max_chars=200, min_chunk_chars=10).chunk_text(text)
        assert len(chunks) > 1
        assert all(isinstance(c, TextChunk) for c in chunks)
        assert all(c.char_count > 0 for c in chunks)

    def test_paragraph_chunks(self):
        text = "Para one with text.\n\nPara two with more.\n\nPara three is here."
        chunks = chunker(SplitStrategy.PARAGRAPH, max_chars=100, min_chunk_chars=5).chunk_text(text)
        assert len(chunks) >= 1

    def test_word_chunks(self):
        text = " ".join(f"word{i}" for i in range(200))
        chunks = chunker(SplitStrategy.WORD, max_chars=100, min_chunk_chars=10).chunk_text(text)
        assert len(chunks) > 1
        for c in chunks:
            assert c.char_count <= 100 + 50  # roughly bounded

    def test_character_chunks(self):
        text = "abcdefghij" * 50  # 500 chars
        chunks = chunker(SplitStrategy.CHARACTER, max_chars=100, overlap_chars=0,
                         min_chunk_chars=10).chunk_text(text)
        assert len(chunks) >= 5
        assert chunks[0].char_count <= 100

    def test_metadata_propagated(self):
        chunks = chunker(max_chars=100, min_chunk_chars=5).chunk_text(
            "A sentence here. Another sentence there.", metadata={"doc": "d1"}
        )
        assert chunks
        assert all(c.metadata.get("doc") == "d1" for c in chunks)


class TestSentenceSplitting:
    def test_split_into_sentences(self):
        ch = chunker()
        sentences = ch._split_into_sentences("One. Two! Three? Four.")
        assert len(sentences) >= 3

    def test_chunk_ids_sequential(self):
        text = "Sentence number one here. " * 50
        chunks = chunker(max_chars=100, min_chunk_chars=10).chunk_text(text)
        ids = [c.chunk_id for c in chunks]
        assert ids == list(range(len(chunks)))


class TestConvenienceFunction:
    def test_chunk_text_function(self):
        result = chunk_text(
            "First. Second. Third.", max_chars=100, preserve_sentences=False
        )
        assert isinstance(result, list)
