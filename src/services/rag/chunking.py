"""
Text Chunking Module
Issue #229: Chunking & normalization pipeline

This module handles the chunking of normalized articles into appropriately sized chunks
with configurable parameters like max_chars, overlap, and language-aware splitting.
"""

import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

try:
    import spacy
    from spacy.lang.en import English
except ImportError:
    spacy = None
    English = None

logger = logging.getLogger(__name__)


class SplitStrategy(Enum):
    """Strategies for text splitting."""
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
    WORD = "word"
    CHARACTER = "character"


@dataclass
class ChunkConfig:
    """Configuration for text chunking."""
    max_chars: int = 1000
    overlap_chars: int = 100
    split_on: SplitStrategy = SplitStrategy.SENTENCE
    min_chunk_chars: int = 50
    preserve_sentences: bool = True
    language: str = "en"


@dataclass
class TextChunk:
    """Represents a chunk of text with metadata."""
    text: str
    start_offset: int
    end_offset: int
    chunk_id: int
    word_count: int
    char_count: int
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk to dictionary representation."""
        return {
            'text': self.text,
            'start_offset': self.start_offset,
            'end_offset': self.end_offset,
            'chunk_id': self.chunk_id,
            'word_count': self.word_count,
            'char_count': self.char_count,
            'metadata': self.metadata,
        }


class TextChunker:
    """
    Language-aware text chunker that splits text into appropriately sized chunks.
    
    Features:
    - Configurable chunk size and overlap
    - Language-aware sentence splitting
    - Multiple splitting strategies
    - Metadata preservation
    - Offset tracking for reconstruction
    """
    
    def __init__(self, config: Optional[ChunkConfig] = None):
        """
        Initialize text chunker.
        
        Args:
            config: Chunking configuration
        """
        self.config = config or ChunkConfig()
        
        # Initialize language model for sentence splitting
        self.nlp = None
        if spacy and self.config.preserve_sentences:
            try:
                # Try to load language-specific model
                if self.config.language == "en":
                    self.nlp = English()
                    self.nlp.add_pipe("sentencizer")
                else:
                    # Fallback to English for unsupported languages
                    self.nlp = English()
                    self.nlp.add_pipe("sentencizer")
                    logger.warning(f"Language '{self.config.language}' not supported, using English")
            except Exception as e:
                logger.warning(f"Failed to load spacy model: {e}, using regex fallback")
                self.nlp = None
        
        # Fallback regex patterns for sentence splitting
        self.sentence_endings = re.compile(r'[.!?]+\s+')
        self.paragraph_endings = re.compile(r'\n\s*\n')
        
    def chunk_text(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> List[TextChunk]:
        """
        Chunk text into appropriately sized pieces.
        
        Args:
            text: Text to chunk
            metadata: Optional metadata to include with chunks
            
        Returns:
            List of TextChunk objects
        """
        if not text or not text.strip():
            return []
        
        metadata = metadata or {}
        
        # Choose splitting strategy
        if self.config.split_on == SplitStrategy.SENTENCE:
            return self._chunk_by_sentences(text, metadata)
        elif self.config.split_on == SplitStrategy.PARAGRAPH:
            return self._chunk_by_paragraphs(text, metadata)
        elif self.config.split_on == SplitStrategy.WORD:
            return self._chunk_by_words(text, metadata)
        else:  # CHARACTER
            return self._chunk_by_characters(text, metadata)
    
    def _chunk_by_sentences(self, text: str, metadata: Dict[str, Any]) -> List[TextChunk]:
        """Chunk text by sentences, respecting max_chars and overlap."""
        sentences = self._split_into_sentences(text)
        if not sentences:
            return []
        
        chunks = []
        current_chunk = ""
        current_start = 0
        chunk_id = 0
        
        i = 0
        while i < len(sentences):
            sentence = sentences[i]
            
            # Check if adding this sentence would exceed max_chars
            if current_chunk and len(current_chunk + sentence) > self.config.max_chars:
                # Create chunk from current content
                if len(current_chunk.strip()) >= self.config.min_chunk_chars:
                    chunk = self._create_chunk(
                        current_chunk.strip(), 
                        current_start, 
                        chunk_id, 
                        metadata
                    )
                    chunks.append(chunk)
                    chunk_id += 1
                
                # Start new chunk with overlap
                overlap_sentences = self._get_overlap_sentences(sentences, i, current_chunk)
                current_chunk = overlap_sentences + sentence
                current_start = self._find_text_position(text, overlap_sentences)
            else:
                current_chunk += sentence
                if not current_chunk.strip():  # First sentence
                    current_start = self._find_text_position(text, sentence)
            
            i += 1
        
        # Add final chunk
        if current_chunk.strip() and len(current_chunk.strip()) >= self.config.min_chunk_chars:
            chunk = self._create_chunk(current_chunk.strip(), current_start, chunk_id, metadata)
            chunks.append(chunk)
        
        return chunks
    
    def _chunk_by_paragraphs(self, text: str, metadata: Dict[str, Any]) -> List[TextChunk]:
        """Chunk text by paragraphs."""
        paragraphs = self.paragraph_endings.split(text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        
        chunks = []
        current_chunk = ""
        current_start = 0
        chunk_id = 0
        
        for i, paragraph in enumerate(paragraphs):
            if current_chunk and len(current_chunk + "\n\n" + paragraph) > self.config.max_chars:
                # Create chunk from current content
                if len(current_chunk.strip()) >= self.config.min_chunk_chars:
                    chunk = self._create_chunk(current_chunk.strip(), current_start, chunk_id, metadata)
                    chunks.append(chunk)
                    chunk_id += 1
                
                # Start new chunk
                current_chunk = paragraph
                current_start = self._find_text_position(text, paragraph)
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
                    current_start = self._find_text_position(text, paragraph)
        
        # Add final chunk
        if current_chunk.strip() and len(current_chunk.strip()) >= self.config.min_chunk_chars:
            chunk = self._create_chunk(current_chunk.strip(), current_start, chunk_id, metadata)
            chunks.append(chunk)
        
        return chunks
    
    def _chunk_by_words(self, text: str, metadata: Dict[str, Any]) -> List[TextChunk]:
        """Chunk text by words."""
        words = text.split()
        if not words:
            return []
        
        chunks = []
        chunk_id = 0
        
        i = 0
        while i < len(words):
            current_words = []
            current_length = 0
            
            # Build chunk up to max_chars
            while i < len(words) and current_length < self.config.max_chars:
                word = words[i]
                if current_length + len(word) + 1 <= self.config.max_chars:  # +1 for space
                    current_words.append(word)
                    current_length += len(word) + (1 if current_words else 0)
                    i += 1
                else:
                    break
            
            if current_words:
                chunk_text = " ".join(current_words)
                if len(chunk_text) >= self.config.min_chunk_chars:
                    start_pos = self._find_text_position(text, chunk_text)
                    chunk = self._create_chunk(chunk_text, start_pos, chunk_id, metadata)
                    chunks.append(chunk)
                    chunk_id += 1
                
                # Calculate overlap
                overlap_words = max(0, len(current_words) * self.config.overlap_chars // self.config.max_chars)
                i -= overlap_words
        
        return chunks
    
    def _chunk_by_characters(self, text: str, metadata: Dict[str, Any]) -> List[TextChunk]:
        """Chunk text by character count."""
        chunks = []
        chunk_id = 0
        
        i = 0
        while i < len(text):
            chunk_end = min(i + self.config.max_chars, len(text))
            chunk_text = text[i:chunk_end].strip()
            
            if len(chunk_text) >= self.config.min_chunk_chars:
                chunk = self._create_chunk(chunk_text, i, chunk_id, metadata)
                chunks.append(chunk)
                chunk_id += 1
            
            # Move forward with overlap
            i += self.config.max_chars - self.config.overlap_chars
        
        return chunks
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences using spacy or regex fallback."""
        if self.nlp:
            try:
                doc = self.nlp(text)
                return [sent.text + " " for sent in doc.sents]
            except Exception as e:
                logger.warning(f"Spacy sentence splitting failed: {e}, using regex")
        
        # Regex fallback
        sentences = self.sentence_endings.split(text)
        sentences = [s.strip() + ". " for s in sentences if s.strip()]
        return sentences
    
    def _get_overlap_sentences(self, sentences: List[str], current_index: int, current_chunk: str) -> str:
        """Get sentences for overlap based on overlap_chars."""
        if self.config.overlap_chars == 0:
            return ""
        
        # Calculate how many sentences to include for overlap
        overlap_length = 0
        overlap_sentences = []
        
        # Work backwards from current position
        for i in range(current_index - 1, -1, -1):
            sentence = sentences[i]
            if overlap_length + len(sentence) <= self.config.overlap_chars:
                overlap_sentences.insert(0, sentence)
                overlap_length += len(sentence)
            else:
                break
        
        return "".join(overlap_sentences)
    
    def _find_text_position(self, full_text: str, chunk_text: str) -> int:
        """Find the start position of chunk_text in full_text."""
        # Clean up the texts for matching
        chunk_clean = chunk_text.strip()
        if len(chunk_clean) < 10:  # Too short to reliably find
            return 0
            
        # Try to find the chunk text in the full text
        pos = full_text.find(chunk_clean[:50])  # Use first 50 chars for matching
        return max(0, pos)
    
    def _create_chunk(self, text: str, start_offset: int, chunk_id: int, metadata: Dict[str, Any]) -> TextChunk:
        """Create a TextChunk object."""
        word_count = len(text.split())
        char_count = len(text)
        end_offset = start_offset + char_count
        
        chunk_metadata = metadata.copy()
        chunk_metadata.update({
            'chunk_strategy': self.config.split_on.value,
            'max_chars': self.config.max_chars,
            'overlap_chars': self.config.overlap_chars,
        })
        
        return TextChunk(
            text=text,
            start_offset=start_offset,
            end_offset=end_offset,
            chunk_id=chunk_id,
            word_count=word_count,
            char_count=char_count,
            metadata=chunk_metadata,
        )


def chunk_text(
    text: str,
    max_chars: int = 1000,
    overlap_chars: int = 100,
    split_on: str = "sentence",
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Convenience function to chunk text.
    
    Args:
        text: Text to chunk
        max_chars: Maximum characters per chunk
        overlap_chars: Overlap between chunks
        split_on: Splitting strategy ("sentence", "paragraph", "word", "character")
        metadata: Optional metadata to include
        **kwargs: Additional configuration options
        
    Returns:
        List of chunk dictionaries
    """
    # Set reasonable defaults for convenience function
    config_kwargs = {
        'min_chunk_chars': kwargs.pop('min_chunk_chars', 10),  # Lower default
        **kwargs
    }
    
    config = ChunkConfig(
        max_chars=max_chars,
        overlap_chars=overlap_chars,
        split_on=SplitStrategy(split_on),
        **config_kwargs
    )
    
    chunker = TextChunker(config)
    chunks = chunker.chunk_text(text, metadata)
    
    return [chunk.to_dict() for chunk in chunks]
