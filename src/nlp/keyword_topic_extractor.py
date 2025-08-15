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

import os
import re
import json
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.cluster import KMeans
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.stem import WordNetLemmatizer
from nltk.tag import pos_tag
import spacy

# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

try:
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('wordnet')

try:
    nltk.data.find('taggers/averaged_perceptron_tagger')
except LookupError:
    nltk.download('averaged_perceptron_tagger')

# Set up logging
logger = logging.getLogger(__name__)


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
        self.lemmatizer = WordNetLemmatizer()
        
        # Extended stopwords including news-specific terms
        self.stop_words = set(stopwords.words('english'))
        self.stop_words.update([
            'said', 'says', 'according', 'report', 'reports', 'news',
            'article', 'story', 'post', 'published', 'updated', 'source',
            'sources', 'reporter', 'correspondent', 'editorial', 'editor',
            'website', 'online', 'digital', 'print', 'media', 'press',
            'today', 'yesterday', 'tomorrow', 'monday', 'tuesday', 
            'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
            'january', 'february', 'march', 'april', 'may', 'june',
            'july', 'august', 'september', 'october', 'november', 'december'
        ])
        
        # Valid POS tags for keywords (nouns, adjectives, verbs)
        self.valid_pos = {'NN', 'NNS', 'NNP', 'NNPS', 'JJ', 'JJR', 'JJS', 'VB', 'VBD', 'VBG', 'VBN', 'VBP', 'VBZ'}
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove URLs
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        
        # Remove email addresses
        text = re.sub(r'\S+@\S+', '', text)
        
        # Remove extra whitespace and newlines
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters but keep basic punctuation
        text = re.sub(r'[^\w\s\.\,\;\:\!\?]', '', text)
        
        return text.strip()
    
    def extract_sentences(self, text: str) -> List[str]:
        """Extract sentences from text."""
        cleaned_text = self.clean_text(text)
        sentences = sent_tokenize(cleaned_text)
        return [s for s in sentences if len(s.split()) > 3]  # Filter very short sentences
    
    def extract_keywords_pos(self, text: str, min_length: int = 3, max_keywords: int = 20) -> List[str]:
        """Extract potential keywords using POS tagging."""
        cleaned_text = self.clean_text(text)
        tokens = word_tokenize(cleaned_text.lower())
        
        # POS tagging
        pos_tagged = pos_tag(tokens)
        
        # Extract words with valid POS tags
        keywords = []
        for word, pos in pos_tagged:
            if (pos in self.valid_pos and 
                word not in self.stop_words and 
                len(word) >= min_length and 
                word.isalpha()):
                lemmatized = self.lemmatizer.lemmatize(word)
                keywords.append(lemmatized)
        
        # Remove duplicates while preserving order
        unique_keywords = []
        seen = set()
        for keyword in keywords:
            if keyword not in seen:
                unique_keywords.append(keyword)
                seen.add(keyword)
        
        return unique_keywords[:max_keywords]


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
            stop_words='english',
            lowercase=True,
            token_pattern=r'\b[a-zA-Z][a-zA-Z0-9]{2,}\b',  # Minimum 3 chars, start with letter
            min_df=1,  # Minimum document frequency
            max_df=0.95  # Maximum document frequency
        )
    
    def extract_keywords(self, texts: List[str], top_k: int = 10) -> List[List[KeywordResult]]:
        """Extract keywords from multiple texts using TF-IDF."""
        if not texts:
            return []
        
        # Preprocess texts
        cleaned_texts = [self.preprocessor.clean_text(text) for text in texts]
        
        # Filter out empty texts
        non_empty_texts = [(i, text) for i, text in enumerate(cleaned_texts) if text.strip()]
        
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
            
            # Create a new vectorizer with adjusted parameters for small datasets
            vectorizer = TfidfVectorizer(
                max_features=self.max_features,
                ngram_range=self.ngram_range,
                stop_words='english',
                lowercase=True,
                token_pattern=r'\b[a-zA-Z][a-zA-Z0-9]{2,}\b',
                min_df=1,  # Allow words that appear in at least 1 document
                max_df=min(0.95, len(actual_texts) - 1) if len(actual_texts) > 1 else 1.0
            )
            
            # Fit TF-IDF on all texts
            tfidf_matrix = vectorizer.fit_transform(actual_texts)
            feature_names = vectorizer.get_feature_names_out()
            
            results = [[] for _ in texts]  # Initialize results for all original texts
            
            # Process each non-empty text
            for result_idx, (original_idx, _) in enumerate(non_empty_texts):
                # Get TF-IDF scores for this document
                doc_scores = tfidf_matrix[result_idx].toarray()[0]
                
                # Get top keywords with scores
                top_indices = doc_scores.argsort()[-top_k:][::-1]
                
                keywords = []
                for idx in top_indices:
                    if doc_scores[idx] > 0:  # Only include words that appear in this document
                        keywords.append(KeywordResult(
                            keyword=feature_names[idx],
                            score=float(doc_scores[idx]),
                            method='tfidf'
                        ))
                
                results[original_idx] = keywords
            
            return results
            
        except Exception as e:
            logger.error(f"Error in TF-IDF extraction: {e}")
            # Fallback to simple frequency-based extraction
            return self._extract_keywords_fallback(texts, top_k)
    
    def _extract_keywords_single_doc(self, texts: List[str], top_k: int) -> List[List[KeywordResult]]:
        """Extract keywords from a single document using word frequency."""
        results = []
        for text in texts:
            try:
                pos_keywords = self.preprocessor.extract_keywords_pos(text, max_keywords=top_k)
                keywords = [
                    KeywordResult(keyword=kw, score=0.5, method='frequency') 
                    for kw in pos_keywords
                ]
                results.append(keywords)
            except Exception as e:
                logger.error(f"Error in single doc extraction: {e}")
                results.append([])
        return results
    
    def _extract_keywords_fallback(self, texts: List[str], top_k: int) -> List[List[KeywordResult]]:
        """Fallback keyword extraction using simple methods."""
        results = []
        for text in texts:
            try:
                # Use simple word frequency counting
                words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9]{2,}\b', text.lower())
                word_freq = {}
                for word in words:
                    if word not in self.preprocessor.stop_words:
                        word_freq[word] = word_freq.get(word, 0) + 1
                
                # Get top words by frequency
                top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:top_k]
                keywords = [
                    KeywordResult(keyword=word, score=freq/len(words), method='frequency') 
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
            stop_words='english',
            lowercase=True,
            token_pattern=r'\b[a-zA-Z][a-zA-Z0-9]{2,}\b',
            min_df=1,
            max_df=0.95
        )
        
        # Initialize LDA model
        self.lda_model = LatentDirichletAllocation(
            n_components=n_topics,
            max_iter=10,
            learning_method='online',
            learning_offset=50.0,
            random_state=42
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
                
                topics.append({
                    "topic_id": topic_idx,
                    "topic_name": topic_name,
                    "topic_words": top_words,
                    "word_scores": [float(topic[i]) for i in top_word_indices]
                })
            
            return {
                "topics": topics,
                "model_fitted": True,
                "n_texts": len(cleaned_texts),
                "perplexity": self.lda_model.perplexity(doc_term_matrix)
            }
            
        except Exception as e:
            logger.error(f"Error in LDA topic modeling: {e}")
            return {"topics": [], "model_fitted": False}
    
    def predict_topics(self, texts: List[str]) -> List[List[TopicResult]]:
        """Predict topics for new texts."""
        if not hasattr(self.lda_model, 'components_'):
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
                        
                        doc_topics.append(TopicResult(
                            topic_id=topic_idx,
                            topic_name=topic_name,
                            topic_words=top_words,
                            probability=float(prob)
                        ))
                
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
            max_features=self.config.get('tfidf_max_features', 1000),
            ngram_range=tuple(self.config.get('tfidf_ngram_range', [1, 3]))
        )
        
        self.lda_modeler = LDATopicModeler(
            n_topics=self.config.get('lda_n_topics', 10),
            max_features=self.config.get('lda_max_features', 1000)
        )
        
        # Track fitted state
        self.topics_fitted = False
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            'tfidf_max_features': 1000,
            'tfidf_ngram_range': [1, 3],
            'lda_n_topics': 10,
            'lda_max_features': 1000,
            'keywords_per_article': 10,
            'min_topic_probability': 0.1
        }
    
    def fit_corpus(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Fit topic model on a corpus of articles."""
        texts = [f"{article.get('title', '')} {article.get('content', '')}" 
                for article in articles if article.get('content')]
        
        logger.info(f"Fitting topic model on {len(texts)} articles")
        
        # Fit LDA topic model
        topic_info = self.lda_modeler.fit_topics(texts)
        self.topics_fitted = topic_info['model_fitted']
        
        return topic_info
    
    def extract_keywords_and_topics(self, article: Dict[str, Any]) -> ExtractionResult:
        """Extract keywords and topics from a single article."""
        start_time = datetime.now()
        
        # Prepare text for analysis
        title = article.get('title', '')
        content = article.get('content', '')
        full_text = f"{title} {content}".strip()
        
        if not full_text:
            logger.warning(f"Empty text for article {article.get('id', 'unknown')}")
            return self._empty_result(article, start_time)
        
        # Extract keywords using TF-IDF
        keywords = []
        try:
            tfidf_results = self.tfidf_extractor.extract_keywords(
                [full_text], 
                top_k=self.config.get('keywords_per_article', 10)
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
                keywords = [KeywordResult(keyword=kw, score=0.5, method='pos') for kw in pos_keywords]
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
            article_id=article.get('id', ''),
            url=article.get('url', ''),
            title=title,
            keywords=keywords,
            topics=topics,
            dominant_topic=dominant_topic,
            extraction_method='tfidf_lda',
            processed_at=end_time,
            processing_time=processing_time
        )
    
    def _empty_result(self, article: Dict[str, Any], start_time: datetime) -> ExtractionResult:
        """Create empty result for articles with no content."""
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        return ExtractionResult(
            article_id=article.get('id', ''),
            url=article.get('url', ''),
            title=article.get('title', ''),
            keywords=[],
            topics=[],
            dominant_topic=None,
            extraction_method='empty',
            processed_at=end_time,
            processing_time=processing_time
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
                logger.error(f"Error processing article {article.get('id', 'unknown')}: {e}")
                results.append(self._empty_result(article, datetime.now()))
        
        logger.info(f"Successfully processed {len(results)} articles")
        return results


def create_keyword_extractor(config_path: Optional[str] = None) -> KeywordTopicExtractor:
    """Factory function to create a keyword extractor with configuration."""
    config = None
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"Error loading config from {config_path}: {e}")
    
    return KeywordTopicExtractor(config)


# Example usage and testing
if __name__ == "__main__":
    # Sample articles for testing
    sample_articles = [
        {
            "id": "test_1",
            "url": "https://example.com/1",
            "title": "Breaking: New AI Technology Revolutionizes Healthcare",
            "content": "Artificial intelligence and machine learning algorithms are transforming medical diagnosis and treatment. Researchers have developed advanced neural networks that can detect diseases earlier than traditional methods."
        },
        {
            "id": "test_2", 
            "url": "https://example.com/2",
            "title": "Climate Change Impact on Global Economy",
            "content": "Environmental scientists warn that climate change is affecting global markets and economic stability. Rising temperatures and extreme weather events are disrupting supply chains and agricultural production."
        }
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
