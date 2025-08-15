#!/usr/bin/env python3
"""
Debug script to understand the exact test failure.
"""

import sys
import os
sys.path.append('/workspaces/NeuroNews')

from src.nlp.keyword_topic_extractor import TFIDFKeywordExtractor, LDATopicModeler, KeywordResult

def test_tfidf_single_text():
    """Reproduce the exact failing test."""
    print("=== Testing TFIDFKeywordExtractor single text ===")
    
    # Exact same setup as test
    extractor = TFIDFKeywordExtractor(max_features=100)
    texts = ["Machine learning and artificial intelligence are transforming technology"]
    results = extractor.extract_keywords(texts, top_k=5)
    
    print(f"Results length: {len(results)}")
    print(f"First result length: {len(results[0]) if results else 0}")
    
    if results and results[0]:
        for i, keyword in enumerate(results[0]):
            print(f"Keyword {i}: {keyword.keyword}, method: {keyword.method}, score: {keyword.score}")
            print(f"Is KeywordResult: {isinstance(keyword, KeywordResult)}")
            
        first_method = results[0][0].method
        print(f"\nFirst keyword method: '{first_method}'")
        print(f"Expected: 'frequency'")
        print(f"Assertion 'frequency' == method: {'frequency' == first_method}")
        print(f"Assertion method == 'tfidf': {first_method == 'tfidf'}")

def test_lda_topics():
    """Reproduce the exact failing LDA test."""
    print("\n=== Testing LDATopicModeler ===")
    
    modeler = LDATopicModeler(n_topics=3, max_features=100)
    texts = [
        "Machine learning and artificial intelligence research advances in neural networks and deep learning algorithms for computer vision and natural language processing applications",
        "Climate change and environmental sustainability issues require global cooperation and green technology solutions including renewable energy sources and carbon reduction strategies", 
        "Healthcare technology and medical innovation progress through genomic sequencing personalized medicine treatments and telemedicine platform development for patient care",
        "Artificial intelligence transforms healthcare diagnostics with automated medical imaging analysis and predictive analytics for disease prevention and early detection systems",
        "Environmental protection and climate action policies focus on sustainable development goals including biodiversity conservation and ecosystem restoration initiatives worldwide",
        "Financial technology fintech innovations include blockchain cryptocurrency digital payments mobile banking and algorithmic trading systems for modern finance",
        "Space exploration missions investigate mars colonization satellite technology rocket propulsion systems and astronomical research for understanding the universe and planetary science"
    ]
    
    topic_info = modeler.fit_topics(texts)
    
    print(f"Model fitted: {topic_info['model_fitted']}")
    print(f"Number of topics: {len(topic_info['topics'])}")
    print(f"Has perplexity: {'perplexity' in topic_info}")
    print(f"Assertion model_fitted is True: {topic_info['model_fitted'] is True}")
    
    if not topic_info["model_fitted"]:
        print("ERROR: Model not fitted!")
        print(f"Topic info keys: {list(topic_info.keys())}")

if __name__ == "__main__":
    test_tfidf_single_text()
    test_lda_topics()
