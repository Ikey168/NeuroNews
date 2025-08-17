#!/usr/bin/env python3
"""
Validation script for AI-based fake news detection implementation.
Tests the core functionality and model performance.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ml.fake_news_detection import FakeNewsDetector
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_fake_news_detection():
    """Test the fake news detection functionality."""
    
    print("🔍 Testing AI-based Fake News Detection")
    print("=" * 50)
    
    try:
        # Initialize detector
        print("📊 Initializing FakeNewsDetector...")
        detector = FakeNewsDetector()
        
        # Test cases - mix of real and fake news examples
        test_articles = [
            {
                "title": "Scientists Discover New Species of Deep-Sea Fish",
                "content": "Researchers from the Marine Biology Institute have identified a previously unknown species of deep-sea fish during a recent expedition to the Mariana Trench. The discovery adds to our understanding of deep-ocean biodiversity.",
                "expected": "REAL"
            },
            {
                "title": "Aliens Land in Times Square, Demand Pizza",
                "content": "Extraterrestrial beings reportedly landed their spacecraft in the heart of New York City yesterday, immediately requesting the city's famous pizza. NASA has yet to comment on this groundbreaking first contact.",
                "expected": "FAKE"
            },
            {
                "title": "Local Hospital Implements New Safety Protocols",
                "content": "City General Hospital announced the implementation of enhanced safety protocols following recent health guidelines. The new measures include updated sanitation procedures and improved patient monitoring systems.",
                "expected": "REAL"
            },
            {
                "title": "Study Shows Chocolate Cures All Diseases Instantly",
                "content": "A revolutionary study published nowhere credible claims that eating chocolate can instantly cure any disease known to humanity. The research was conducted by the International Chocolate Appreciation Society.",
                "expected": "FAKE"
            }
        ]
        
        print(f"🧪 Testing {len(test_articles)} sample articles...")
        print()
        
        correct_predictions = 0
        
        for i, article in enumerate(test_articles, 1):
            print(f"Test {i}: {article['title'][:50]}...")
            
            try:
                # Predict veracity
                result = detector.predict_veracity(
                    title=article['title'],
                    content=article['content']
                )
                
                # Extract prediction
                prediction = "REAL" if result['is_real'] else "FAKE"
                confidence = result['confidence']
                
                # Check if prediction matches expected
                is_correct = prediction == article['expected']
                if is_correct:
                    correct_predictions += 1
                
                status = "✅ CORRECT" if is_correct else "❌ WRONG"
                print(f"   Predicted: {prediction} (confidence: {confidence:.3f}) - {status}")
                print(f"   Expected: {article['expected']}")
                
            except Exception as e:
                print(f"   ❌ ERROR: {str(e)}")
            
            print()
        
        # Calculate accuracy
        accuracy = correct_predictions / len(test_articles)
        print(f"📈 Overall Accuracy: {accuracy:.2%} ({correct_predictions}/{len(test_articles)})")
        
        if accuracy >= 0.75:
            print("🎉 Fake news detection is working well!")
            return True
        else:
            print("⚠️ Accuracy is below 75%. Model may need improvement.")
            return False
            
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")
        return False

def test_api_integration():
    """Test the API integration functionality."""
    
    print("\n🔌 Testing API Integration")
    print("=" * 30)
    
    try:
        from src.api.routes.veracity_routes import get_article_veracity
        print("✅ Veracity routes imported successfully")
        
        # Test the route function exists
        if callable(get_article_veracity):
            print("✅ get_article_veracity function is callable")
        else:
            print("❌ get_article_veracity is not callable")
            return False
            
        return True
        
    except ImportError as e:
        print(f"❌ Could not import veracity routes: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Error testing API integration: {str(e)}")
        return False

def main():
    """Run all validation tests."""
    
    print("🚀 NeuroNews Fake News Detection Validation")
    print("=" * 60)
    print()
    
    # Run tests
    detection_test = test_fake_news_detection()
    api_test = test_api_integration()
    
    print("\n📋 Validation Summary")
    print("=" * 25)
    print(f"Fake News Detection: {'✅ PASS' if detection_test else '❌ FAIL'}")
    print(f"API Integration: {'✅ PASS' if api_test else '❌ FAIL'}")
    
    # Overall result
    all_passed = detection_test and api_test
    
    if all_passed:
        print("\n🎉 All tests passed! Fake news detection is ready for deployment.")
        sys.exit(0)
    else:
        print("\n⚠️ Some tests failed. Please review the implementation.")
        sys.exit(1)

if __name__ == "__main__":
    main()
