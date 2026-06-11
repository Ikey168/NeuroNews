"""
Test to verify line 430 (excessive_caps flag) is now reachable after the refactor.
"""
import pytest
from src.database.data_validation_pipeline import SourceReputationAnalyzer, SourceReputationConfig


def test_excessive_caps_flag_line_430():
    """Test that line 430 is now covered by checking excessive caps before lowercasing."""
    config = SourceReputationConfig(
        trusted_domains=['reuters.com'],
        questionable_domains=['test.com'],
        banned_domains=['fake.com'],
        reputation_thresholds={'trusted': 0.8, 'reliable': 0.6, 'questionable': 0.4}
    )
    
    analyzer = SourceReputationAnalyzer(config)
    
    # Article with title containing excessive caps (4+ consecutive uppercase letters)
    article = {
        'title': 'Breaking NEWS About Important Topic',  # NEWS = 4 consecutive caps
        'content': 'This is some content that is long enough to avoid thin_content flag. ' * 10,
        'url': 'https://test.com/article'
    }
    
    # This should trigger the excessive_caps flag
    result = analyzer.analyze_source(article)
    flags = result.get("flags", [])
    
    print(f"Title: {article['title']}")
    print(f"Flags: {flags}")
    
    assert "excessive_caps" in flags, f"Expected excessive_caps flag in {flags}"


def test_caps_flag_with_various_patterns():
    """Test different patterns of excessive caps."""
    config = SourceReputationConfig(
        trusted_domains=['reuters.com'],
        questionable_domains=['test.com'],
        banned_domains=['fake.com'],
        reputation_thresholds={'trusted': 0.8, 'reliable': 0.6, 'questionable': 0.4}
    )
    
    analyzer = SourceReputationAnalyzer(config)
    
    # Test cases with different cap patterns
    test_cases = [
        ('Breaking ABC News', True),   # ABC = 3 caps
        ('URGENT Update', True),       # URGENT = 6 caps  
        ('COVID Report', True),        # COVID = 5 caps
        ('News Today', False),         # No consecutive caps >= 3
        ('US Report', False),          # US = only 2 caps
    ]
    
    for title, should_have_flag in test_cases:
        article = {
            'title': title,
            'content': 'Long content here to avoid thin content flag. ' * 20,
            'url': 'https://test.com/article'
        }
        
        result = analyzer.analyze_source(article)
        flags = result.get("flags", [])
        
        if should_have_flag:
            assert "excessive_caps" in flags, f"Title '{title}' should trigger excessive_caps flag"
        else:
            assert "excessive_caps" not in flags, f"Title '{title}' should not trigger excessive_caps flag"
