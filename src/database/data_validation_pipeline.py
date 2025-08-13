"""
Comprehensive Data Validation Pipeline for NeuroNews.

This module implements advanced data validation, cleaning, and quality assurance
for scraped news articles before they are stored in the database.

Issue #21: Set Up Data Validation Pipeline
- Implement duplicate detection before storing articles
- Validate article length, title consistency, and publication date
- Remove HTML artifacts & unnecessary metadata
- Flag potential fake or low-quality news sources
"""

import re
import hashlib
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from urllib.parse import urlparse
from dataclasses import dataclass
import html
import unicodedata

# Set up logging
logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validation process."""
    is_valid: bool
    score: float
    issues: List[str]
    warnings: List[str]
    cleaned_data: Dict[str, Any]
    metadata: Dict[str, Any]


@dataclass
class SourceReputationConfig:
    """Configuration for source reputation scoring."""
    trusted_domains: List[str]
    questionable_domains: List[str]
    banned_domains: List[str]
    reputation_thresholds: Dict[str, float]


class HTMLCleaner:
    """Advanced HTML content cleaner."""
    
    def __init__(self):
        # Common HTML artifacts and patterns to remove
        self.html_patterns = [
            # HTML tags
            re.compile(r'<[^>]+>', re.IGNORECASE),
            # HTML entities
            re.compile(r'&[a-zA-Z0-9#]+;'),
            # JavaScript code blocks
            re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),
            # CSS style blocks
            re.compile(r'<style[^>]*>.*?</style>', re.IGNORECASE | re.DOTALL),
            # HTML comments
            re.compile(r'<!--.*?-->', re.DOTALL),
            # Multiple whitespace/newlines
            re.compile(r'\s+', re.MULTILINE),
            # Common navigation text
            re.compile(r'(Skip to main content|Subscribe now|Sign up|Log in|Advertisement)', re.IGNORECASE),
            # Social media sharing text
            re.compile(r'(Share on Facebook|Tweet|Share on LinkedIn|Pin it)', re.IGNORECASE),
            # Cookie and privacy notices
            re.compile(r'(This website uses cookies|We use cookies|Privacy Policy|Accept all cookies)', re.IGNORECASE),
        ]
        
        # Metadata patterns to remove
        self.metadata_patterns = [
            re.compile(r'Published:\s*\d+.*?ago', re.IGNORECASE),
            re.compile(r'Updated:\s*\d+.*?ago', re.IGNORECASE),
            re.compile(r'Reading time:\s*\d+\s*min', re.IGNORECASE),
            re.compile(r'\d+\s*comments?', re.IGNORECASE),
            re.compile(r'Share this article', re.IGNORECASE),
            re.compile(r'Follow us on', re.IGNORECASE),
        ]
    
    def clean_content(self, content: str) -> str:
        """
        Clean HTML content and remove artifacts.
        
        Args:
            content: Raw content string
            
        Returns:
            Cleaned content string
        """
        if not content:
            return ""
        
        cleaned = content
        
        # Decode HTML entities first
        cleaned = html.unescape(cleaned)
        
        # Remove HTML patterns
        for pattern in self.html_patterns:
            cleaned = pattern.sub(' ', cleaned)
        
        # Remove metadata patterns
        for pattern in self.metadata_patterns:
            cleaned = pattern.sub('', cleaned)
        
        # Normalize unicode characters
        cleaned = unicodedata.normalize('NFKD', cleaned)
        
        # Clean up whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = cleaned.strip()
        
        # Remove leading/trailing punctuation artifacts
        cleaned = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', cleaned)
        
        return cleaned
    
    def clean_title(self, title: str) -> str:
        """
        Clean article title.
        
        Args:
            title: Raw title string
            
        Returns:
            Cleaned title string
        """
        if not title:
            return ""
        
        cleaned = html.unescape(title)
        cleaned = re.sub(r'<[^>]+>', '', cleaned)  # Remove HTML tags
        cleaned = re.sub(r'\s+', ' ', cleaned)     # Normalize whitespace
        cleaned = cleaned.strip()
        
        # Remove common title suffixes
        suffixes = [
            r'\s*-\s*[^-]+\.com$',  # " - website.com"
            r'\s*\|\s*[^|]+$',      # " | website name"
            r'\s*:\s*[^:]+\.com$',  # " : website.com"
        ]
        
        for suffix in suffixes:
            cleaned = re.sub(suffix, '', cleaned, flags=re.IGNORECASE)
        
        return cleaned


class DuplicateDetector:
    """Enhanced duplicate detection with multiple strategies."""
    
    def __init__(self):
        self.url_cache = set()
        self.title_cache = set()
        self.content_hashes = set()
        self.fuzzy_title_cache = set()
    
    def is_duplicate(self, article: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if article is a duplicate.
        
        Args:
            article: Article dictionary
            
        Returns:
            Tuple of (is_duplicate, reason)
        """
        url = article.get('url', '')
        title = article.get('title', '')
        content = article.get('content', '')
        
        # Check URL duplicates
        if url and url in self.url_cache:
            return True, "duplicate_url"
        
        # Check exact title duplicates
        title_normalized = title.lower().strip()
        if title_normalized and title_normalized in self.title_cache:
            return True, "duplicate_title"
        
        # Check content hash duplicates
        if content:
            content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            if content_hash in self.content_hashes:
                return True, "duplicate_content"
            self.content_hashes.add(content_hash)
        
        # Check fuzzy title duplicates (similar titles)
        fuzzy_title = self._create_fuzzy_title(title)
        if fuzzy_title and fuzzy_title in self.fuzzy_title_cache:
            return True, "similar_title"
        
        # Not a duplicate, add to caches
        if url:
            self.url_cache.add(url)
        if title_normalized:
            self.title_cache.add(title_normalized)
        if fuzzy_title:
            self.fuzzy_title_cache.add(fuzzy_title)
        
        return False, "unique"
    
    def _create_fuzzy_title(self, title: str) -> str:
        """Create fuzzy title for similarity matching."""
        if not title:
            return ""
        
        # Remove punctuation and normalize
        fuzzy = re.sub(r'[^\w\s]', '', title.lower())
        fuzzy = re.sub(r'\s+', ' ', fuzzy).strip()
        
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were'}
        words = [w for w in fuzzy.split() if w not in stop_words]
        
        return ' '.join(sorted(words))  # Sort words for better matching


class SourceReputationAnalyzer:
    """Analyzer for source credibility and reputation."""
    
    def __init__(self, config: Optional[SourceReputationConfig] = None):
        self.config = config or self._get_default_config()
    
    def _get_default_config(self) -> SourceReputationConfig:
        """Get default source reputation configuration."""
        return SourceReputationConfig(
            trusted_domains=[
                'reuters.com', 'ap.org', 'bbc.com', 'npr.org', 
                'pbs.org', 'economist.com', 'wsj.com', 'ft.com',
                'bloomberg.com', 'axios.com', 'politico.com'
            ],
            questionable_domains=[
                'dailymail.co.uk', 'nypost.com', 'foxnews.com',
                'breitbart.com', 'infowars.com', 'naturalnews.com'
            ],
            banned_domains=[
                'fakenews.com', 'clickbait.com', 'spam.com'
            ],
            reputation_thresholds={
                'trusted': 0.9,
                'reliable': 0.7,
                'questionable': 0.4,
                'unreliable': 0.2
            }
        )
    
    def analyze_source(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze source reputation and credibility.
        
        Args:
            article: Article dictionary
            
        Returns:
            Source analysis results
        """
        url = article.get('url', '')
        source = article.get('source', '')
        
        if not url:
            return {
                'reputation_score': 0.5,
                'credibility_level': 'unknown',
                'flags': ['missing_url'],
                'domain': None
            }
        
        try:
            domain = urlparse(url).netloc.lower()
        except:
            domain = ''
        
        reputation_score = self._calculate_reputation_score(domain, source)
        credibility_level = self._get_credibility_level(reputation_score)
        flags = self._get_reputation_flags(domain, article)
        
        return {
            'reputation_score': reputation_score,
            'credibility_level': credibility_level,
            'flags': flags,
            'domain': domain
        }
    
    def _calculate_reputation_score(self, domain: str, source: str) -> float:
        """Calculate reputation score for domain/source."""
        score = 0.5  # Default neutral score
        
        # Check trusted domains
        for trusted in self.config.trusted_domains:
            if trusted in domain:
                score = 0.95
                break
        
        # Check questionable domains
        for questionable in self.config.questionable_domains:
            if questionable in domain:
                score = 0.3
                break
        
        # Check banned domains
        for banned in self.config.banned_domains:
            if banned in domain:
                score = 0.1
                break
        
        # Adjust based on domain characteristics
        if '.edu' in domain or '.gov' in domain:
            score = min(score + 0.2, 1.0)
        elif '.org' in domain:
            score = min(score + 0.1, 1.0)
        
        return score
    
    def _get_credibility_level(self, score: float) -> str:
        """Get credibility level from score."""
        thresholds = self.config.reputation_thresholds
        
        if score >= thresholds['trusted']:
            return 'trusted'
        elif score >= thresholds['reliable']:
            return 'reliable'
        elif score >= thresholds['questionable']:
            return 'questionable'
        else:
            return 'unreliable'
    
    def _get_reputation_flags(self, domain: str, article: Dict[str, Any]) -> List[str]:
        """Get reputation warning flags."""
        flags = []
        
        # Check for suspicious patterns
        title = article.get('title', '').lower()
        content = article.get('content', '').lower()
        
        # Clickbait indicators
        clickbait_patterns = [
            r'you won\'t believe',
            r'shocking truth',
            r'doctors hate',
            r'one weird trick',
            r'amazing secret',
            r'\d+ reasons why',
            r'this will blow your mind'
        ]
        
        for pattern in clickbait_patterns:
            if re.search(pattern, title):
                flags.append('clickbait_title')
                break
        
        # Sensationalism indicators
        if re.search(r'[A-Z]{3,}', title):  # Excessive caps
            flags.append('excessive_caps')
        
        if title.count('!') > 2:
            flags.append('excessive_exclamation')
        
        # Content quality indicators
        if content and len(content) < 200:
            flags.append('thin_content')
        
        # Domain reputation flags
        for banned in self.config.banned_domains:
            if banned in domain:
                flags.append('banned_domain')
        
        for questionable in self.config.questionable_domains:
            if questionable in domain:
                flags.append('questionable_source')
        
        return flags


class ContentValidator:
    """Validator for article content quality and consistency."""
    
    def __init__(self):
        self.min_title_length = 10
        self.max_title_length = 200
        self.min_content_length = 100
        self.max_content_length = 50000
        self.min_word_count = 20
    
    def validate_content(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate article content quality.
        
        Args:
            article: Article dictionary
            
        Returns:
            Validation results
        """
        issues = []
        warnings = []
        score = 100.0
        
        title = article.get('title', '')
        content = article.get('content', '')
        url = article.get('url', '')
        published_date = article.get('published_date', '')
        
        # Validate title
        title_result = self._validate_title(title)
        score += title_result['score_adjustment']
        issues.extend(title_result['issues'])
        warnings.extend(title_result['warnings'])
        
        # Validate content
        content_result = self._validate_content_quality(content)
        score += content_result['score_adjustment']
        issues.extend(content_result['issues'])
        warnings.extend(content_result['warnings'])
        
        # Validate URL
        url_result = self._validate_url(url)
        score += url_result['score_adjustment']
        issues.extend(url_result['issues'])
        warnings.extend(url_result['warnings'])
        
        # Validate date
        date_result = self._validate_date(published_date)
        score += date_result['score_adjustment']
        issues.extend(date_result['issues'])
        warnings.extend(date_result['warnings'])
        
        return {
            'validation_score': max(0, min(100, score)),
            'issues': issues,
            'warnings': warnings,
            'is_valid': score >= 50,  # Minimum threshold
            'quality_metrics': {
                'title_length': len(title),
                'content_length': len(content),
                'word_count': len(content.split()) if content else 0,
                'reading_time': max(1, len(content.split()) // 200) if content else 0
            }
        }
    
    def _validate_title(self, title: str) -> Dict[str, Any]:
        """Validate article title."""
        issues = []
        warnings = []
        score_adjustment = 0
        
        if not title:
            issues.append("missing_title")
            score_adjustment -= 25
        else:
            title_len = len(title)
            
            if title_len < self.min_title_length:
                issues.append("title_too_short")
                score_adjustment -= 15
            elif title_len > self.max_title_length:
                warnings.append("title_very_long")
                score_adjustment -= 5
            
            # Check for title quality
            if title.isupper():
                warnings.append("title_all_caps")
                score_adjustment -= 5
            
            if title.count('?') > 3:
                warnings.append("excessive_question_marks")
                score_adjustment -= 5
        
        return {
            'score_adjustment': score_adjustment,
            'issues': issues,
            'warnings': warnings
        }
    
    def _validate_content_quality(self, content: str) -> Dict[str, Any]:
        """Validate content quality."""
        issues = []
        warnings = []
        score_adjustment = 0
        
        if not content:
            issues.append("missing_content")
            score_adjustment -= 30
        else:
            content_len = len(content)
            word_count = len(content.split())
            
            if content_len < self.min_content_length:
                issues.append("content_too_short")
                score_adjustment -= 20
            elif content_len > self.max_content_length:
                warnings.append("content_very_long")
                score_adjustment -= 5
            
            if word_count < self.min_word_count:
                issues.append("insufficient_word_count")
                score_adjustment -= 15
            
            # Check content quality indicators
            if content.count('\n') / len(content) > 0.1:
                warnings.append("excessive_line_breaks")
                score_adjustment -= 5
            
            # Check for placeholder content
            placeholder_patterns = [
                'lorem ipsum', 'placeholder', 'coming soon',
                'under construction', 'page not found'
            ]
            
            for pattern in placeholder_patterns:
                if pattern in content.lower():
                    issues.append("placeholder_content")
                    score_adjustment -= 20
                    break
        
        return {
            'score_adjustment': score_adjustment,
            'issues': issues,
            'warnings': warnings
        }
    
    def _validate_url(self, url: str) -> Dict[str, Any]:
        """Validate URL format and accessibility."""
        issues = []
        warnings = []
        score_adjustment = 0
        
        if not url:
            issues.append("missing_url")
            score_adjustment -= 20
        else:
            try:
                parsed = urlparse(url)
                if not parsed.scheme:
                    issues.append("invalid_url_scheme")
                    score_adjustment -= 10
                
                if not parsed.netloc:
                    issues.append("invalid_url_domain")
                    score_adjustment -= 10
                
                # Check for suspicious URL patterns
                if 'bit.ly' in url or 'tinyurl' in url:
                    warnings.append("shortened_url")
                    score_adjustment -= 5
                
            except Exception:
                issues.append("malformed_url")
                score_adjustment -= 15
        
        return {
            'score_adjustment': score_adjustment,
            'issues': issues,
            'warnings': warnings
        }
    
    def _validate_date(self, published_date: str) -> Dict[str, Any]:
        """Validate publication date."""
        issues = []
        warnings = []
        score_adjustment = 0
        
        if not published_date:
            warnings.append("missing_date")
            score_adjustment -= 5
        else:
            try:
                # Try to parse the date
                if 'T' in published_date:
                    date_obj = datetime.fromisoformat(published_date.replace('Z', '+00:00'))
                else:
                    date_obj = datetime.strptime(published_date, '%Y-%m-%d')
                
                # Check if date is reasonable
                now = datetime.now()
                if date_obj > now:
                    warnings.append("future_date")
                    score_adjustment -= 10
                elif date_obj < now - timedelta(days=365*5):  # More than 5 years old
                    warnings.append("very_old_article")
                    score_adjustment -= 5
                
            except Exception:
                issues.append("invalid_date_format")
                score_adjustment -= 10
        
        return {
            'score_adjustment': score_adjustment,
            'issues': issues,
            'warnings': warnings
        }


class DataValidationPipeline:
    """
    Comprehensive data validation pipeline for news articles.
    
    This pipeline implements all requirements from Issue #21:
    - Duplicate detection before storing articles
    - Article length, title consistency, and publication date validation
    - HTML artifacts and unnecessary metadata removal
    - Fake or low-quality news source flagging
    """
    
    def __init__(self, config: Optional[SourceReputationConfig] = None):
        self.html_cleaner = HTMLCleaner()
        self.duplicate_detector = DuplicateDetector()
        self.source_analyzer = SourceReputationAnalyzer(config)
        self.content_validator = ContentValidator()
        
        self.processed_count = 0
        self.rejected_count = 0
        self.warnings_count = 0
        
        logger.info("Data validation pipeline initialized")
    
    def process_article(self, article: Dict[str, Any]) -> Optional[ValidationResult]:
        """
        Process a single article through the validation pipeline.
        
        Args:
            article: Raw article dictionary
            
        Returns:
            ValidationResult if article passes validation, None if rejected
        """
        self.processed_count += 1
        
        try:
            # Step 1: Clean HTML and remove artifacts
            cleaned_article = self._clean_article(article)
            
            # Step 2: Check for duplicates
            is_duplicate, duplicate_reason = self.duplicate_detector.is_duplicate(cleaned_article)
            if is_duplicate:
                logger.info(f"Article rejected - {duplicate_reason}: {cleaned_article.get('url', 'Unknown URL')}")
                self.rejected_count += 1
                return None
            
            # Step 3: Validate content quality
            content_validation = self.content_validator.validate_content(cleaned_article)
            
            # Step 4: Analyze source reputation
            source_analysis = self.source_analyzer.analyze_source(cleaned_article)
            
            # Step 5: Calculate overall validation score
            overall_score = self._calculate_overall_score(content_validation, source_analysis)
            
            # Step 6: Determine if article passes validation
            all_issues = content_validation['issues'] + source_analysis['flags']
            all_warnings = content_validation['warnings']
            
            is_valid = overall_score >= 50 and not any(
                issue in ['missing_title', 'missing_content', 'banned_domain'] 
                for issue in all_issues
            )
            
            if not is_valid:
                logger.warning(f"Article failed validation (score: {overall_score:.1f}): {cleaned_article.get('url', 'Unknown URL')}")
                self.rejected_count += 1
                return None
            
            if all_warnings:
                self.warnings_count += 1
            
            # Step 7: Add validation metadata
            validated_article = self._add_validation_metadata(
                cleaned_article, content_validation, source_analysis, overall_score
            )
            
            logger.debug(f"Article validated successfully (score: {overall_score:.1f}): {validated_article.get('url', 'Unknown URL')}")
            
            return ValidationResult(
                is_valid=True,
                score=overall_score,
                issues=all_issues,
                warnings=all_warnings,
                cleaned_data=validated_article,
                metadata={
                    'content_validation': content_validation,
                    'source_analysis': source_analysis,
                    'processing_timestamp': datetime.now().isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"Error processing article {article.get('url', 'Unknown URL')}: {e}")
            self.rejected_count += 1
            return None
    
    def _clean_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """Clean article content and metadata."""
        cleaned = article.copy()
        
        # Clean title
        if 'title' in cleaned:
            cleaned['title'] = self.html_cleaner.clean_title(cleaned['title'])
        
        # Clean content
        if 'content' in cleaned:
            cleaned['content'] = self.html_cleaner.clean_content(cleaned['content'])
        
        # Clean author
        if 'author' in cleaned:
            author = cleaned['author']
            if author:
                cleaned['author'] = re.sub(r'<[^>]+>', '', author).strip()
        
        # Normalize source name
        if 'source' in cleaned:
            source = cleaned['source']
            if source:
                cleaned['source'] = re.sub(r'[^\w\s]', '', source).strip().title()
        
        # Remove unnecessary metadata fields
        metadata_to_remove = [
            'scraped_at', 'raw_html', 'response_headers',
            'cookies', 'request_info', 'debug_info'
        ]
        for field in metadata_to_remove:
            cleaned.pop(field, None)
        
        return cleaned
    
    def _calculate_overall_score(self, content_validation: Dict, source_analysis: Dict) -> float:
        """Calculate overall validation score."""
        content_score = content_validation['validation_score']
        reputation_score = source_analysis['reputation_score'] * 100
        
        # Weighted average: content quality (70%) + source reputation (30%)
        overall_score = (content_score * 0.7) + (reputation_score * 0.3)
        
        return overall_score
    
    def _add_validation_metadata(self, article: Dict, content_validation: Dict, 
                                source_analysis: Dict, overall_score: float) -> Dict[str, Any]:
        """Add validation metadata to article."""
        validated = article.copy()
        
        # Add validation scores
        validated['validation_score'] = overall_score
        validated['content_validation_score'] = content_validation['validation_score']
        validated['source_reputation_score'] = source_analysis['reputation_score']
        
        # Add quality metrics
        validated.update(content_validation['quality_metrics'])
        
        # Add source metadata
        validated['source_credibility'] = source_analysis['credibility_level']
        validated['source_domain'] = source_analysis['domain']
        
        # Add validation timestamp
        validated['validated_at'] = datetime.now().isoformat()
        
        # Determine overall quality rating
        if overall_score >= 80:
            validated['content_quality'] = 'high'
        elif overall_score >= 60:
            validated['content_quality'] = 'medium'
        else:
            validated['content_quality'] = 'low'
        
        # Add flags if any issues found
        all_flags = content_validation['issues'] + source_analysis['flags']
        if all_flags:
            validated['validation_flags'] = all_flags
        
        return validated
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get processing statistics."""
        return {
            'processed_count': self.processed_count,
            'rejected_count': self.rejected_count,
            'accepted_count': self.processed_count - self.rejected_count,
            'warnings_count': self.warnings_count,
            'rejection_rate': (self.rejected_count / self.processed_count * 100) if self.processed_count > 0 else 0,
            'acceptance_rate': ((self.processed_count - self.rejected_count) / self.processed_count * 100) if self.processed_count > 0 else 0
        }
    
    def reset_statistics(self):
        """Reset processing statistics."""
        self.processed_count = 0
        self.rejected_count = 0
        self.warnings_count = 0


def main():
    """Test the data validation pipeline."""
    # Example usage
    pipeline = DataValidationPipeline()
    
    # Test article
    test_article = {
        'title': 'Sample News Article <span>with HTML</span>',
        'content': '<p>This is a test article content with <b>HTML tags</b> and some metadata to be cleaned.</p><!-- comment -->',
        'url': 'https://reuters.com/test-article',
        'source': 'Reuters',
        'author': 'John Doe',
        'published_date': '2024-03-15T10:30:00Z'
    }
    
    result = pipeline.process_article(test_article)
    
    if result:
        print("✅ Article validated successfully!")
        print(f"Score: {result.score:.1f}")
        print(f"Quality: {result.cleaned_data.get('content_quality', 'unknown')}")
        if result.warnings:
            print(f"Warnings: {result.warnings}")
    else:
        print("❌ Article rejected")
    
    print(f"\nPipeline Statistics: {pipeline.get_statistics()}")


if __name__ == '__main__':
    main()
