"""
Tests for Article Normalization Module
Issue #229: Chunking & normalization pipeline

Tests cover HTML normalization, metadata extraction, edge cases,
and various content formats.
"""

import pytest
from datetime import datetime
from services.rag.normalization import ArticleNormalizer, normalize_article


class TestArticleNormalizer:
    """Test suite for ArticleNormalizer class."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.normalizer = ArticleNormalizer()
    
    def test_empty_content(self):
        """Test handling of empty content."""
        result = self.normalizer.normalize_article("")
        assert result['content'] == ''
        assert result['word_count'] == 0
        assert result['char_count'] == 0
        assert result['title'] == ''
    
    def test_none_content(self):
        """Test handling of None content."""
        result = self.normalizer.normalize_article(None)
        assert result['content'] == ''
        assert result['word_count'] == 0
    
    def test_plain_text_normalization(self):
        """Test normalization of plain text."""
        text = "This is a test article.\n\nIt has multiple paragraphs.\nWith some interesting content."
        result = self.normalizer.normalize_article(text)
        
        assert 'test article' in result['content']
        assert result['word_count'] > 0
        assert result['char_count'] > 0
        assert result['language'] in ['en', 'unknown']  # Depends on langdetect availability
    
    def test_html_normalization(self):
        """Test HTML content normalization."""
        html = """
        <html>
        <head><title>Test Article Title</title></head>
        <body>
            <article>
                <h1>Main Title</h1>
                <p class="byline">By John Doe</p>
                <time datetime="2024-01-15T10:30:00">January 15, 2024</time>
                <p>This is the first paragraph of the article.</p>
                <p>This is the second paragraph with more content.</p>
            </article>
        </body>
        </html>
        """
        
        result = self.normalizer.normalize_article(html)
        
        assert 'Test Article Title' in result['title'] or 'Main Title' in result['title']
        assert 'John Doe' in result['byline']
        assert 'first paragraph' in result['content']
        assert 'second paragraph' in result['content']
        assert result['timestamp'] is not None
    
    def test_html_with_unwanted_elements(self):
        """Test HTML normalization with scripts, styles, etc."""
        html = """
        <html>
        <head>
            <title>Clean Title</title>
            <script>var x = 1;</script>
            <style>body { color: red; }</style>
        </head>
        <body>
            <nav>Navigation content</nav>
            <header>Header content</header>
            <article>
                <p>Main article content that should be preserved.</p>
            </article>
            <footer>Footer content</footer>
        </body>
        </html>
        """
        
        result = self.normalizer.normalize_article(html)
        
        assert 'Main article content' in result['content']
        assert 'var x = 1' not in result['content']
        assert 'color: red' not in result['content']
        assert 'Navigation content' not in result['content']
        assert 'Footer content' not in result['content']
    
    def test_metadata_extraction(self):
        """Test metadata extraction from HTML."""
        html = """
        <html>
        <head>
            <title>Article Title</title>
            <meta name="author" content="Jane Smith">
            <meta name="published" content="2024-02-20">
            <link rel="canonical" href="https://example.com/article">
        </head>
        <body>
            <article>
                <p>Article content here.</p>
            </article>
        </body>
        </html>
        """
        
        result = self.normalizer.normalize_article(html)
        
        assert result['title'] == 'Article Title'
        assert result['byline'] == 'Jane Smith'
        assert result['url'] == 'https://example.com/article'
        assert result['timestamp'] is not None
    
    def test_datetime_parsing(self):
        """Test various datetime format parsing."""
        test_cases = [
            ('2024-01-15T10:30:00', datetime),
            ('2024-01-15', datetime),
            ('January 15, 2024', datetime),
            ('Jan 15, 2024', datetime),
            ('15/01/2024', datetime),
            ('01/15/2024', datetime),
            ('invalid date', type(None)),
        ]
        
        for date_str, expected_type in test_cases:
            result = self.normalizer._parse_datetime(date_str)
            assert isinstance(result, expected_type), f"Failed for {date_str}"
    
    def test_text_cleaning(self):
        """Test text cleaning functionality."""
        dirty_text = """
        This  has   multiple    spaces.
        
        
        It also has multiple newlines.
        
        
        And some URLs: https://example.com and emails: test@example.com
        """
        
        cleaned = self.normalizer._clean_text(dirty_text)
        
        assert '   ' not in cleaned  # Multiple spaces removed
        assert 'https://example.com' not in cleaned  # URLs removed
        assert 'test@example.com' not in cleaned  # Emails removed
        assert 'multiple spaces' in cleaned
        assert 'multiple newlines' in cleaned
    
    def test_preserve_paragraphs(self):
        """Test paragraph preservation option."""
        html = """
        <article>
            <p>First paragraph.</p>
            <p>Second paragraph.</p>
            <p>Third paragraph.</p>
        </article>
        """
        
        # Test with paragraph preservation
        normalizer_preserve = ArticleNormalizer(preserve_paragraphs=True)
        result_preserve = normalizer_preserve.normalize_article(html)
        
        # Test without paragraph preservation
        normalizer_no_preserve = ArticleNormalizer(preserve_paragraphs=False)
        result_no_preserve = normalizer_no_preserve.normalize_article(html)
        
        # Should have more structure with preservation
        assert result_preserve['content'].count('\n') >= result_no_preserve['content'].count('\n')
    
    def test_min_paragraph_length(self):
        """Test minimum paragraph length filtering."""
        html = """
        <article>
            <p>This is a long paragraph that should be included because it meets the minimum length requirement.</p>
            <p>Short.</p>
            <p>Another long paragraph that provides substantial content and should also be included in the final result.</p>
        </article>
        """
        
        normalizer = ArticleNormalizer(min_paragraph_length=20)
        result = normalizer.normalize_article(html)
        
        assert 'long paragraph' in result['content']
        assert 'Short.' not in result['content']  # Too short, should be filtered
    
    def test_metadata_override(self):
        """Test metadata override functionality."""
        text = "Simple article content."
        metadata = {
            'title': 'Override Title',
            'byline': 'Override Author',
            'url': 'https://override.com',
            'custom_field': 'custom_value'
        }
        
        result = self.normalizer.normalize_article(text, metadata)
        
        assert result['title'] == 'Override Title'
        assert result['byline'] == 'Override Author'
        assert result['url'] == 'https://override.com'
        assert result['metadata']['custom_field'] == 'custom_value'
    
    def test_edge_case_very_long_title(self):
        """Test handling of very long titles."""
        long_title = "A" * 500 + " Very Long Title"
        text = f"{long_title}\n\nThis is the article content."
        
        result = self.normalizer.normalize_article(text)
        
        # Long first line should not be treated as title
        assert result['title'] != long_title
        assert 'article content' in result['content']
    
    def test_edge_case_no_content_paragraphs(self):
        """Test HTML with empty paragraphs."""
        html = """
        <article>
            <p></p>
            <p>   </p>
            <p>Actual content here.</p>
            <p></p>
        </article>
        """
        
        result = self.normalizer.normalize_article(html)
        
        assert 'Actual content here' in result['content']
        assert result['content'].strip() == 'Actual content here.'
    
    def test_edge_case_code_blocks(self):
        """Test handling of code blocks in content."""
        html = """
        <article>
            <p>Here's some code:</p>
            <pre><code>
def hello_world():
    print("Hello, world!")
    return True
            </code></pre>
            <p>And more regular content.</p>
        </article>
        """
        
        normalizer = ArticleNormalizer(min_paragraph_length=5)  # Lower threshold
        result = normalizer.normalize_article(html)
        
        assert "Here's some code" in result['content']
        assert 'hello_world' in result['content']
        assert 'regular content' in result['content']
    
    def test_edge_case_quotes_and_special_chars(self):
        """Test handling of quotes and special characters."""
        text = '''Article with "quotes" and 'apostrophes' and em—dashes and ellipses… and symbols like @#$%.'''
        
        result = self.normalizer.normalize_article(text)
        
        assert '"quotes"' in result['content']
        assert "'apostrophes'" in result['content']
        assert 'em—dashes' in result['content']
        assert 'ellipses…' in result['content']
        # Special characters like @#$% should be preserved


class TestNormalizationConvenienceFunction:
    """Test the convenience function."""
    
    def test_normalize_article_function(self):
        """Test the standalone normalize_article function."""
        text = "Test article content."
        result = normalize_article(text)
        
        assert result['content'] == 'Test article content.'
        assert result['word_count'] == 3
        assert result['char_count'] == len('Test article content.')
    
    def test_normalize_with_kwargs(self):
        """Test normalize_article with additional kwargs."""
        text = "Test content."
        result = normalize_article(
            text,
            preserve_paragraphs=False,
            detect_language=False
        )
        
        assert result['content'] == 'Test content.'
        assert result['language'] == 'unknown'  # Language detection disabled
