"""
Language detection and processing utilities for multi-language news articles.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
import re
from collections import Counter
import json
import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


class LanguageDetector:
    """Detects language of text using multiple methods."""
    
    # Common words for language detection (basic heuristic approach)
    LANGUAGE_PATTERNS = {
        'en': {
            'common_words': {'the', 'and', 'is', 'in', 'to', 'of', 'a', 'that', 'it', 'with', 'for', 'as', 'was', 'on', 'are', 'you'},
            'patterns': [r'\bthe\b', r'\band\b', r'\bof\b', r'\bto\b', r'\ba\b']
        },
        'es': {
            'common_words': {'el', 'la', 'de', 'que', 'y', 'a', 'en', 'un', 'es', 'se', 'no', 'te', 'lo', 'le', 'da', 'su'},
            'patterns': [r'\bel\b', r'\bla\b', r'\bde\b', r'\bque\b', r'\by\b']
        },
        'fr': {
            'common_words': {'le', 'de', 'et', 'à', 'un', 'il', 'être', 'et', 'en', 'avoir', 'que', 'pour', 'dans', 'ce', 'son', 'une'},
            'patterns': [r'\ble\b', r'\bde\b', r'\bet\b', r'\bà\b', r'\bun\b']
        },
        'de': {
            'common_words': {'der', 'die', 'und', 'in', 'den', 'von', 'zu', 'das', 'mit', 'sich', 'des', 'auf', 'für', 'ist', 'im', 'dem'},
            'patterns': [r'\bder\b', r'\bdie\b', r'\bund\b', r'\bdas\b', r'\bden\b']
        },
        'zh': {
            'common_words': {'的', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你'},
            'patterns': [r'的', r'是', r'在', r'我', r'有']
        },
        'ja': {
            'common_words': {'の', 'に', 'は', 'を', 'た', 'が', 'で', 'て', 'と', 'し', 'れ', 'さ', 'ある', 'いる', 'する', 'です', 'ます'},
            'patterns': [r'の', r'に', r'は', r'を', r'た']
        },
        'ru': {
            'common_words': {'в', 'и', 'не', 'что', 'он', 'на', 'я', 'с', 'со', 'как', 'а', 'то', 'все', 'она', 'так', 'его'},
            'patterns': [r'\bв\b', r'\bи\b', r'\bне\b', r'\bчто\b', r'\bна\b']
        },
        'ar': {
            'common_words': {'في', 'من', 'إلى', 'على', 'هذا', 'هذه', 'التي', 'الذي', 'كان', 'كانت', 'لكن', 'أن', 'قد', 'لا', 'ما', 'كل'},
            'patterns': [r'في', r'من', r'إلى', r'على', r'هذا']
        },
        'pt': {
            'common_words': {'o', 'de', 'a', 'e', 'do', 'da', 'em', 'um', 'para', 'com', 'não', 'uma', 'os', 'no', 'se', 'na'},
            'patterns': [r'\bo\b', r'\bde\b', r'\ba\b', r'\be\b', r'\bdo\b']
        },
        'it': {
            'common_words': {'il', 'di', 'che', 'e', 'la', 'per', 'un', 'in', 'con', 'del', 'da', 'a', 'al', 'le', 'si', 'dei'},
            'patterns': [r'\bil\b', r'\bdi\b', r'\bche\b', r'\be\b', r'\bla\b']
        }
    }
    
    def __init__(self, fallback_language: str = 'en'):
        """
        Initialize language detector.
        
        Args:
            fallback_language: Language to use when detection fails
        """
        self.fallback_language = fallback_language
        
    def detect_language(self, text: str, min_length: int = 50) -> Dict[str, Any]:
        """
        Detect the language of the given text.
        
        Args:
            text: Text to analyze
            min_length: Minimum text length for reliable detection
            
        Returns:
            Dictionary with language detection results
        """
        if not text or len(text.strip()) < min_length:
            logger.warning(f"Text too short for reliable language detection: {len(text)} chars")
            return {
                'language': 'unknown',
                'confidence': 0.0,
                'method': 'fallback',
                'reason': 'text_too_short'
            }
            
        # Clean text for analysis
        clean_text = self._clean_text(text)
        words = clean_text.lower().split()
        
        if len(words) < 5:
            logger.warning("Too few words for reliable language detection")
            return {
                'language': 'unknown',
                'confidence': 0.0,
                'method': 'fallback',
                'reason': 'insufficient_words'
            }
            
        # Score each language
        language_scores = {}
        
        for lang_code, lang_data in self.LANGUAGE_PATTERNS.items():
            score = self._calculate_language_score(words, lang_data)
            language_scores[lang_code] = score
            
        # Find the best match
        if not language_scores:
            return {
                'language': self.fallback_language,
                'confidence': 0.5,
                'method': 'fallback',
                'reason': 'no_matches'
            }
            
        best_language = max(language_scores, key=language_scores.get)
        confidence = language_scores[best_language]
        
        # If confidence is too low, still return the best guess but mark as low confidence
        if confidence < 0.1:
            logger.warning(f"Low confidence language detection: {confidence}")
            return {
                'language': 'unknown',
                'confidence': confidence,
                'method': 'pattern_based',
                'reason': 'low_confidence',
                'best_guess': best_language
            }
            
        logger.info(f"Detected language: {best_language} (confidence: {confidence:.2f})")
        return {
            'language': best_language,
            'confidence': confidence,
            'method': 'pattern_based',
            'all_scores': language_scores
        }
        
    def _clean_text(self, text: str) -> str:
        """Clean text for language detection."""
        # Remove URLs, emails, numbers, special characters
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        text = re.sub(r'\S+@\S+', '', text)
        text = re.sub(r'\d+', '', text)
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
        
    def _calculate_language_score(self, words: List[str], lang_data: Dict) -> float:
        """Calculate language match score based on common words and patterns."""
        common_words = lang_data['common_words']
        patterns = lang_data['patterns']
        
        # Word-based matching
        word_matches = sum(1 for word in words if word in common_words)
        word_score = word_matches / len(words) if words else 0
        
        # Pattern-based matching for character detection
        pattern_score = 0
        text = ' '.join(words)
        for pattern in patterns:
            matches = len(re.findall(pattern, text, re.IGNORECASE))
            pattern_score += matches
        
        # Normalize pattern score
        pattern_score = min(pattern_score / len(words), 1.0) if words else 0
        
        # Character-based detection for non-Latin scripts
        char_score = 0
        if lang_data['common_words']:
            sample_word = next(iter(lang_data['common_words']))
            
            # Check for Chinese characters
            if re.search(r'[\u4e00-\u9fff]', sample_word):
                chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
                total_chars = len(re.sub(r'\s', '', text))
                char_score = chinese_chars / total_chars if total_chars > 0 else 0
                
            # Check for Japanese characters (Hiragana, Katakana, Kanji)
            elif re.search(r'[\u3040-\u309f\u30a0-\u30ff]', sample_word):
                japanese_chars = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', text))
                total_chars = len(re.sub(r'\s', '', text))
                char_score = japanese_chars / total_chars if total_chars > 0 else 0
                
            # Check for Cyrillic characters (Russian)
            elif re.search(r'[а-яёА-ЯЁ]', sample_word):
                cyrillic_chars = len(re.findall(r'[а-яёА-ЯЁ]', text))
                total_chars = len(re.sub(r'\s', '', text))
                char_score = cyrillic_chars / total_chars if total_chars > 0 else 0
                
            # Check for Arabic characters
            elif re.search(r'[\u0600-\u06ff]', sample_word):
                arabic_chars = len(re.findall(r'[\u0600-\u06ff]', text))
                total_chars = len(re.sub(r'\s', '', text))
                char_score = arabic_chars / total_chars if total_chars > 0 else 0
        
        # Combine scores with weights
        if char_score > 0:
            # For non-Latin scripts, prioritize character-based detection
            combined_score = 0.7 * char_score + 0.2 * word_score + 0.1 * pattern_score
        else:
            # For Latin scripts, prioritize word and pattern matching
            combined_score = 0.6 * word_score + 0.4 * pattern_score
        
        return combined_score
        
    def get_supported_languages(self) -> List[str]:
        """Get list of supported language codes."""
        return list(self.LANGUAGE_PATTERNS.keys())


class AWSTranslateService:
    """AWS Translate service wrapper for translating text."""
    
    def __init__(self, 
                 region_name: str = 'us-east-1',
                 aws_access_key_id: Optional[str] = None,
                 aws_secret_access_key: Optional[str] = None):
        """
        Initialize AWS Translate service.
        
        Args:
            region_name: AWS region
            aws_access_key_id: AWS access key ID
            aws_secret_access_key: AWS secret access key
        """
        self.region_name = region_name
        
        # Initialize AWS session
        session_kwargs = {'region_name': region_name}
        if aws_access_key_id and aws_secret_access_key:
            session_kwargs.update({
                'aws_access_key_id': aws_access_key_id,
                'aws_secret_access_key': aws_secret_access_key
            })
            
        self.session = boto3.Session(**session_kwargs)
        self.translate_client = self.session.client('translate')
        
        # Translation cache to avoid redundant translations
        self._translation_cache = {}
        
    def translate_text(self, 
                      text: str, 
                      source_language: str, 
                      target_language: str = 'en',
                      max_length: int = 5000) -> Dict[str, Any]:
        """
        Translate text from source to target language.
        
        Args:
            text: Text to translate
            source_language: Source language code
            target_language: Target language code
            max_length: Maximum text length for translation
            
        Returns:
            Dict containing translation result and metadata
        """
        if not text or not text.strip():
            return {
                'translated_text': '',
                'source_language': source_language,
                'target_language': target_language,
                'confidence': 0.0,
                'error': 'Empty text provided'
            }
            
        # Don't translate if already in target language
        if source_language == target_language:
            return {
                'translated_text': text,
                'source_language': source_language,
                'target_language': target_language,
                'confidence': 1.0,
                'error': None
            }
            
        # Check cache first
        cache_key = f"{source_language}:{target_language}:{hash(text[:100])}"
        if cache_key in self._translation_cache:
            logger.info("Using cached translation")
            return self._translation_cache[cache_key]
            
        # Truncate text if too long
        if len(text) > max_length:
            logger.warning(f"Text truncated from {len(text)} to {max_length} characters")
            text = text[:max_length]
            
        try:
            response = self.translate_client.translate_text(
                Text=text,
                SourceLanguageCode=source_language,
                TargetLanguageCode=target_language
            )
            
            result = {
                'translated_text': response['TranslatedText'],
                'source_language': response['SourceLanguageCode'],
                'target_language': response['TargetLanguageCode'],
                'confidence': 1.0,  # AWS doesn't provide confidence score
                'error': None
            }
            
            # Cache successful translation
            self._translation_cache[cache_key] = result
            
            logger.info(f"Successfully translated text from {source_language} to {target_language}")
            return result
            
        except (BotoCoreError, ClientError, Exception) as e:
            error_msg = f"AWS Translate error: {str(e)}"
            logger.error(error_msg)
            return {
                'translated_text': text,  # Return original text on error
                'source_language': source_language,
                'target_language': target_language,
                'confidence': 0.0,
                'error': error_msg
            }
            
    def get_supported_languages(self) -> List[str]:
        """Get list of supported language codes from AWS Translate."""
        try:
            response = self.translate_client.list_languages()
            return [lang['LanguageCode'] for lang in response['Languages']]
        except (BotoCoreError, ClientError) as e:
            logger.error(f"Error fetching supported languages: {e}")
            return ['en', 'es', 'fr', 'de', 'zh', 'ja', 'ru', 'ar', 'pt', 'it']  # Fallback list
            
    def detect_language(self, text: str) -> Dict[str, Any]:
        """
        Use AWS Comprehend to detect language (as alternative to local detection).
        
        Args:
            text: Text to analyze
            
        Returns:
            Dict containing detection result
        """
        try:
            comprehend_client = self.session.client('comprehend')
            response = comprehend_client.detect_dominant_language(Text=text[:5000])  # Comprehend limit
            
            if response['Languages']:
                best_match = max(response['Languages'], key=lambda x: x['Score'])
                return {
                    'language_code': best_match['LanguageCode'],
                    'confidence': best_match['Score'],
                    'error': None
                }
            else:
                return {
                    'language_code': 'en',
                    'confidence': 0.5,
                    'error': 'No language detected'
                }
                
        except (BotoCoreError, ClientError) as e:
            error_msg = f"AWS Comprehend error: {str(e)}"
            logger.error(error_msg)
            return {
                'language_code': 'en',
                'confidence': 0.5,
                'error': error_msg
            }


class TranslationQualityChecker:
    """Checks translation quality using various heuristics."""
    
    def __init__(self):
        """Initialize translation quality checker."""
        pass
    
    def assess_translation_quality(self, 
                                 original_text: str, 
                                 translated_text: str,
                                 source_language: str,
                                 target_language: str) -> Dict[str, any]:
        """
        Assess the quality of a translation using various metrics.
        This is an alias for check_translation_quality for backward compatibility.
        
        Args:
            original_text: Original text
            translated_text: Translated text
            source_language: Source language code
            target_language: Target language code
            
        Returns:
            Dict containing quality metrics with overall_score key
        """
        result = self.check_translation_quality(original_text, translated_text, source_language, target_language)
        # Add overall_score as an alias for quality_score
        result['overall_score'] = result.get('quality_score', 0.0)
        
        # Check if length ratio is within acceptable bounds
        length_ratio = result.get('length_ratio', 0.0)
        expected_ratios = {
            ('en', 'es'): (0.8, 1.3),
            ('en', 'fr'): (0.9, 1.4),
            ('en', 'de'): (0.7, 1.2),
            ('en', 'zh'): (0.3, 0.7),
            ('zh', 'en'): (1.4, 3.0),
            ('ja', 'en'): (1.2, 2.5),
        }
        
        lang_pair = (source_language, target_language)
        if lang_pair in expected_ratios:
            min_ratio, max_ratio = expected_ratios[lang_pair]
            result['length_ratio_ok'] = min_ratio <= length_ratio <= max_ratio
        else:
            # For unknown language pairs, use a more lenient check
            result['length_ratio_ok'] = 0.3 <= length_ratio <= 3.0
            
        return result
        
    def check_translation_quality(self, 
                                 original_text: str, 
                                 translated_text: str,
                                 source_language: str,
                                 target_language: str) -> Dict[str, any]:
        """
        Check the quality of a translation using various metrics.
        
        Args:
            original_text: Original text
            translated_text: Translated text
            source_language: Source language code
            target_language: Target language code
            
        Returns:
            Dict containing quality metrics
        """
        if not original_text or not translated_text:
            return {
                'quality_score': 0.0,
                'length_ratio': 0.0,
                'issues': ['Empty text provided'],
                'recommendations': ['Provide valid text for translation']
            }
            
        issues = []
        recommendations = []
        
        # Length ratio check
        length_ratio = len(translated_text) / len(original_text) if original_text else 0
        
        # Typical length ratios for different language pairs
        expected_ratios = {
            ('en', 'es'): (0.8, 1.3),
            ('en', 'fr'): (0.9, 1.4),
            ('en', 'de'): (0.7, 1.2),
            ('en', 'zh'): (0.3, 0.7),
            ('zh', 'en'): (1.4, 3.0),
            ('ja', 'en'): (1.2, 2.5),
        }
        
        # Check if length ratio is reasonable
        lang_pair = (source_language, target_language)
        if lang_pair in expected_ratios:
            min_ratio, max_ratio = expected_ratios[lang_pair]
            if length_ratio < min_ratio:
                issues.append(f"Translation too short (ratio: {length_ratio:.2f})")
                recommendations.append("Check for truncated translation")
            elif length_ratio > max_ratio:
                issues.append(f"Translation too long (ratio: {length_ratio:.2f})")
                recommendations.append("Check for repeated or expanded content")
                
        # Check for untranslated content (same text)
        if original_text.strip() == translated_text.strip():
            issues.append("No translation occurred")
            recommendations.append("Verify source and target languages are different")
            
        # Check for common translation errors
        if self._has_encoding_issues(translated_text):
            issues.append("Potential encoding issues detected")
            recommendations.append("Check text encoding and character support")
            
        # Calculate overall quality score
        quality_score = self._calculate_quality_score(length_ratio, issues, lang_pair)
        
        return {
            'quality_score': quality_score,
            'length_ratio': length_ratio,
            'issues': issues,
            'recommendations': recommendations,
            'character_count_original': len(original_text),
            'character_count_translated': len(translated_text),
            'word_count_original': len(original_text.split()),
            'word_count_translated': len(translated_text.split())
        }
        
    def _has_encoding_issues(self, text: str) -> bool:
        """Check for common encoding issues in translated text."""
        # Look for replacement characters or common encoding problems
        encoding_indicators = ['�', '????', '\\x', '\\u']
        return any(indicator in text for indicator in encoding_indicators)
        
    def _calculate_quality_score(self, length_ratio: float, issues: List[str], lang_pair: Tuple[str, str]) -> float:
        """Calculate overall quality score based on various factors."""
        base_score = 1.0
        
        # Penalize for issues (more aggressive penalty)
        issue_penalty = len(issues) * 0.3
        base_score -= issue_penalty
        
        # More aggressive length ratio penalty for very poor translations
        if length_ratio < 0.2:  # Very short translation
            base_score *= 0.2
        elif length_ratio < 0.3:  # Short translation
            base_score *= 0.4
        elif length_ratio > 5.0:  # Very long translation
            base_score *= 0.3
        elif length_ratio > 3.0:  # Long translation
            base_score *= 0.5
        else:
            # Moderate length ratio adjustment for normal cases
            if lang_pair in [('en', 'zh'), ('zh', 'en'), ('en', 'ja'), ('ja', 'en')]:
                # More lenient for languages with different writing systems
                length_penalty = max(0, abs(length_ratio - 1.0) - 1.0) * 0.1
            else:
                length_penalty = max(0, abs(length_ratio - 1.0) - 0.5) * 0.15
            base_score -= length_penalty
        
        return max(0.0, min(1.0, base_score))
