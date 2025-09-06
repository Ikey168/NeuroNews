#!/usr/bin/env python3
"""
Comprehensive ML Testing for Fake News Detection Classes (Issue #483)
Tests for machine learning model classes to ensure accurate predictions and robust ML infrastructure.
"""

import pytest
import os
import sys
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

@pytest.mark.unit
class TestFakeNewsDetectorML:
    """Test the FakeNewsDetector class from src/ml/fake_news_detection.py"""
    
    @pytest.fixture
    def mock_torch(self):
        """Mock PyTorch dependencies"""
        with patch('src.ml.fake_news_detection.torch') as mock_torch:
            mock_torch.device.return_value = "cpu"
            mock_torch.cuda.is_available.return_value = False
            yield mock_torch
    
    @pytest.fixture
    def mock_pipeline(self):
        """Mock transformers pipeline"""
        with patch('src.ml.fake_news_detection.pipeline') as mock_pipeline:
            mock_classifier = Mock()
            mock_classifier.return_value = [[
                {"label": "REAL", "score": 0.8},
                {"label": "FAKE", "score": 0.2}
            ]]
            mock_pipeline.return_value = mock_classifier
            yield mock_pipeline
    
    def test_fake_news_detector_initialization(self, mock_torch, mock_pipeline):
        """Test FakeNewsDetector initialization"""
        from src.ml.fake_news_detection import FakeNewsDetector
        
        detector = FakeNewsDetector()
        
        assert detector.model_name == "hamzelou/fake-news-bert"
        assert detector.model_version == "roberta-fake-news-v1.0"
        assert detector.confidence_threshold == 0.7
        assert detector.max_length == 512
        assert detector.device == "cpu"
    
    def test_config_loading_with_file(self, mock_torch, mock_pipeline):
        """Test configuration loading from file"""
        from src.ml.fake_news_detection import FakeNewsDetector
        
        # Create temporary config file
        config_data = {
            "fake_news_detection": {
                "confidence_threshold": 0.9,
                "max_length": 256,
                "batch_size": 8
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            import json
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            detector = FakeNewsDetector(config_path=config_path)
            assert detector.confidence_threshold == 0.9
            assert detector.max_length == 256
        finally:
            os.unlink(config_path)
    
    def test_predict_veracity_with_transformer(self, mock_torch, mock_pipeline):
        """Test prediction with transformer model"""
        from src.ml.fake_news_detection import FakeNewsDetector
        
        detector = FakeNewsDetector()
        
        result = detector.predict_veracity(
            "Breaking News", 
            "Scientists discover new treatment for cancer"
        )
        
        assert isinstance(result, dict)
        assert "is_real" in result
        assert "confidence" in result
        assert "model_version" in result
        assert "timestamp" in result
        assert result["is_real"] == True  # REAL has higher score
        assert isinstance(result["confidence"], float)
    
    def test_predict_veracity_rule_based_fallback(self, mock_torch):
        """Test rule-based prediction fallback"""
        from src.ml.fake_news_detection import FakeNewsDetector
        
        with patch('src.ml.fake_news_detection.pipeline', side_effect=Exception("Model failed")):
            detector = FakeNewsDetector()
            
            # Test fake news indicators
            result = detector.predict_veracity(
                "SHOCKING SECRET", 
                "Doctors hate this one weird trick for miracle cure"
            )
            
            assert result["is_real"] == False
            assert result["method"] == "rule_based"
            
            # Test real news indicators
            result = detector.predict_veracity(
                "Research Study", 
                "University researchers published peer-reviewed findings in journal"
            )
            
            assert result["is_real"] == True
            assert result["method"] == "rule_based"
    
    def test_batch_predict(self, mock_torch, mock_pipeline):
        """Test batch prediction functionality"""
        from src.ml.fake_news_detection import FakeNewsDetector
        
        detector = FakeNewsDetector()
        
        articles = [
            {"id": 1, "title": "News 1", "content": "Content 1"},
            {"id": 2, "title": "News 2", "content": "Content 2"}
        ]
        
        results = detector.batch_predict(articles)
        
        assert len(results) == 2
        assert all("is_real" in result for result in results)
        assert all("confidence" in result for result in results)
        assert results[0]["article_id"] == 1
        assert results[1]["article_id"] == 2
    
    def test_get_model_info(self, mock_torch, mock_pipeline):
        """Test model information retrieval"""
        from src.ml.fake_news_detection import FakeNewsDetector
        
        detector = FakeNewsDetector()
        info = detector.get_model_info()
        
        assert "model_name" in info
        assert "model_version" in info
        assert "device" in info
        assert "confidence_threshold" in info
        assert "max_length" in info
        assert "available" in info
        assert info["available"] == True

@pytest.mark.unit
class TestFakeNewsDetectorNLP:
    """Test the FakeNewsDetector class from src/nlp/fake_news_detector.py"""
    
    @pytest.fixture
    def mock_transformers(self):
        """Mock transformers dependencies"""
        with patch.multiple(
            'src.nlp.fake_news_detector',
            AutoTokenizer=Mock(),
            AutoModelForSequenceClassification=Mock(),
            RobertaTokenizer=Mock(),
            RobertaForSequenceClassification=Mock(),
            torch=Mock()
        ):
            yield
    
    @pytest.fixture
    def mock_dataset(self):
        """Mock training dataset"""
        texts = ["This is real news", "This is fake news"]
        labels = [1, 0]
        return texts, labels
    
    def test_fake_news_detector_nlp_initialization(self, mock_transformers):
        """Test FakeNewsDetector NLP initialization"""
        from src.nlp.fake_news_detector import FakeNewsDetector
        
        detector = FakeNewsDetector(model_name="roberta-base", use_pretrained=False)
        
        assert detector.model_name == "roberta-base"
        assert hasattr(detector, 'config')
        assert hasattr(detector, 'device')
    
    def test_prepare_liar_dataset(self, mock_transformers):
        """Test LIAR dataset preparation"""
        from src.nlp.fake_news_detector import FakeNewsDetector
        
        detector = FakeNewsDetector(use_pretrained=False)
        texts, labels = detector.prepare_liar_dataset()
        
        assert len(texts) == len(labels)
        assert len(texts) > 0
        assert all(isinstance(text, str) for text in texts)
        assert all(isinstance(label, int) for label in labels)
        assert all(label in [0, 1] for label in labels)
    
    def test_text_preprocessing(self, mock_transformers):
        """Test text preprocessing functionality"""
        from src.nlp.fake_news_detector import FakeNewsDetector
        
        detector = FakeNewsDetector(use_pretrained=False)
        
        # Test normal text
        processed = detector._preprocess_text("This is normal text.")
        assert processed == "This is normal text."
        
        # Test text with extra whitespace
        processed = detector._preprocess_text("Text   with   spaces\n\n")
        assert processed == "Text with spaces"
        
        # Test ALL CAPS text
        processed = detector._preprocess_text("THIS IS ALL CAPS")
        assert processed == "this is all caps"
        
        # Test empty/None text
        assert detector._preprocess_text("") == ""
        assert detector._preprocess_text(None) == ""
    
    def test_trust_level_classification(self, mock_transformers):
        """Test trust level classification"""
        from src.nlp.fake_news_detector import FakeNewsDetector
        
        detector = FakeNewsDetector(use_pretrained=False)
        
        assert detector._classify_trust_level(85.0) == "high"
        assert detector._classify_trust_level(65.0) == "medium"
        assert detector._classify_trust_level(45.0) == "low"
    
    def test_training_with_minimal_data(self, mock_transformers, mock_dataset):
        """Test model training with minimal dataset"""
        from src.nlp.fake_news_detector import FakeNewsDetector
        
        detector = FakeNewsDetector(use_pretrained=False)
        
        # Mock the training components
        with patch('src.nlp.fake_news_detector.Trainer') as mock_trainer_class:
            mock_trainer = Mock()
            mock_trainer.train.return_value = None
            mock_trainer.evaluate.return_value = {
                "eval_accuracy": 0.8,
                "eval_f1": 0.75,
                "eval_precision": 0.85,
                "eval_recall": 0.70
            }
            mock_trainer.save_model.return_value = None
            mock_trainer_class.return_value = mock_trainer
            
            with patch('src.nlp.fake_news_detector.FakeNewsDataset'):
                texts, labels = mock_dataset
                
                results = detector.train(texts, labels, num_epochs=1, batch_size=2)
                
                assert "accuracy" in results
                assert "f1" in results
                assert "precision" in results
                assert "recall" in results
                assert isinstance(results["accuracy"], float)
    
    def test_batch_prediction(self, mock_transformers):
        """Test batch prediction functionality"""
        from src.nlp.fake_news_detector import FakeNewsDetector
        
        detector = FakeNewsDetector(use_pretrained=False)
        
        # Mock predict_trustworthiness
        with patch.object(detector, 'predict_trustworthiness') as mock_predict:
            mock_predict.return_value = {
                "trustworthiness_score": 75.0,
                "classification": "real",
                "confidence": 80.0
            }
            
            texts = ["News 1", "News 2", "News 3"]
            results = detector.batch_predict(texts)
            
            assert len(results) == 3
            assert all("trustworthiness_score" in result for result in results)
            assert mock_predict.call_count == 3

@pytest.mark.unit
class TestFakeNewsConfig:
    """Test FakeNewsConfig class"""
    
    def test_config_initialization_defaults(self):
        """Test config initialization with defaults"""
        from src.nlp.fake_news_detector import FakeNewsConfig
        
        config = FakeNewsConfig()
        
        assert config.model_name == "roberta-base"
        assert config.max_length == 512
        assert config.confidence_threshold == 0.6
        assert config.batch_size == 16
        assert config.num_epochs == 3
        assert config.learning_rate == 2e-5
    
    def test_config_initialization_custom(self):
        """Test config initialization with custom values"""
        from src.nlp.fake_news_detector import FakeNewsConfig
        
        config = FakeNewsConfig(
            model_name="deberta-v3-base",
            max_length=256,
            confidence_threshold=0.8,
            batch_size=32
        )
        
        assert config.model_name == "deberta-v3-base"
        assert config.max_length == 256
        assert config.confidence_threshold == 0.8
        assert config.batch_size == 32
    
    def test_config_constants(self):
        """Test configuration constants"""
        from src.nlp.fake_news_detector import FakeNewsConfig
        
        config = FakeNewsConfig()
        
        assert hasattr(config, 'MODELS')
        assert hasattr(config, 'HIGH_CONFIDENCE_THRESHOLD')
        assert hasattr(config, 'MEDIUM_CONFIDENCE_THRESHOLD')
        assert hasattr(config, 'TRUSTWORTHINESS_THRESHOLD')
        assert config.HIGH_CONFIDENCE_THRESHOLD == 80.0
        assert config.MEDIUM_CONFIDENCE_THRESHOLD == 60.0

@pytest.mark.unit
class TestFakeNewsDataset:
    """Test FakeNewsDataset class"""
    
    def test_dataset_initialization(self):
        """Test dataset initialization"""
        from src.nlp.fake_news_detector import FakeNewsDataset
        
        texts = ["Text 1", "Text 2"]
        labels = [1, 0]
        mock_tokenizer = Mock()
        
        dataset = FakeNewsDataset(texts, labels, mock_tokenizer, max_length=128)
        
        assert len(dataset) == 2
        assert dataset.texts == texts
        assert dataset.labels == labels
        assert dataset.max_length == 128
    
    def test_dataset_getitem(self):
        """Test dataset item retrieval"""
        from src.nlp.fake_news_detector import FakeNewsDataset
        import torch
        
        texts = ["Sample text"]
        labels = [1]
        
        mock_tokenizer = Mock()
        mock_tokenizer.return_value = {
            "input_ids": torch.tensor([[1, 2, 3]]),
            "attention_mask": torch.tensor([[1, 1, 1]])
        }
        
        dataset = FakeNewsDataset(texts, labels, mock_tokenizer)
        item = dataset[0]
        
        assert "input_ids" in item
        assert "attention_mask" in item
        assert "labels" in item
        
        mock_tokenizer.assert_called_once()

@pytest.mark.integration 
class TestFakeNewsDetectionIntegration:
    """Integration tests for fake news detection pipeline"""
    
    def test_end_to_end_prediction_pipeline(self):
        """Test complete prediction pipeline"""
        # This would test the full pipeline from text input to prediction output
        # For now, we'll mock the complex dependencies
        
        with patch('src.ml.fake_news_detection.torch'), \
             patch('src.ml.fake_news_detection.pipeline') as mock_pipeline:
            
            mock_classifier = Mock()
            mock_classifier.return_value = [[
                {"label": "REAL", "score": 0.9},
                {"label": "FAKE", "score": 0.1}
            ]]
            mock_pipeline.return_value = mock_classifier
            
            from src.ml.fake_news_detection import FakeNewsDetector
            
            detector = FakeNewsDetector()
            result = detector.predict_veracity(
                "Economic Report",
                "The quarterly GDP growth exceeded expectations according to government statistics."
            )
            
            assert result["is_real"] == True
            assert result["confidence"] > 0.8
            assert "explanation" in result
            assert "timestamp" in result

@pytest.mark.performance
class TestFakeNewsDetectionPerformance:
    """Performance tests for fake news detection"""
    
    def test_prediction_performance(self):
        """Test prediction performance and latency"""
        with patch('src.ml.fake_news_detection.torch'), \
             patch('src.ml.fake_news_detection.pipeline'):
            
            from src.ml.fake_news_detection import FakeNewsDetector
            import time
            
            detector = FakeNewsDetector()
            
            # Test single prediction performance
            start_time = time.time()
            result = detector.predict_veracity("Title", "Content")
            end_time = time.time()
            
            prediction_time = end_time - start_time
            
            # Should complete within reasonable time (mocked, so should be very fast)
            assert prediction_time < 1.0
            assert result is not None
    
    def test_batch_processing_performance(self):
        """Test batch processing performance"""
        with patch('src.ml.fake_news_detection.torch'), \
             patch('src.ml.fake_news_detection.pipeline'):
            
            from src.ml.fake_news_detection import FakeNewsDetector
            
            detector = FakeNewsDetector()
            
            # Create batch of articles
            articles = [
                {"id": i, "title": f"Title {i}", "content": f"Content {i}"}
                for i in range(10)
            ]
            
            results = detector.batch_predict(articles)
            
            assert len(results) == 10
            assert all("is_real" in result for result in results)
            assert all("confidence" in result for result in results)

if __name__ == "__main__":
    pytest.main([__file__])