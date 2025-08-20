"""
AI-Powered Article Summarization Module

This module provides AI-powered summarization capabilities using state-of-the-art
transformer models like BART, Pegasus, and T5. It supports generating summaries
of different lengths (short, medium, long) and handles various article types.

Features:
- Multiple summarization models (BART, Pegasus, T5)
- Three summary lengths (short, medium, long)
- Batch processing for efficiency
- Caching and storage integration
- Error handling and fallbacks
- Performance metrics

Author: NeuroNews Development Team
Created: August 2025
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

import nltk
import torch
from nltk.tokenize import sent_tokenize, word_tokenize
from transformers import (
    AutoModelForSeq2SeqLM,
    AutoTokenizer,
    BartForConditionalGeneration,
    BartTokenizer,
    PegasusForConditionalGeneration,
    PegasusTokenizer,
    T5ForConditionalGeneration,
    T5Tokenizer,
    pipeline,
)

# Download required NLTK data
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt")

logger = logging.getLogger(__name__)


class SummaryLength(Enum):
    """Enumeration for different summary lengths."""

    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class SummarizationModel(Enum):
    """Enumeration for available summarization models."""

    BART = "facebook/bart-large-cnn"
    PEGASUS = "google/pegasus-cnn_dailymail"
    T5 = "t5-small"
    DISTILBART = "sshleifer/distilbart-cnn-12-6"  # Lighter version


@dataclass
class SummaryConfig:
    """Configuration for summary generation."""

    model: SummarizationModel
    max_length: int
    min_length: int
    length_penalty: float = 2.0
    num_beams: int = 4
    early_stopping: bool = True
    no_repeat_ngram_size: int = 3


@dataclass
class Summary:
    """Data class representing a generated summary."""

    text: str
    length: SummaryLength
    model: SummarizationModel
    confidence_score: float
    processing_time: float
    word_count: int
    sentence_count: int
    compression_ratio: float
    created_at: str


class AIArticleSummarizer:
    """
    Advanced AI-powered article summarization system.

    This class provides comprehensive summarization capabilities using multiple
    state-of-the-art transformer models with support for different summary lengths
    and advanced configuration options.
    """

    def __init__(
        self,
        default_model: SummarizationModel = SummarizationModel.DISTILBART,
        device: Optional[str] = None,
        enable_caching: bool = True,
    ):
        """
        Initialize the AI Article Summarizer.

        Args:
            default_model: Default model to use for summarization
            device: Device to run models on ('cpu', 'cuda', or auto-detect)
            enable_caching: Whether to enable model caching
        """
        self.default_model = default_model
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.enable_caching = enable_caching

        # Model cache
        self._models: Dict[SummarizationModel, Tuple] = {}
        self._tokenizers: Dict[SummarizationModel, object] = {}

        # Summary configurations for different lengths
        self.configs = {
            SummaryLength.SHORT: SummaryConfig(
                model=default_model,
                max_length=50,
                min_length=20,
                length_penalty=2.0,
                num_beams=4,
            ),
            SummaryLength.MEDIUM: SummaryConfig(
                model=default_model,
                max_length=150,
                min_length=50,
                length_penalty=1.5,
                num_beams=4,
            ),
            SummaryLength.LONG: SummaryConfig(
                model=default_model,
                max_length=300,
                min_length=100,
                length_penalty=1.0,
                num_beams=6,
            ),
        }

        # Performance metrics
        self.metrics = {
            "total_summaries": 0,
            "total_processing_time": 0.0,
            "average_processing_time": 0.0,
            "model_usage_count": {model: 0 for model in SummarizationModel},
        }

        logger.info(
            "AIArticleSummarizer initialized with device: {0}".format(
                self.device)
        )

    def _load_model(self, model_type: SummarizationModel) -> Tuple:
        """
        Load and cache a summarization model.

        Args:
            model_type: Type of model to load

        Returns:
            Tuple of (model, tokenizer)
        """
        if model_type in self._models and self.enable_caching:
            return self._models[model_type]

        logger.info("Loading model: {0}".format(model_type.value))
        start_time = time.time()

        try:
            if model_type == SummarizationModel.BART:
                tokenizer = BartTokenizer.from_pretrained(model_type.value)
                model = BartForConditionalGeneration.from_pretrained(model_type.value)
            elif model_type == SummarizationModel.PEGASUS:
                tokenizer = PegasusTokenizer.from_pretrained(model_type.value)
                model = PegasusForConditionalGeneration.from_pretrained(
                    model_type.value
                )
            elif model_type == SummarizationModel.T5:
                tokenizer = T5Tokenizer.from_pretrained(model_type.value)
                model = T5ForConditionalGeneration.from_pretrained(model_type.value)
            elif model_type == SummarizationModel.DISTILBART:
                tokenizer = AutoTokenizer.from_pretrained(model_type.value)
                model = AutoModelForSeq2SeqLM.from_pretrained(model_type.value)
            else:
                raise ValueError("Unsupported model type: {0}".format(model_type))

            # Move model to device
            model = model.to(self.device)
            model.eval()  # Set to evaluation mode

            load_time = time.time() - start_time
            logger.info("Model {0} loaded in {1}s".format(model_type.value, load_time))

            if self.enable_caching:
                self._models[model_type] = (model, tokenizer)

            return model, tokenizer

        except Exception as e:
            logger.error("Failed to load model {0}: {1}".format(model_type.value, str(e)))
            raise

    def _preprocess_text(self, text: str) -> str:
        """
        Preprocess text for summarization.

        Args:
            text: Raw text to preprocess

        Returns:
            Cleaned and preprocessed text
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # Basic cleaning
        text = text.strip()

        # Remove excessive whitespace
        text = " ".join(text.split())

        # Ensure text ends with proper punctuation
        if text and text[-1] not in ".!?":
            text += "."

        return text

    def _calculate_metrics(
        self, original_text: str, summary_text: str, processing_time: float
    ) -> Dict[str, float]:
        """
        Calculate summary quality metrics.

        Args:
            original_text: Original article text
            summary_text: Generated summary text
            processing_time: Time taken to generate summary

        Returns:
            Dictionary of metrics
        """
        original_words = len(word_tokenize(original_text))
        summary_words = len(word_tokenize(summary_text))
        len(sent_tokenize(original_text))
        summary_sentences = len(sent_tokenize(summary_text))

        compression_ratio = summary_words / original_words if original_words > 0 else 0

        # Simple confidence score based on text properties
        confidence_score = min(
            0.95,
            # Prefer ~20% compression
            max(0.1, 0.8 - abs(compression_ratio - 0.2) * 2),
        )

        return {
            "word_count": summary_words,
            "sentence_count": summary_sentences,
            "compression_ratio": compression_ratio,
            "confidence_score": confidence_score,
            "processing_time": processing_time,
        }

    async def summarize_article(
        self,
        text: str,
        length: SummaryLength = SummaryLength.MEDIUM,
        model: Optional[SummarizationModel] = None,
    ) -> Summary:
        """
        Generate a summary for an article.

        Args:
            text: Article text to summarize
            length: Desired length of summary
            model: Specific model to use (optional)

        Returns:
            Generated Summary object
        """
        start_time = time.time()

        try:
            # Preprocess text
            clean_text = self._preprocess_text(text)

            # Use specified model or default from config
            model_type = model or self.configs[length].model
            config = self.configs[length]

            # Load model
            model_obj, tokenizer = self._load_model(model_type)

            # Prepare text for model
            if model_type == SummarizationModel.T5:
                input_text = "summarize: {0}".format(clean_text)
            else:
                input_text = clean_text

            # Tokenize input
            inputs = tokenizer.encode(
                input_text, return_tensors="pt", max_length=1024, truncation=True
            ).to(self.device)

            # Generate summary
            with torch.no_grad():
                summary_ids = model_obj.generate(
                    inputs,
                    max_length=config.max_length,
                    min_length=config.min_length,
                    length_penalty=config.length_penalty,
                    num_beams=config.num_beams,
                    early_stopping=config.early_stopping,
                    no_repeat_ngram_size=config.no_repeat_ngram_size,
                    do_sample=False,
                )

            # Decode summary
            summary_text = tokenizer.decode(summary_ids[0], skip_special_tokens=True)

            processing_time = time.time() - start_time

            # Calculate metrics
            metrics = self._calculate_metrics(clean_text, summary_text, processing_time)

            # Update global metrics
            self.metrics["total_summaries"] += 1
            self.metrics["total_processing_time"] += processing_time
            self.metrics["average_processing_time"] = (
                self.metrics["total_processing_time"] / self.metrics["total_summaries"]
            )
            self.metrics["model_usage_count"][model_type] += 1

            # Create summary object
            summary = Summary(
                text=summary_text,
                length=length,
                model=model_type,
                confidence_score=metrics["confidence_score"],
                processing_time=processing_time,
                word_count=metrics["word_count"],
                sentence_count=metrics["sentence_count"],
                compression_ratio=metrics["compression_ratio"],
                created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )

            logger.info(
                f"Summary generated: {
                    length.value} ({
                    metrics['word_count']} words, "
                "{0}s)".format(
                    processing_time:.2f)
            )

            return summary

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                "Summarization failed after {0}s: {1}".format(
                    processing_time:.2f, 
                    str(e))
            )
            raise

    async def summarize_article_all_lengths(
        self, text: str, model: Optional[SummarizationModel] = None
    ) -> Dict[SummaryLength, Summary]:
        """
        Generate summaries of all lengths for an article.

        Args:
            text: Article text to summarize
            model: Specific model to use (optional)

        Returns:
            Dictionary mapping length to Summary objects
        """
        tasks = []
        for length in SummaryLength:
            task = self.summarize_article(text, length, model)
            tasks.append(task)

        summaries = await asyncio.gather(*tasks)

        return {
            SummaryLength.SHORT: summaries[0],
            SummaryLength.MEDIUM: summaries[1],
            SummaryLength.LONG: summaries[2],
        }

    def get_model_info(self) -> Dict:
        """
        Get information about loaded models and performance metrics.

        Returns:
            Dictionary with model information and metrics
        """
        return {
            "loaded_models": list(self._models.keys()),
            "default_model": self.default_model,
            "device": self.device,
            "metrics": self.metrics,
            "configs": {
                length.value: {
                    "max_length": config.max_length,
                    "min_length": config.min_length,
                    "model": config.model.value,
                }
                for length, config in self.configs.items()
            },
        }

    def clear_cache(self):
        """Clear model cache to free memory."""
        self._models.clear()
        self._tokenizers.clear()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.info("Model cache cleared")


# Utility functions for integration
def create_summary_hash(
    text: str, length: SummaryLength, model: SummarizationModel
) -> str:
    """
    Create a hash for caching summaries.

    Args:
        text: Original text
        length: Summary length
        model: Model used

    Returns:
        SHA256 hash string
    """
    content = "{0}{1}{2}".format(text, length.value, model.value)
    return hashlib.sha256(content.encode()).hexdigest()


def get_summary_pipeline(model_name: str = "facebook/bart-large-cnn"):
    """
    Get a simple summarization pipeline for quick usage.

    Args:
        model_name: Name of the model to use

    Returns:
        Hugging Face summarization pipeline
    """
    device = 0 if torch.cuda.is_available() else -1
    return pipeline("summarization", model=model_name, device=device)


# Example usage and testing
async def demo_summarization():
    """Demo function showing how to use the summarizer."""
    sample_text = """
    Artificial intelligence (AI) is intelligence demonstrated by machines, in contrast to the natural intelligence displayed by humans and animals. Leading AI textbooks define the field as the study of "intelligent agents": any device that perceives its environment and takes actions that maximize its chance of successfully achieving its goals. Colloquially, the term "artificial intelligence" is often used to describe machines that mimic "cognitive" functions that humans associate with the human mind, such as "learning" and "problem solving".

    The scope of AI is disputed: as machines become increasingly capable, tasks considered to require "intelligence" are often removed from the definition of AI, a phenomenon known as the AI effect. A quip in Tesler's Theorem says "AI is whatever hasn't been done yet." For instance, optical character recognition is frequently excluded from things considered to be AI, having become a routine technology. Modern machine learning capabilities are typically considered AI.

    Artificial intelligence was founded as an academic discipline in 1956, and in the years since has experienced several waves of optimism, followed by disappointment and the loss of funding (known as an "AI winter"), followed by new approaches, success and renewed funding. AI research has tried many different approaches, but no single approach has been successful for all problems. Research in AI has focused on the following areas: reasoning, knowledge representation, planning, learning, natural language processing, perception, and the ability to move and manipulate objects.
    """

    summarizer = AIArticleSummarizer()

    print("Generating summaries...")
    summaries = await summarizer.summarize_article_all_lengths(sample_text)

    for length, summary in summaries.items():
        print("\n{0} SUMMARY:".format(length.value.upper()))
        print("Text: {0}".format(summary.text))
        print(
            "Words: {0}, Compression: {1}".format(
                summary.word_count, 
                summary.compression_ratio:.2%)
        )
        print("Processing time: {0}s".format(summary.processing_time))


if __name__ == "__main__":
    # Run demo
    asyncio.run(demo_summarization())
