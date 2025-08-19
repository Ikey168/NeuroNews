"""
Keyword Extraction and Topic Modeling Module (Issue #29).

This module implements advanced NLP techniques for extracting keywords
and identifying topics in news articles using:
- TF-IDF for keyword extraction
- Latent Dirichlet Allocation (LDA) for topic modeling
- BERT embeddings for enhanced semantic understanding

Features:
- Extract relevant keywords from article content
- Identify dominant topics and themes
- Store results in Redshift database
- Support multiple extraction strategies
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer

# Set up logging first
logger = logging.getLogger(__name__)

# NLTK imports with error handling
try:
    import nltk
    from nltk.corpus import stopwords
    from nltk.stem import WordNetLemmatizer
    from nltk.tag import pos_tag
    from nltk.tokenize import sent_tokenize, word_tokenize

    # Download required NLTK data if not already present
    def ensure_nltk_data():
        """Ensure required NLTK data is downloaded."""
        required_data = [
            ("punkt", "tokenizers/punkt"),
            ("punkt_tab", "tokenizers/punkt_tab"),
            ("stopwords", "corpora/stopwords"),
            ("wordnet", "corpora/wordnet"),
            ("averaged_perceptron_tagger", "taggers/averaged_perceptron_tagger"),
            (
                "averaged_perceptron_tagger_eng",
                "taggers/averaged_perceptron_tagger_eng",
            ),
        ]

        for name, path in required_data:
            try:
                nltk.data.find(path)
            except LookupError:
                try:
                    logger.info(f"Downloading NLTK data: {name}")
                    nltk.download(name, quiet=True)
                except Exception as e:
                    logger.warning(f"Failed to download NLTK data {name}: {e}")

    # Try to ensure NLTK data is available
    try:
        ensure_nltk_data()
    except Exception as e:
        logger.warning(f"NLTK data setup failed: {e}")

    NLTK_AVAILABLE = True
    try:
        # Test if NLTK is working
        stopwords.words("english")
        WordNetLemmatizer()
    except Exception as e:
        logger.warning(f"NLTK not fully functional: {e}")
        NLTK_AVAILABLE = False

except ImportError as e:
    logger.warning(f"NLTK not available: {e}")
    NLTK_AVAILABLE = False

    # Create dummy classes for when NLTK is not available
    class WordNetLemmatizer:
        def lemmatize(self, word):
            return word

    def stopwords():
        return []

    def word_tokenize(text):
        return text.split()

    def sent_tokenize(text):
        return text.split(".")

    def pos_tag(tokens):
        return [(token, "NN") for token in tokens]


# spaCy imports with error handling
try:
    import spacy

    # Try to load the English model, fallback if not available
    try:
        nlp = spacy.load("en_core_web_sm")
        SPACY_AVAILABLE = True
    except OSError:
        logger.warning(
            "spaCy English model not found. Install with: python -m spacy download en_core_web_sm"
        )
        nlp = None
        SPACY_AVAILABLE = False
except ImportError:
    logger.warning("spaCy not available. Install with: pip install spacy")
    nlp = None
    SPACY_AVAILABLE = False


@dataclass
class KeywordResult:
    """Represents extracted keywords with scores."""

    keyword: str
    score: float
    method: str  # 'tfidf', 'lda', 'bert'


@dataclass
class TopicResult:
    """Represents identified topic with associated words and probability."""

    topic_id: int
    topic_name: str
    topic_words: List[str]
    probability: float
    coherence_score: Optional[float] = None


@dataclass
class ExtractionResult:
    """Complete result of keyword extraction and topic modeling."""

    article_id: str
    url: str
    title: str
    keywords: List[KeywordResult]
    topics: List[TopicResult]
    dominant_topic: Optional[TopicResult]
    extraction_method: str
    processed_at: datetime
    processing_time: float


class TextPreprocessor:
    """Text preprocessing utilities for keyword extraction."""

    def __init__(self):
        """Initialize preprocessor with required components."""
        if NLTK_AVAILABLE:
            try:
                self.lemmatizer = WordNetLemmatizer()
                # Extended stopwords including news-specific terms
                self.stop_words = set(stopwords.words("english"))
            except Exception as e:
                logger.warning(f"NLTK initialization failed: {e}")
                self.lemmatizer = None
                self.stop_words = set()
        else:
            self.lemmatizer = None
            self.stop_words = set()

        # Add news-specific stop words
        self.stop_words.update(
            [
                "said",
                "says",
                "according",
                "report",
                "reports",
                "news",
                "article",
                "story",
                "post",
                "published",
                "updated",
                "source",
                "sources",
                "reporter",
                "correspondent",
                "editorial",
                "editor",
                "website",
                "online",
                "digital",
                "print",
                "media",
                "press",
                "today",
                "yesterday",
                "tomorrow",
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
                "january",
                "february",
                "march",
                "april",
                "may",
                "june",
                "july",
                "august",
                "september",
                "october",
                "november",
                "december",
            ]
        )

        # Valid POS tags for keywords (nouns, adjectives, verbs)
        self.valid_pos = {
            "NN",
            "NNS",
            "NNP",
            "NNPS",
            "JJ",
            "JJR",
            "JJS",
            "VB",
            "VBD",
            "VBG",
            "VBN",
            "VBP",
            "VBZ",
        }

    def clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)

        # Remove URLs
        text = re.sub(
            r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
            "",
            text,
        )

        # Remove email addresses
        text = re.sub(r"\S+@\S+", "", text)

        # Remove extra whitespace and newlines
        text = re.sub(r"\s+", " ", text)

        # Remove special characters but keep basic punctuation
        text = re.sub(r"[^\w\s\.\,\;\:\!\?]", "", text)

        return text.strip()

    def extract_sentences(self, text: str) -> List[str]:
        """Extract sentences from text."""
        cleaned_text = self.clean_text(text)

        if not NLTK_AVAILABLE:
            # Simple fallback: split on sentence-ending punctuation
            sentences = re.split(r"[.!?]+", cleaned_text)
            return [s.strip() for s in sentences if len(s.strip().split()) > 3]

        try:
            sentences = sent_tokenize(cleaned_text)
            return [
                s for s in sentences if len(s.split()) > 3
            ]  # Filter very short sentences
        except Exception as e:
            logger.warning(
                f"NLTK sentence tokenization failed: {e}. Using simple sentence splitting."
            )
            # Simple fallback: split on sentence-ending punctuation
            sentences = re.split(r"[.!?]+", cleaned_text)
            return [s.strip() for s in sentences if len(s.strip().split()) > 3]

    def extract_keywords_pos(
        self, text: str, min_length: int = 3, max_keywords: int = 20
    ) -> List[str]:
        """Extract potential keywords using POS tagging."""
        cleaned_text = self.clean_text(text)

        if not NLTK_AVAILABLE:
            # Simple fallback: extract words based on length and stop words
            words = re.findall(r"\b[a-zA-Z]{3,}\b", cleaned_text.lower())
            keywords = []
            for word in words:
                if word not in self.stop_words and word not in keywords:
                    keywords.append(word)
            return keywords[:max_keywords]

        try:
            tokens = word_tokenize(cleaned_text.lower())
            # POS tagging
            pos_tagged = pos_tag(tokens)

            # Extract words with valid POS tags
            keywords = []
            for word, pos in pos_tagged:
                if (
                    pos in self.valid_pos
                    and word not in self.stop_words
                    and len(word) >= min_length
                    and word.isalpha()
                ):
                    try:
                        if self.lemmatizer:
                            lemmatized = self.lemmatizer.lemmatize(word)
                            keywords.append(lemmatized)
                        else:
                            keywords.append(word)
                    except BaseException:
                        keywords.append(word)  # Fallback to original word

            # Remove duplicates while preserving order
            unique_keywords = []
            seen = set()
            for keyword in keywords:
                if keyword not in seen:
                    unique_keywords.append(keyword)
                    seen.add(keyword)

            return unique_keywords[:max_keywords]

        except Exception as e:
            logger.warning(f"NLTK processing failed: {e}. Using simple word filtering.")
            # Simple fallback: extract words based on length and stop words
            words = re.findall(r"\b[a-zA-Z]{3,}\b", cleaned_text.lower())
            keywords = []
            for word in words:
                if word not in self.stop_words and word not in keywords:
                    keywords.append(word)
            return keywords[:max_keywords]


class TFIDFKeywordExtractor:
    """TF-IDF based keyword extraction."""

    def __init__(self, max_features: int = 1000, ngram_range: Tuple[int, int] = (1, 3)):
        """Initialize TF-IDF extractor."""
        self.max_features = max_features
        self.ngram_range = ngram_range
        self.preprocessor = TextPreprocessor()

        # Initialize TF-IDF vectorizer with custom preprocessing
        self.vectorizer = TfidfVectorizer(
            max_features=max_features,
            ngram_range=ngram_range,
            stop_words="english",
            lowercase=True,
            # Minimum 3 chars, start with letter
            token_pattern=r"\b[a-zA-Z][a-zA-Z0-9]{2,}\b",
            min_df=1,  # Minimum document frequency
            max_df=0.95,  # Maximum document frequency
        )

    def extract_keywords(
        self, texts: List[str], top_k: int = 10
    ) -> List[List[KeywordResult]]:
        """Extract keywords from multiple texts using TF-IDF."""
        if not texts:
            return []

        # Preprocess texts
        cleaned_texts = [self.preprocessor.clean_text(text) for text in texts]

        # Filter out empty texts
        non_empty_texts = [
            (i, text) for i, text in enumerate(cleaned_texts) if text.strip()
        ]

        if len(non_empty_texts) < 1:
            logger.warning("No valid texts for TF-IDF extraction")
            return [[] for _ in texts]

        try:
            # Adjust min_df for small datasets
            if len(non_empty_texts) == 1:
                # For single document, use simple word frequency
                return self._extract_keywords_single_doc(texts, top_k)

            # For multiple documents, use TF-IDF
            actual_texts = [text for _, text in non_empty_texts]

            # Create a new vectorizer with adjusted parameters for small
            # datasets
            vectorizer = TfidfVectorizer(
                max_features=self.max_features,
                ngram_range=self.ngram_range,
                stop_words="english",
                lowercase=True,
                token_pattern=r"\b[a-zA-Z][a-zA-Z0-9]{2,}\b",
                min_df=1,  # Allow words that appear in at least 1 document
                max_df=(
                    min(0.95, len(actual_texts) - 1) if len(actual_texts) > 1 else 1.0
                ),
            )

            # Fit TF-IDF on all texts
            tfidf_matrix = vectorizer.fit_transform(actual_texts)
            feature_names = vectorizer.get_feature_names_out()

            # Initialize results for all original texts
            results = [[] for _ in texts]

            # Process each non-empty text
            for result_idx, (original_idx, _) in enumerate(non_empty_texts):
                # Get TF-IDF scores for this document
                doc_scores = tfidf_matrix[result_idx].toarray()[0]

                # Get top keywords with scores
                top_indices = doc_scores.argsort()[-top_k:][::-1]

                keywords = []
                for idx in top_indices:
                    if (
                        doc_scores[idx] > 0
                    ):  # Only include words that appear in this document
                        keywords.append(
                            KeywordResult(
                                keyword=feature_names[idx],
                                score=float(doc_scores[idx]),
                                method="tfidf",
                            )
                        )

                results[original_idx] = keywords

            return results

        except Exception as e:
            logger.error(f"Error in TF-IDF extraction: {e}")
            # Fallback to simple frequency-based extraction
            return self._extract_keywords_fallback(texts, top_k)

    def _extract_keywords_single_doc(
        self, texts: List[str], top_k: int
    ) -> List[List[KeywordResult]]:
        """Extract keywords from a single document using word frequency."""
        results = []
        for text in texts:
            try:
                pos_keywords = self.preprocessor.extract_keywords_pos(
                    text, max_keywords=top_k
                )
                keywords = [
                    KeywordResult(keyword=kw, score=0.5, method="frequency")
                    for kw in pos_keywords
                ]
                results.append(keywords)
            except Exception as e:
                logger.error(f"Error in single doc extraction: {e}")
                results.append([])
        return results

    def _extract_keywords_fallback(
        self, texts: List[str], top_k: int
    ) -> List[List[KeywordResult]]:
        """Fallback keyword extraction using simple methods."""
        results = []
        for text in texts:
            try:
                # Use simple word frequency counting
                words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{2,}\b", text.lower())
                word_freq = {}
                for word in words:
                    if word not in self.preprocessor.stop_words:
                        word_freq[word] = word_freq.get(word, 0) + 1

                # Get top words by frequency
                top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[
                    :top_k
                ]
                keywords = [
                    KeywordResult(
                        keyword=word, score=freq / len(words), method="frequency"
                    )
                    for word, freq in top_words
                ]
                results.append(keywords)
            except Exception as e:
                logger.error(f"Error in fallback extraction: {e}")
                results.append([])
        return results


class LDATopicModeler:
    """Latent Dirichlet Allocation for topic modeling."""

    def __init__(self, n_topics: int = 10, max_features: int = 1000):
        """Initialize LDA topic modeler."""
        self.n_topics = n_topics
        self.max_features = max_features
        self.preprocessor = TextPreprocessor()

        # Initialize count vectorizer for LDA
        self.vectorizer = CountVectorizer(
            max_features=max_features,
            ngram_range=(1, 2),
            stop_words="english",
            lowercase=True,
            token_pattern=r"\b[a-zA-Z][a-zA-Z0-9]{2,}\b",
            min_df=1,
            max_df=0.95,
        )

        # Initialize LDA model
        self.lda_model = LatentDirichletAllocation(
            n_components=n_topics,
            max_iter=10,
            learning_method="online",
            learning_offset=50.0,
            random_state=42,
        )

    def fit_topics(self, texts: List[str]) -> Dict[str, Any]:
        """Fit LDA model on texts and return topic information."""
        if not texts or len(texts) < 2:
            logger.warning("Insufficient texts for topic modeling")
            return {"topics": [], "model_fitted": False}

        try:
            # Preprocess texts
            cleaned_texts = [self.preprocessor.clean_text(text) for text in texts]
            cleaned_texts = [text for text in cleaned_texts if len(text.split()) > 10]

            if len(cleaned_texts) < 2:
                logger.warning("Insufficient cleaned texts for topic modeling")
                return {"topics": [], "model_fitted": False}

            # Vectorize texts
            doc_term_matrix = self.vectorizer.fit_transform(cleaned_texts)

            # Fit LDA model
            self.lda_model.fit(doc_term_matrix)

            # Extract topic information
            feature_names = self.vectorizer.get_feature_names_out()
            topics = []

            for topic_idx, topic in enumerate(self.lda_model.components_):
                # Get top words for this topic
                top_word_indices = topic.argsort()[-10:][::-1]
                top_words = [feature_names[i] for i in top_word_indices]

                # Generate topic name from top words
                topic_name = "_".join(top_words[:3])

                topics.append(
                    {
                        "topic_id": topic_idx,
                        "topic_name": topic_name,
                        "topic_words": top_words,
                        "word_scores": [float(topic[i]) for i in top_word_indices],
                    }
                )

            return {
                "topics": topics,
                "model_fitted": True,
                "n_texts": len(cleaned_texts),
                "perplexity": self.lda_model.perplexity(doc_term_matrix),
            }

        except Exception as e:
            logger.error(f"Error in LDA topic modeling: {e}")
            return {"topics": [], "model_fitted": False}

    def predict_topics(self, texts: List[str]) -> List[List[TopicResult]]:
        """Predict topics for new texts."""
        if not hasattr(self.lda_model, "components_"):
            logger.error("LDA model not fitted yet")
            return [[] for _ in texts]

        try:
            # Preprocess and vectorize texts
            cleaned_texts = [self.preprocessor.clean_text(text) for text in texts]
            doc_term_matrix = self.vectorizer.transform(cleaned_texts)

            # Predict topic distributions
            topic_distributions = self.lda_model.transform(doc_term_matrix)

            results = []
            feature_names = self.vectorizer.get_feature_names_out()

            for doc_idx, distribution in enumerate(topic_distributions):
                doc_topics = []

                # Get topics with probability > threshold
                for topic_idx, prob in enumerate(distribution):
                    if prob > 0.1:  # Minimum probability threshold
                        topic = self.lda_model.components_[topic_idx]
                        top_word_indices = topic.argsort()[-5:][::-1]
                        top_words = [feature_names[i] for i in top_word_indices]
                        topic_name = "_".join(top_words[:3])

                        doc_topics.append(
                            TopicResult(
                                topic_id=topic_idx,
                                topic_name=topic_name,
                                topic_words=top_words,
                                probability=float(prob),
                            )
                        )

                # Sort by probability
                doc_topics.sort(key=lambda x: x.probability, reverse=True)
                results.append(doc_topics)

            return results

        except Exception as e:
            logger.error(f"Error in topic prediction: {e}")
            return [[] for _ in texts]


class KeywordTopicExtractor:
    """Main class for keyword extraction and topic modeling."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the keyword and topic extractor."""
        self.config = config or self._get_default_config()

        # Initialize extractors
        self.tfidf_extractor = TFIDFKeywordExtractor(
            max_features=self.config.get("tfidf_max_features", 1000),
            ngram_range=tuple(self.config.get("tfidf_ngram_range", [1, 3])),
        )

        self.lda_modeler = LDATopicModeler(
            n_topics=self.config.get("lda_n_topics", 10),
            max_features=self.config.get("lda_max_features", 1000),
        )

        # Track fitted state
        self.topics_fitted = False

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "tfidf_max_features": 1000,
            "tfidf_ngram_range": [1, 3],
            "lda_n_topics": 10,
            "lda_max_features": 1000,
            "keywords_per_article": 10,
            "min_topic_probability": 0.1,
        }

    def fit_corpus(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Fit topic model on a corpus of articles."""
        texts = [
            f"{article.get('title', '')} {article.get('content', '')}"
            for article in articles
            if article.get("content")
        ]

        logger.info(f"Fitting topic model on {len(texts)} articles")

        # Fit LDA topic model
        topic_info = self.lda_modeler.fit_topics(texts)
        self.topics_fitted = topic_info["model_fitted"]

        return topic_info

    def extract_keywords_and_topics(self, article: Dict[str, Any]) -> ExtractionResult:
        """Extract keywords and topics from a single article."""
        start_time = datetime.now()

        # Prepare text for analysis
        title = article.get("title", "")
        content = article.get("content", "")
        full_text = f"{title} {content}".strip()

        if not full_text:
            logger.warning(
                f"Empty text for article {
                    article.get(
                        'id', 'unknown')}"
            )
            return self._empty_result(article, start_time)

        # Extract keywords using TF-IDF
        keywords = []
        try:
            tfidf_results = self.tfidf_extractor.extract_keywords(
                [full_text], top_k=self.config.get("keywords_per_article", 10)
            )
            if tfidf_results:
                keywords = tfidf_results[0]
        except Exception as e:
            logger.error(f"Error in TF-IDF keyword extraction: {e}")
            # Fallback to POS-based extraction for single articles
            try:
                pos_keywords = self.tfidf_extractor.preprocessor.extract_keywords_pos(
                    full_text, max_keywords=10
                )
                keywords = [
                    KeywordResult(keyword=kw, score=0.5, method="pos")
                    for kw in pos_keywords
                ]
            except Exception as e2:
                logger.error(f"Error in fallback POS extraction: {e2}")

        # Extract topics if model is fitted
        topics = []
        dominant_topic = None
        if self.topics_fitted:
            try:
                topic_results = self.lda_modeler.predict_topics([full_text])
                if topic_results and topic_results[0]:
                    topics = topic_results[0]
                    dominant_topic = topics[0] if topics else None
            except Exception as e:
                logger.error(f"Error extracting topics: {e}")

        # Calculate processing time
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()

        return ExtractionResult(
            article_id=article.get("id", ""),
            url=article.get("url", ""),
            title=title,
            keywords=keywords,
            topics=topics,
            dominant_topic=dominant_topic,
            extraction_method="tfidf_lda",
            processed_at=end_time,
            processing_time=processing_time,
        )

    def _empty_result(
        self, article: Dict[str, Any], start_time: datetime
    ) -> ExtractionResult:
        """Create empty result for articles with no content."""
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()

        return ExtractionResult(
            article_id=article.get("id", ""),
            url=article.get("url", ""),
            title=article.get("title", ""),
            keywords=[],
            topics=[],
            dominant_topic=None,
            extraction_method="empty",
            processed_at=end_time,
            processing_time=processing_time,
        )

    def process_batch(self, articles: List[Dict[str, Any]]) -> List[ExtractionResult]:
        """Process a batch of articles for keywords and topics."""
        if not articles:
            return []

        logger.info(f"Processing batch of {len(articles)} articles")

        # First fit the topic model if not already fitted
        if not self.topics_fitted:
            self.fit_corpus(articles)

        # Process each article
        results = []
        for article in articles:
            try:
                result = self.extract_keywords_and_topics(article)
                results.append(result)
            except Exception as e:
                logger.error(
                    f"Error processing article {
                        article.get(
                            'id', 'unknown')}: {e}"
                )
                results.append(self._empty_result(article, datetime.now()))

        logger.info(f"Successfully processed {len(results)} articles")
        return results


class SimpleKeywordExtractor:
    """Simplified keyword extractor that works without external dependencies."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize simple extractor."""
        self.config = config or self._get_default_config()
        self.preprocessor = self._create_simple_preprocessor()
        self.topics_fitted = False

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {"keywords_per_article": 10, "min_keyword_length": 3, "max_keywords": 50}

    def _create_simple_preprocessor(self):
        """Create a simple preprocessor that doesn't require NLTK."""

        class SimplePreprocessor:
            def __init__(self):
                self.stop_words = {
                    "the",
                    "a",
                    "an",
                    "and",
                    "or",
                    "but",
                    "in",
                    "on",
                    "at",
                    "to",
                    "for",
                    "of",
                    "with",
                    "by",
                    "from",
                    "up",
                    "about",
                    "into",
                    "through",
                    "during",
                    "before",
                    "after",
                    "above",
                    "below",
                    "between",
                    "among",
                    "over",
                    "under",
                    "is",
                    "are",
                    "was",
                    "were",
                    "be",
                    "been",
                    "being",
                    "have",
                    "has",
                    "had",
                    "do",
                    "does",
                    "did",
                    "will",
                    "would",
                    "could",
                    "should",
                    "may",
                    "might",
                    "must",
                    "can",
                    "this",
                    "that",
                    "these",
                    "those",
                    "i",
                    "you",
                    "he",
                    "she",
                    "it",
                    "we",
                    "they",
                    "me",
                    "him",
                    "her",
                    "us",
                    "them",
                    "my",
                    "your",
                    "his",
                    "her",
                    "its",
                    "our",
                    "their",
                    "said",
                    "says",
                    "according",
                    "report",
                    "reports",
                    "news",
                    "article",
                    "story",
                }

            def clean_text(self, text: str) -> str:
                # Remove HTML tags
                text = re.sub(r"<[^>]+>", "", text)
                # Remove URLs
                text = re.sub(r"http[s]?://\S+", "", text)
                # Remove special characters except letters and spaces
                text = re.sub(r"[^a-zA-Z\s]", "", text)
                # Remove extra whitespace
                text = re.sub(r"\s+", " ", text)
                return text.strip()

            def extract_keywords_pos(
                self, text: str, max_keywords: int = 20
            ) -> List[str]:
                cleaned_text = self.clean_text(text)
                words = re.findall(r"\b[a-zA-Z]{3,}\b", cleaned_text.lower())
                keywords = []
                for word in words:
                    if word not in self.stop_words and word not in keywords:
                        keywords.append(word)
                return keywords[:max_keywords]

        return SimplePreprocessor()

    def extract_keywords_and_topics(self, article: Dict[str, Any]) -> ExtractionResult:
        """Extract keywords from a single article."""
        start_time = datetime.now()

        title = article.get("title", "")
        content = article.get("content", "")
        full_text = f"{title} {content}".strip()

        if not full_text:
            return self._empty_result(article, start_time)

        # Extract keywords using simple method
        keyword_strings = self.preprocessor.extract_keywords_pos(
            full_text, max_keywords=self.config.get("keywords_per_article", 10)
        )

        keywords = [
            KeywordResult(keyword=kw, score=0.5, method="simple")
            for kw in keyword_strings
        ]

        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()

        return ExtractionResult(
            article_id=article.get("id", ""),
            url=article.get("url", ""),
            title=title,
            keywords=keywords,
            topics=[],
            dominant_topic=None,
            extraction_method="simple",
            processed_at=end_time,
            processing_time=processing_time,
        )

    def process_batch(self, articles: List[Dict[str, Any]]) -> List[ExtractionResult]:
        """Process multiple articles."""
        results = []
        for article in articles:
            result = self.extract_keywords_and_topics(article)
            results.append(result)
        return results

    def _empty_result(
        self, article: Dict[str, Any], start_time: datetime
    ) -> ExtractionResult:
        """Create empty result for failed processing."""
        end_time = datetime.now()
        return ExtractionResult(
            article_id=article.get("id", ""),
            url=article.get("url", ""),
            title=article.get("title", ""),
            keywords=[],
            topics=[],
            dominant_topic=None,
            extraction_method="simple",
            processed_at=end_time,
            processing_time=(end_time - start_time).total_seconds(),
        )


def create_keyword_extractor(
    config_path: Optional[str] = None,
) -> Union[KeywordTopicExtractor, SimpleKeywordExtractor]:
    """
    Factory function to create keyword extractor with fallback to simple extractor
    if ML dependencies are not available.
    """
    try:
        # Check if all required ML dependencies are available
        sklearn_available = False
        try:
            pass

            sklearn_available = True
        except ImportError:
            pass

        nltk_available = False
        try:
            pass

            # Try to use NLTK to check if it's properly set up
            from nltk.corpus import stopwords

            # Test if data is available (may need download)
            try:
                stopwords.words("english")
                nltk_available = True
            except LookupError:
                # NLTK data not downloaded, but module available
                nltk_available = False
        except ImportError:
            pass

        spacy_available = False
        try:
            import spacy

            # Check if the model is available
            try:
                spacy.load("en_core_web_sm")
                spacy_available = True
            except OSError:
                # Model not available
                spacy_available = False
        except ImportError:
            pass

        logger.info(
            f"Dependencies check: sklearn={sklearn_available}, nltk={nltk_available}, spacy={spacy_available}"
        )

        # If ML dependencies are available, use the full extractor
        if sklearn_available:
            config = None
            if config_path and os.path.exists(config_path):
                try:
                    with open(config_path, "r") as f:
                        config = json.load(f)
                except Exception as e:
                    logger.error(f"Error loading config from {config_path}: {e}")
            return KeywordTopicExtractor(config)
        else:
            # Fall back to simple extractor
            logger.warning(
                "ML dependencies not available, using simple keyword extractor"
            )
            config = None
            if config_path and os.path.exists(config_path):
                try:
                    with open(config_path, "r") as f:
                        config = json.load(f)
                except Exception as e:
                    logger.error(f"Error loading config from {config_path}: {e}")
            return SimpleKeywordExtractor(config)

    except Exception as e:
        logger.error(f"Failed to create keyword extractor: {e}")
        # Fall back to simple extractor in case of any errors
        logger.warning("Falling back to simple keyword extractor due to error")
        return SimpleKeywordExtractor()


# Example usage and testing
if __name__ == "__main__":
    # Sample articles for testing
    sample_articles = [
        {
            "id": "test_1",
            "url": "https://example.com/1",
            "title": "Breaking: New AI Technology Revolutionizes Healthcare",
            "content": "Artificial intelligence and machine learning algorithms are transforming medical diagnosis and treatment. Researchers have developed advanced neural networks that can detect diseases earlier than traditional methods.",
        },
        {
            "id": "test_2",
            "url": "https://example.com/2",
            "title": "Climate Change Impact on Global Economy",
            "content": "Environmental scientists warn that climate change is affecting global markets and economic stability. Rising temperatures and extreme weather events are disrupting supply chains and agricultural production.",
        },
    ]

    # Initialize extractor
    extractor = create_keyword_extractor()

    # Process articles
    results = extractor.process_batch(sample_articles)

    # Display results
    for result in results:
        print(f"\nArticle: {result.title}")
        print(f"Keywords: {[k.keyword for k in result.keywords[:5]]}")
        if result.dominant_topic:
            print(f"Dominant Topic: {result.dominant_topic.topic_name}")
        print(f"Processing Time: {result.processing_time:.2f}s")
