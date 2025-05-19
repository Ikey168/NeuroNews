"""
Tests for scraper timing measurements.
"""

import pytest
import asyncio
import pandas as pd
from pathlib import Path
import json
import tempfile
from aioresponses import aioresponses
import matplotlib.pyplot as plt

from scripts.measure_scraper_times import ScraperTimer, NEWS_SOURCES

# Test data
TEST_HTML = """
<html>
    <head><title>Test Article</title></head>
    <body>
        <h1>Article Title</h1>
        <article>Article content for {source}</article>
    </body>
</html>
"""

@pytest.fixture
def timer():
    """Create test timer instance."""
    return ScraperTimer(concurrency=5)

@pytest.fixture
def mock_responses():
    """Mock URL responses with different latencies."""
    with aioresponses() as m:
        # Setup responses for each source with different latencies
        for source, urls in NEWS_SOURCES.items():
            for url in urls:
                # Simulate different response times for different sources
                delay = {
                    'reuters': 0.1,
                    'bloomberg': 0.2,
                    'wsj': 0.3
                }.get(source, 0.1)
                
                m.get(
                    url,
                    status=200,
                    body=TEST_HTML.format(source=source),
                    delay=delay
                )
        yield m

@pytest.fixture
def temp_output_dir():
    """Create temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.mark.asyncio
async def test_measure_single_source(timer, mock_responses):
    """Test measuring a single news source."""
    source = 'reuters'
    urls = NEWS_SOURCES[source]
    
    await timer.measure_source(source, urls, iterations=2)
    
    assert source in timer.results
    assert len(timer.results[source]) == 2
    
    for result in timer.results[source]:
        assert 'duration' in result
        assert 'articles' in result
        assert 'avg_time_per_article' in result
        assert 'success_rate' in result
        assert result['articles'] == len(urls)
        assert result['success_rate'] == 1.0

@pytest.mark.asyncio
async def test_measure_all_sources(timer, mock_responses):
    """Test measuring all news sources."""
    for source, urls in NEWS_SOURCES.items():
        await timer.measure_source(source, urls, iterations=1)
    
    assert len(timer.results) == len(NEWS_SOURCES)
    
    df = timer.analyze_results()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == len(NEWS_SOURCES)  # One row per source with 1 iteration
    assert set(df['source'].unique()) == set(NEWS_SOURCES.keys())

def test_analyze_results(timer):
    """Test results analysis."""
    # Add test data
    timer.results = {
        'test_source': [
            {
                'duration': 1.0,
                'articles': 5,
                'avg_time_per_article': 0.2,
                'success_rate': 1.0
            },
            {
                'duration': 1.5,
                'articles': 4,
                'avg_time_per_article': 0.375,
                'success_rate': 0.8
            }
        ]
    }
    
    df = timer.analyze_results()
    
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2  # Two measurements
    assert list(df.columns) == ['source', 'duration', 'articles', 
                               'avg_time_per_article', 'success_rate']
    assert df['source'].iloc[0] == 'test_source'

def test_plot_results(timer, temp_output_dir):
    """Test results visualization."""
    # Add test data for multiple sources
    timer.results = {
        'source1': [
            {
                'duration': 1.0,
                'articles': 5,
                'avg_time_per_article': 0.2,
                'success_rate': 1.0
            }
        ],
        'source2': [
            {
                'duration': 2.0,
                'articles': 3,
                'avg_time_per_article': 0.67,
                'success_rate': 0.6
            }
        ]
    }
    
    # Generate plots
    timer.plot_results(temp_output_dir)
    
    # Check if plot file was created
    plot_files = list(temp_output_dir.glob('scraper_timing_*.png'))
    assert len(plot_files) == 1
    
    # Verify plot contents
    plot = plt.imread(plot_files[0])
    assert plot.shape[2] == 4  # RGBA image
    assert plot.shape[0] > 0 and plot.shape[1] > 0

@pytest.mark.asyncio
async def test_error_handling(timer):
    """Test handling of failed requests."""
    with aioresponses() as m:
        # Setup mix of successful and failed responses
        urls = NEWS_SOURCES['reuters']
        
        # One success, one error, one timeout
        m.get(urls[0], status=200, body=TEST_HTML.format(source='reuters'))
        m.get(urls[1], status=500)
        m.get(urls[2], exception=asyncio.TimeoutError)
        
        await timer.measure_source('reuters', urls, iterations=1)
        
        result = timer.results['reuters'][0]
        assert result['success_rate'] < 1.0
        assert result['articles'] == 1

@pytest.mark.asyncio
async def test_concurrent_execution(timer, mock_responses):
    """Test concurrent request handling."""
    source = 'reuters'
    urls = NEWS_SOURCES[source]
    
    start_time = asyncio.get_event_loop().time()
    await timer.measure_source(source, urls, iterations=1)
    duration = asyncio.get_event_loop().time() - start_time
    
    # Should be faster than sequential execution
    # (sum of individual delays would be 0.3 seconds)
    assert duration < 0.3

def test_output_files(timer, temp_output_dir):
    """Test output file generation."""
    # Add test results
    timer.results = {
        'source1': [
            {
                'duration': 1.0,
                'articles': 5,
                'avg_time_per_article': 0.2,
                'success_rate': 1.0
            }
        ]
    }
    
    # Generate outputs
    df = timer.analyze_results()
    df.to_csv(temp_output_dir / 'timing_results.csv')
    
    timer.plot_results(temp_output_dir)
    
    # Verify files
    assert (temp_output_dir / 'timing_results.csv').exists()
    assert len(list(temp_output_dir.glob('scraper_timing_*.png'))) == 1