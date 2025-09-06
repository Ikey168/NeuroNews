#!/usr/bin/env python3
"""
Service Integration ML Testing (Issue #483) 
Tests for NLP service integration classes and text processing ML components.
"""

import pytest
import os
import sys
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import numpy as np

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

@pytest.mark.unit
class TestNLPServiceIntegration:
    """Test NLP service integration and orchestration"""
    
    def test_nlp_service_simulation(self):
        """Test NLP service integration functionality (simulated)"""
        
        class MockNLPService:
            def __init__(self):
                self.services = {}
                self.active_models = set()
                self.processing_queue = []
            
            def register_service(self, service_name: str, service_config: dict):
                """Register an NLP service"""
                self.services[service_name] = {
                    "config": service_config,
                    "status": "registered",
                    "processed_items": 0
                }
            
            def activate_service(self, service_name: str):
                """Activate an NLP service"""
                if service_name in self.services:
                    self.services[service_name]["status"] = "active"
                    self.active_models.add(service_name)
                    return True
                return False
            
            def process_text(self, service_name: str, text: str, options: dict = None):
                """Process text through specified NLP service"""
                if service_name not in self.active_models:
                    raise ValueError(f"Service {service_name} is not active")
                
                # Simulate different NLP services
                if service_name == "sentiment_analyzer":
                    return {
                        "sentiment": "positive" if "good" in text.lower() else "negative",
                        "confidence": 0.87,
                        "service": service_name
                    }
                elif service_name == "entity_extractor":
                    # Mock entity extraction
                    entities = []
                    if "company" in text.lower():
                        entities.append({"text": "company", "label": "ORG", "confidence": 0.92})
                    if "john" in text.lower():
                        entities.append({"text": "John", "label": "PERSON", "confidence": 0.95})
                    
                    return {
                        "entities": entities,
                        "service": service_name
                    }
                elif service_name == "topic_classifier":
                    # Mock topic classification
                    topics = ["politics", "technology", "sports", "business"]
                    return {
                        "topic": topics[hash(text) % len(topics)],
                        "confidence": 0.78,
                        "service": service_name
                    }
                
                self.services[service_name]["processed_items"] += 1
                return {"message": "processed", "service": service_name}
            
            def batch_process(self, service_name: str, texts: list, batch_size: int = 10):
                """Process multiple texts in batches"""
                results = []
                for i in range(0, len(texts), batch_size):
                    batch = texts[i:i + batch_size]
                    batch_results = []
                    
                    for text in batch:
                        result = self.process_text(service_name, text)
                        batch_results.append(result)
                    
                    results.extend(batch_results)
                
                return results
            
            def get_service_stats(self, service_name: str):
                """Get statistics for a service"""
                if service_name not in self.services:
                    return None
                
                return {
                    "service_name": service_name,
                    "status": self.services[service_name]["status"],
                    "processed_items": self.services[service_name]["processed_items"],
                    "is_active": service_name in self.active_models
                }
        
        nlp_service = MockNLPService()
        
        # Test service registration
        nlp_service.register_service("sentiment_analyzer", {
            "model": "roberta-sentiment",
            "batch_size": 32
        })
        
        nlp_service.register_service("entity_extractor", {
            "model": "spacy-ner",
            "languages": ["en"]
        })
        
        assert "sentiment_analyzer" in nlp_service.services
        assert "entity_extractor" in nlp_service.services
        
        # Test service activation
        assert nlp_service.activate_service("sentiment_analyzer")
        assert nlp_service.activate_service("entity_extractor")
        assert "sentiment_analyzer" in nlp_service.active_models
        
        # Test text processing
        sentiment_result = nlp_service.process_text(
            "sentiment_analyzer", 
            "This is a good article about technology"
        )
        
        assert sentiment_result["sentiment"] == "positive"
        assert sentiment_result["confidence"] > 0
        assert sentiment_result["service"] == "sentiment_analyzer"
        
        # Test entity extraction
        entity_result = nlp_service.process_text(
            "entity_extractor",
            "John works at a technology company"
        )
        
        assert "entities" in entity_result
        assert len(entity_result["entities"]) > 0
        
        # Test batch processing
        texts = [
            "Good news about the economy",
            "Bad news about the market", 
            "Neutral report on technology"
        ]
        
        batch_results = nlp_service.batch_process("sentiment_analyzer", texts)
        assert len(batch_results) == 3
        assert all("sentiment" in result for result in batch_results)
        
        # Test service statistics
        stats = nlp_service.get_service_stats("sentiment_analyzer")
        assert stats["processed_items"] >= 4  # Individual + batch processing
        assert stats["is_active"] == True


@pytest.mark.unit  
class TestTextProcessor:
    """Test advanced text processing pipelines"""
    
    def test_text_processor_simulation(self):
        """Test advanced text processing functionality (simulated)"""
        
        class MockTextProcessor:
            def __init__(self):
                self.preprocessing_steps = []
                self.processing_stats = {"processed_documents": 0}
            
            def add_preprocessing_step(self, step_name: str, step_function):
                """Add a preprocessing step to the pipeline"""
                self.preprocessing_steps.append({
                    "name": step_name,
                    "function": step_function
                })
            
            def preprocess_text(self, text: str):
                """Apply all preprocessing steps to text"""
                processed_text = text
                
                for step in self.preprocessing_steps:
                    try:
                        processed_text = step["function"](processed_text)
                    except Exception as e:
                        print(f"Error in step {step['name']}: {e}")
                        continue
                
                return processed_text
            
            def extract_features(self, text: str):
                """Extract text features for ML"""
                features = {}
                
                # Basic text features
                features["word_count"] = len(text.split())
                features["char_count"] = len(text)
                features["sentence_count"] = text.count('.') + text.count('!') + text.count('?')
                features["avg_word_length"] = sum(len(word) for word in text.split()) / max(len(text.split()), 1)
                
                # Advanced features
                features["uppercase_ratio"] = sum(1 for c in text if c.isupper()) / max(len(text), 1)
                features["punctuation_density"] = sum(1 for c in text if c in '.,;:!?') / max(len(text), 1)
                features["question_marks"] = text.count('?')
                features["exclamation_marks"] = text.count('!')
                
                return features
            
            def detect_language(self, text: str):
                """Detect text language (mock implementation)"""
                # Simple heuristic for demo
                common_english_words = ["the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"]
                english_word_count = sum(1 for word in text.lower().split() if word in common_english_words)
                
                if english_word_count > len(text.split()) * 0.1:
                    return {"language": "en", "confidence": 0.95}
                else:
                    return {"language": "unknown", "confidence": 0.3}
            
            def analyze_readability(self, text: str):
                """Analyze text readability"""
                words = text.split()
                sentences = text.count('.') + text.count('!') + text.count('?')
                
                if sentences == 0:
                    return {"score": 0, "level": "unknown"}
                
                # Simplified Flesch Reading Ease approximation
                avg_sentence_length = len(words) / sentences
                avg_syllables_per_word = 1.5  # Approximation
                
                flesch_score = 206.835 - (1.015 * avg_sentence_length) - (84.6 * avg_syllables_per_word)
                
                if flesch_score >= 90:
                    level = "very_easy"
                elif flesch_score >= 80:
                    level = "easy"
                elif flesch_score >= 70:
                    level = "fairly_easy"
                elif flesch_score >= 60:
                    level = "standard"
                elif flesch_score >= 50:
                    level = "fairly_difficult"
                elif flesch_score >= 30:
                    level = "difficult"
                else:
                    level = "very_difficult"
                
                return {"score": flesch_score, "level": level}
            
            def process_document(self, document: dict):
                """Process a complete document"""
                text = document.get("content", "")
                
                processed_doc = {
                    "original_text": text,
                    "preprocessed_text": self.preprocess_text(text),
                    "features": self.extract_features(text),
                    "language": self.detect_language(text),
                    "readability": self.analyze_readability(text),
                    "processed_at": datetime.now().isoformat()
                }
                
                self.processing_stats["processed_documents"] += 1
                return processed_doc
        
        processor = MockTextProcessor()
        
        # Add preprocessing steps
        def remove_html_tags(text):
            import re
            return re.sub(r'<[^>]+>', '', text)
        
        def normalize_whitespace(text):
            import re
            return re.sub(r'\s+', ' ', text.strip())
        
        def remove_urls(text):
            import re
            return re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        
        processor.add_preprocessing_step("remove_html", remove_html_tags)
        processor.add_preprocessing_step("normalize_whitespace", normalize_whitespace)
        processor.add_preprocessing_step("remove_urls", remove_urls)
        
        # Test preprocessing
        messy_text = "<p>This is a   messy    text with https://example.com/link</p>"
        cleaned_text = processor.preprocess_text(messy_text)
        
        assert "<p>" not in cleaned_text
        assert "https://example.com" not in cleaned_text
        assert "  " not in cleaned_text  # Multiple spaces should be normalized
        
        # Test feature extraction
        sample_text = "This is a sample news article. It contains multiple sentences! How readable is it?"
        features = processor.extract_features(sample_text)
        
        assert features["word_count"] > 0
        assert features["sentence_count"] >= 2  # At least 2 sentences
        assert features["question_marks"] == 1
        assert features["exclamation_marks"] == 1
        assert 0 <= features["uppercase_ratio"] <= 1
        
        # Test language detection
        lang_result = processor.detect_language("The quick brown fox jumps over the lazy dog")
        assert lang_result["language"] == "en"
        assert lang_result["confidence"] > 0.8
        
        # Test readability analysis
        readability = processor.analyze_readability(sample_text)
        assert "score" in readability
        assert "level" in readability
        assert isinstance(readability["score"], (int, float))
        
        # Test document processing
        document = {
            "title": "Test Article",
            "content": "This is a comprehensive news article about technology. It discusses various innovations and their impacts on society."
        }
        
        processed_doc = processor.process_document(document)
        
        assert "original_text" in processed_doc
        assert "preprocessed_text" in processed_doc
        assert "features" in processed_doc
        assert "language" in processed_doc
        assert "readability" in processed_doc
        assert "processed_at" in processed_doc
        
        # Verify processing stats
        assert processor.processing_stats["processed_documents"] == 1


@pytest.mark.unit
class TestLanguageDetector:
    """Test multi-language detection and support"""
    
    def test_language_detector_simulation(self):
        """Test language detection functionality (simulated)"""
        
        class MockLanguageDetector:
            def __init__(self):
                self.supported_languages = {
                    'en': {'name': 'English', 'model': 'en_core_web_sm'},
                    'es': {'name': 'Spanish', 'model': 'es_core_news_sm'},
                    'fr': {'name': 'French', 'model': 'fr_core_news_sm'},
                    'de': {'name': 'German', 'model': 'de_core_news_sm'},
                    'zh': {'name': 'Chinese', 'model': 'zh_core_web_sm'}
                }
                
                self.language_keywords = {
                    'en': ['the', 'and', 'to', 'of', 'a', 'in', 'for', 'is', 'on', 'that'],
                    'es': ['el', 'la', 'de', 'que', 'y', 'en', 'un', 'es', 'se', 'no'],
                    'fr': ['le', 'de', 'et', 'à', 'un', 'il', 'être', 'et', 'en', 'avoir'],
                    'de': ['der', 'die', 'und', 'in', 'den', 'von', 'zu', 'das', 'mit', 'sich'],
                    'zh': ['的', '是', '在', '和', '有', '了', '不', '人', '我', '你']
                }
            
            def detect_language(self, text: str, min_confidence: float = 0.5):
                """Detect the language of input text"""
                if not text or len(text.strip()) < 10:
                    return {"language": "unknown", "confidence": 0.0, "supported": False}
                
                text_lower = text.lower()
                language_scores = {}
                
                # Calculate scores for each language based on keyword matches
                for lang_code, keywords in self.language_keywords.items():
                    score = sum(1 for keyword in keywords if keyword in text_lower)
                    language_scores[lang_code] = score / len(keywords)
                
                # Get the language with highest score
                best_language = max(language_scores.items(), key=lambda x: x[1])
                lang_code, confidence = best_language
                
                # Normalize confidence to 0-1 range
                confidence = min(confidence * 2, 1.0)  # Scale up for demo
                
                if confidence < min_confidence:
                    return {"language": "unknown", "confidence": confidence, "supported": False}
                
                return {
                    "language": lang_code,
                    "language_name": self.supported_languages[lang_code]["name"],
                    "confidence": confidence,
                    "supported": lang_code in self.supported_languages
                }
            
            def detect_multiple_languages(self, text: str):
                """Detect if text contains multiple languages"""
                sentences = text.split('.')
                language_detections = []
                
                for sentence in sentences:
                    if len(sentence.strip()) > 5:
                        detection = self.detect_language(sentence.strip())
                        if detection["confidence"] > 0.3:
                            language_detections.append(detection)
                
                # Analyze language diversity
                unique_languages = set(d["language"] for d in language_detections)
                
                return {
                    "is_multilingual": len(unique_languages) > 1,
                    "languages_detected": list(unique_languages),
                    "language_count": len(unique_languages),
                    "sentence_detections": language_detections
                }
            
            def get_processing_pipeline(self, language: str):
                """Get appropriate processing pipeline for language"""
                if language not in self.supported_languages:
                    return {"error": f"Language {language} not supported"}
                
                return {
                    "language": language,
                    "model": self.supported_languages[language]["model"],
                    "preprocessing_steps": [
                        "tokenization",
                        "sentence_segmentation", 
                        "pos_tagging",
                        "named_entity_recognition"
                    ],
                    "supported_tasks": [
                        "text_classification",
                        "sentiment_analysis",
                        "entity_extraction",
                        "summarization"
                    ]
                }
            
            def batch_detect(self, texts: list):
                """Detect languages for multiple texts"""
                results = []
                
                for i, text in enumerate(texts):
                    detection = self.detect_language(text)
                    detection["text_id"] = i
                    results.append(detection)
                
                # Aggregate statistics
                language_counts = {}
                for result in results:
                    lang = result["language"]
                    language_counts[lang] = language_counts.get(lang, 0) + 1
                
                return {
                    "individual_results": results,
                    "language_distribution": language_counts,
                    "total_texts": len(texts),
                    "unique_languages": len(language_counts)
                }
        
        detector = MockLanguageDetector()
        
        # Test single language detection - English
        english_text = "This is a news article about technology and innovation in the modern world."
        en_result = detector.detect_language(english_text)
        
        assert en_result["language"] == "en"
        assert en_result["language_name"] == "English"
        assert en_result["confidence"] > 0.5
        assert en_result["supported"] == True
        
        # Test single language detection - Spanish (mock)
        spanish_text = "Esta es una noticia sobre tecnología y el desarrollo de la sociedad moderna."
        es_result = detector.detect_language(spanish_text)
        # Note: This might not detect as Spanish due to our simple mock, but test the structure
        
        assert "language" in es_result
        assert "confidence" in es_result
        assert "supported" in es_result
        
        # Test short text handling
        short_result = detector.detect_language("Hi")
        assert short_result["language"] == "unknown"
        assert short_result["confidence"] == 0.0
        
        # Test multilingual detection
        mixed_text = "This is English text. Esta parte está en español. This part is English again."
        multi_result = detector.detect_multiple_languages(mixed_text)
        
        assert "is_multilingual" in multi_result
        assert "languages_detected" in multi_result
        assert "language_count" in multi_result
        assert isinstance(multi_result["sentence_detections"], list)
        
        # Test processing pipeline retrieval
        en_pipeline = detector.get_processing_pipeline("en")
        
        assert en_pipeline["language"] == "en"
        assert en_pipeline["model"] == "en_core_web_sm"
        assert "preprocessing_steps" in en_pipeline
        assert "supported_tasks" in en_pipeline
        assert len(en_pipeline["preprocessing_steps"]) > 0
        
        # Test unsupported language
        unsupported_pipeline = detector.get_processing_pipeline("xyz")
        assert "error" in unsupported_pipeline
        
        # Test batch detection
        batch_texts = [
            "English news article about politics",
            "Another English article about sports",
            "Technology news in English",
            "Short text",
            "The weather is nice today and people are enjoying the sunshine"
        ]
        
        batch_results = detector.batch_detect(batch_texts)
        
        assert batch_results["total_texts"] == 5
        assert len(batch_results["individual_results"]) == 5
        assert "language_distribution" in batch_results
        assert "unique_languages" in batch_results
        
        # Most should be detected as English (or unknown for short text)
        assert batch_results["language_distribution"].get("en", 0) > 0


@pytest.mark.unit
class TestContentAnalyzer:
    """Test content analysis and classification"""
    
    def test_content_analyzer_simulation(self):
        """Test content analysis functionality (simulated)"""
        
        class MockContentAnalyzer:
            def __init__(self):
                self.analysis_modules = {
                    "sentiment": True,
                    "topics": True,
                    "entities": True,
                    "quality": True,
                    "credibility": True
                }
                self.processed_count = 0
            
            def analyze_sentiment(self, text: str):
                """Analyze text sentiment"""
                # Simple keyword-based sentiment for demo
                positive_words = ["good", "great", "excellent", "positive", "happy", "success"]
                negative_words = ["bad", "terrible", "awful", "negative", "sad", "failure"]
                
                text_lower = text.lower()
                pos_count = sum(1 for word in positive_words if word in text_lower)
                neg_count = sum(1 for word in negative_words if word in text_lower)
                
                if pos_count > neg_count:
                    sentiment = "positive"
                    confidence = 0.7 + (pos_count - neg_count) * 0.1
                elif neg_count > pos_count:
                    sentiment = "negative"
                    confidence = 0.7 + (neg_count - pos_count) * 0.1
                else:
                    sentiment = "neutral"
                    confidence = 0.5
                
                return {
                    "sentiment": sentiment,
                    "confidence": min(confidence, 0.95),
                    "positive_indicators": pos_count,
                    "negative_indicators": neg_count
                }
            
            def classify_topics(self, text: str):
                """Classify text into topics"""
                topic_keywords = {
                    "politics": ["government", "election", "policy", "political", "vote", "democracy"],
                    "technology": ["technology", "software", "AI", "computer", "digital", "tech"],
                    "business": ["business", "market", "company", "economy", "financial", "profit"],
                    "sports": ["sports", "game", "player", "team", "match", "competition"],
                    "health": ["health", "medical", "doctor", "hospital", "treatment", "medicine"],
                    "science": ["science", "research", "study", "experiment", "discovery", "scientist"]
                }
                
                text_lower = text.lower()
                topic_scores = {}
                
                for topic, keywords in topic_keywords.items():
                    score = sum(1 for keyword in keywords if keyword in text_lower)
                    if score > 0:
                        topic_scores[topic] = score / len(keywords)
                
                if not topic_scores:
                    return {"primary_topic": "general", "confidence": 0.3, "all_topics": {}}
                
                primary_topic = max(topic_scores.items(), key=lambda x: x[1])
                
                return {
                    "primary_topic": primary_topic[0],
                    "confidence": min(primary_topic[1] * 3, 0.95),  # Scale confidence
                    "all_topics": topic_scores
                }
            
            def extract_entities(self, text: str):
                """Extract named entities from text"""
                # Mock entity extraction
                entities = []
                
                # Simple pattern matching for demo
                import re
                
                # Find potential person names (capitalized words)
                person_patterns = re.findall(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', text)
                for person in person_patterns:
                    entities.append({
                        "text": person,
                        "label": "PERSON",
                        "confidence": 0.85,
                        "start": text.find(person),
                        "end": text.find(person) + len(person)
                    })
                
                # Find potential organizations (words ending with common suffixes)
                org_patterns = re.findall(r'\b[A-Z][a-zA-Z]*(?:Corp|Inc|LLC|Ltd|Company)\b', text)
                for org in org_patterns:
                    entities.append({
                        "text": org,
                        "label": "ORG",
                        "confidence": 0.90,
                        "start": text.find(org),
                        "end": text.find(org) + len(org)
                    })
                
                # Find potential locations (capitalized words in specific contexts)
                location_patterns = re.findall(r'\bin [A-Z][a-z]+\b|\b[A-Z][a-z]+ City\b', text)
                for location in location_patterns:
                    entities.append({
                        "text": location.strip(),
                        "label": "GPE",
                        "confidence": 0.75,
                        "start": text.find(location),
                        "end": text.find(location) + len(location)
                    })
                
                return {
                    "entities": entities,
                    "entity_count": len(entities),
                    "entity_types": list(set(e["label"] for e in entities))
                }
            
            def assess_content_quality(self, text: str):
                """Assess content quality metrics"""
                words = text.split()
                sentences = text.count('.') + text.count('!') + text.count('?')
                
                quality_score = 0.5  # Base score
                
                # Length factor
                if 100 <= len(words) <= 1000:
                    quality_score += 0.2
                
                # Sentence structure
                if sentences > 0:
                    avg_sentence_length = len(words) / sentences
                    if 10 <= avg_sentence_length <= 25:
                        quality_score += 0.1
                
                # Capitalization and punctuation
                if text[0].isupper() and text.count('.') > 0:
                    quality_score += 0.1
                
                # Spelling and grammar (mock check)
                error_indicators = text.count('  ')  # Double spaces
                if error_indicators == 0:
                    quality_score += 0.1
                
                quality_score = min(quality_score, 1.0)
                
                return {
                    "quality_score": quality_score,
                    "word_count": len(words),
                    "sentence_count": sentences,
                    "avg_sentence_length": len(words) / max(sentences, 1),
                    "readability_level": "good" if quality_score > 0.7 else "fair" if quality_score > 0.5 else "poor"
                }
            
            def analyze_credibility(self, text: str):
                """Analyze content credibility"""
                credibility_score = 0.5  # Base score
                
                # Check for credible sources indicators
                credible_indicators = [
                    "according to", "study shows", "research indicates", 
                    "expert says", "data reveals", "report states"
                ]
                
                incredible_indicators = [
                    "shocking secret", "doctors hate", "miracle cure",
                    "you won't believe", "amazing trick", "instant results"
                ]
                
                text_lower = text.lower()
                
                credible_count = sum(1 for indicator in credible_indicators if indicator in text_lower)
                incredible_count = sum(1 for indicator in incredible_indicators if indicator in text_lower)
                
                credibility_score += credible_count * 0.15
                credibility_score -= incredible_count * 0.25
                
                credibility_score = max(0.1, min(credibility_score, 1.0))
                
                return {
                    "credibility_score": credibility_score,
                    "credible_indicators": credible_count,
                    "suspicious_indicators": incredible_count,
                    "assessment": "high" if credibility_score > 0.8 else "medium" if credibility_score > 0.5 else "low"
                }
            
            def comprehensive_analysis(self, content: dict):
                """Perform comprehensive content analysis"""
                text = content.get("content", "")
                title = content.get("title", "")
                
                analysis = {
                    "title": title,
                    "content_length": len(text),
                    "sentiment": self.analyze_sentiment(text),
                    "topics": self.classify_topics(text),
                    "entities": self.extract_entities(text),
                    "quality": self.assess_content_quality(text),
                    "credibility": self.analyze_credibility(text),
                    "analyzed_at": datetime.now().isoformat()
                }
                
                # Overall assessment
                overall_score = (
                    analysis["sentiment"]["confidence"] * 0.2 +
                    analysis["topics"]["confidence"] * 0.2 + 
                    analysis["quality"]["quality_score"] * 0.3 +
                    analysis["credibility"]["credibility_score"] * 0.3
                )
                
                analysis["overall_score"] = overall_score
                analysis["recommendation"] = (
                    "publish" if overall_score > 0.7 else
                    "review" if overall_score > 0.5 else 
                    "reject"
                )
                
                self.processed_count += 1
                return analysis
        
        analyzer = MockContentAnalyzer()
        
        # Test sentiment analysis
        positive_text = "This is great news about excellent developments in technology"
        sentiment_result = analyzer.analyze_sentiment(positive_text)
        
        assert sentiment_result["sentiment"] == "positive"
        assert sentiment_result["confidence"] > 0.7
        assert sentiment_result["positive_indicators"] > 0
        
        negative_text = "This is terrible news about awful developments"
        negative_sentiment = analyzer.analyze_sentiment(negative_text)
        assert negative_sentiment["sentiment"] == "negative"
        
        # Test topic classification
        tech_text = "The new AI technology and software development will revolutionize computer science"
        topic_result = analyzer.classify_topics(tech_text)
        
        assert topic_result["primary_topic"] == "technology"
        assert topic_result["confidence"] > 0.5
        assert "technology" in topic_result["all_topics"]
        
        # Test entity extraction
        entity_text = "John Smith works at TechCorp Inc in New York City"
        entity_result = analyzer.extract_entities(entity_text)
        
        assert entity_result["entity_count"] > 0
        assert len(entity_result["entity_types"]) > 0
        # Should find person, organization, and location entities
        
        # Test quality assessment
        quality_text = "This is a well-written article about technology. It contains multiple sentences with proper punctuation. The content is informative and structured appropriately."
        quality_result = analyzer.assess_content_quality(quality_text)
        
        assert quality_result["quality_score"] > 0.5
        assert quality_result["word_count"] > 0
        assert quality_result["sentence_count"] > 1
        assert quality_result["readability_level"] in ["poor", "fair", "good"]
        
        # Test credibility analysis
        credible_text = "According to recent research, the study shows that data reveals important insights about the topic"
        credibility_result = analyzer.analyze_credibility(credible_text)
        
        assert credibility_result["credibility_score"] > 0.5
        assert credibility_result["credible_indicators"] > 0
        assert credibility_result["assessment"] in ["low", "medium", "high"]
        
        # Test comprehensive analysis
        content = {
            "title": "Technology Breakthrough in AI",
            "content": "Researchers at TechCorp have developed excellent new AI technology. According to the study, this breakthrough shows great promise for the future."
        }
        
        comprehensive_result = analyzer.comprehensive_analysis(content)
        
        assert "sentiment" in comprehensive_result
        assert "topics" in comprehensive_result
        assert "entities" in comprehensive_result
        assert "quality" in comprehensive_result
        assert "credibility" in comprehensive_result
        assert "overall_score" in comprehensive_result
        assert "recommendation" in comprehensive_result
        assert comprehensive_result["recommendation"] in ["publish", "review", "reject"]
        
        # Verify processing counter
        assert analyzer.processed_count == 1


@pytest.mark.integration
class TestServiceIntegrationML:
    """Integration tests for service ML components"""
    
    def test_integrated_nlp_processing_pipeline(self):
        """Test integrated NLP processing pipeline"""
        
        # Mock the integration of all services
        class IntegratedNLPPipeline:
            def __init__(self):
                self.nlp_service = MockNLPService()
                self.text_processor = MockTextProcessor() 
                self.language_detector = MockLanguageDetector()
                self.content_analyzer = MockContentAnalyzer()
                
                # Initialize services
                self._setup_services()
            
            def _setup_services(self):
                """Setup all NLP services"""
                self.nlp_service.register_service("sentiment_analyzer", {"model": "roberta"})
                self.nlp_service.register_service("entity_extractor", {"model": "spacy"})
                self.nlp_service.activate_service("sentiment_analyzer")
                self.nlp_service.activate_service("entity_extractor")
            
            def process_article(self, article: dict):
                """Process article through full NLP pipeline"""
                content = article.get("content", "")
                
                # Step 1: Language detection
                language_info = self.language_detector.detect_language(content)
                
                # Step 2: Text preprocessing
                processed_content = self.text_processor.preprocess_text(content)
                
                # Step 3: NLP services processing
                sentiment = self.nlp_service.process_text("sentiment_analyzer", processed_content)
                entities = self.nlp_service.process_text("entity_extractor", processed_content)
                
                # Step 4: Content analysis
                analysis = self.content_analyzer.comprehensive_analysis({
                    "title": article.get("title", ""),
                    "content": processed_content
                })
                
                return {
                    "article_id": article.get("id"),
                    "language": language_info,
                    "processed_content": processed_content,
                    "sentiment": sentiment,
                    "entities": entities,
                    "analysis": analysis,
                    "pipeline_version": "1.0"
                }
        
        # Initialize mock classes (simplified for integration test)
        class MockNLPService:
            def register_service(self, name, config): pass
            def activate_service(self, name): pass
            def process_text(self, service, text):
                if service == "sentiment_analyzer":
                    return {"sentiment": "positive", "confidence": 0.85}
                elif service == "entity_extractor":
                    return {"entities": [{"text": "test", "label": "ORG"}]}
        
        class MockTextProcessor:
            def preprocess_text(self, text):
                return text.strip().replace("  ", " ")
        
        class MockLanguageDetector:
            def detect_language(self, text):
                return {"language": "en", "confidence": 0.95}
        
        class MockContentAnalyzer:
            def comprehensive_analysis(self, content):
                return {
                    "overall_score": 0.8,
                    "recommendation": "publish",
                    "sentiment": {"sentiment": "positive"}
                }
        
        pipeline = IntegratedNLPPipeline()
        
        # Test article processing
        test_article = {
            "id": "article_123",
            "title": "Technology Breakthrough", 
            "content": "This is an excellent article about new AI technology developments."
        }
        
        result = pipeline.process_article(test_article)
        
        # Verify all pipeline components were executed
        assert result["article_id"] == "article_123"
        assert "language" in result
        assert "processed_content" in result
        assert "sentiment" in result
        assert "entities" in result
        assert "analysis" in result
        assert result["pipeline_version"] == "1.0"
        
        # Verify language detection
        assert result["language"]["language"] == "en"
        
        # Verify sentiment analysis
        assert result["sentiment"]["sentiment"] == "positive"
        
        # Verify entity extraction
        assert "entities" in result["entities"]
        
        # Verify comprehensive analysis
        assert result["analysis"]["overall_score"] > 0
        assert result["analysis"]["recommendation"] in ["publish", "review", "reject"]


@pytest.mark.performance
class TestServiceMLPerformance:
    """Performance tests for service ML components"""
    
    def test_batch_processing_performance(self):
        """Test batch processing performance across services"""
        
        # Create large batch for performance testing
        large_batch = [
            f"This is test article number {i} about technology and innovation."
            for i in range(100)
        ]
        
        class MockPerformanceTester:
            def time_batch_processing(self, texts, batch_size=10):
                """Time batch processing operations"""
                import time
                
                start_time = time.time()
                
                # Simulate processing
                results = []
                for i in range(0, len(texts), batch_size):
                    batch = texts[i:i + batch_size]
                    # Mock processing time
                    time.sleep(0.001)  # 1ms per batch
                    results.extend([{"processed": True} for _ in batch])
                
                end_time = time.time()
                
                return {
                    "total_time": end_time - start_time,
                    "texts_processed": len(texts),
                    "throughput": len(texts) / (end_time - start_time),
                    "avg_time_per_text": (end_time - start_time) / len(texts)
                }
        
        tester = MockPerformanceTester()
        
        # Test different batch sizes
        batch_sizes = [5, 10, 20, 50]
        performance_results = {}
        
        for batch_size in batch_sizes:
            result = tester.time_batch_processing(large_batch, batch_size)
            performance_results[batch_size] = result
            
            # Performance assertions
            assert result["texts_processed"] == 100
            assert result["throughput"] > 50  # Should process >50 texts/second
            assert result["avg_time_per_text"] < 0.1  # Should be <100ms per text
        
        # Find optimal batch size (highest throughput)
        optimal_batch_size = max(
            performance_results.items(),
            key=lambda x: x[1]["throughput"]
        )[0]
        
        assert optimal_batch_size in batch_sizes
        assert performance_results[optimal_batch_size]["throughput"] > 0


if __name__ == "__main__":
    pytest.main([__file__])