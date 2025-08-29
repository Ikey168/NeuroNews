import json
import tempfile
from pathlib import Path
import pytest
from unittest.mock import Mock, patch
from unittest.mock import Mock, patch

from neuronews.ml.models.fake_news_detection import FakeNewsDetector


class DummyClassifierList:
    def __call__(self, text):  # noqa: D401
        return [[{"label": "REAL", "score": 0.8}, {"label": "FAKE", "score": 0.2}]]


class DummyClassifierSingle:
    def __call__(self, text):  # noqa: D401
        return [{"label": "FAKE", "score": 0.9}]


def test_load_config_from_file(tmp_path):
    cfg = {"fake_news_detection": {"confidence_threshold": 0.9, "max_length": 128}}
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(cfg))
    det = FakeNewsDetector(config_path=str(cfg_file))
    assert det.confidence_threshold == 0.9
    assert det.max_length == 128


def test_predict_with_transformer_list(monkeypatch):
    det = FakeNewsDetector()
    det.classifier = DummyClassifierList()
    out = det.predict_veracity("Title", "Some researched study shows data")
    assert out["is_real"] is True
    assert 0 < out["confidence"] <= 1
    assert "explanation" in out


def test_predict_with_transformer_single(monkeypatch):
    det = FakeNewsDetector()
    det.classifier = DummyClassifierSingle()
    out = det.predict_veracity("Title", "Content")
    assert out["is_real"] is False
    assert out["confidence"] == 0.9


def test_rule_based_path(monkeypatch):
    det = FakeNewsDetector()
    det.classifier = None  # force rule-based
    out = det.predict_veracity("Shocking secret", "miracle cure you won't believe")
    assert out["is_real"] in (True, False)
    assert 0 <= out["confidence"] <= 1


def test_explanation_branches():
    det = FakeNewsDetector()
    det.classifier = None
    # High confidence real
    res = {"is_real": True, "confidence": 0.85}
    exp = det._generate_explanation("Title", "research data study", res)
    assert "research" in exp.lower() or "study" in exp.lower()
    # Fake with sensational language
    res2 = {"is_real": False, "confidence": 0.7}
    exp2 = det._generate_explanation("Shocking secret", "miracle claim", res2)
    assert "sensational" in exp2.lower() or "unrealistic" in exp2.lower() or "questionable" in exp2.lower()


def test_fallback_on_exception(monkeypatch):
    det = FakeNewsDetector()
    def boom(*args, **kwargs):
        raise RuntimeError("fail")
    det._predict_with_transformer = boom  # type: ignore
    out = det.predict_veracity("Title", "Content")
    # Should return something with model_version even if failed
    assert "model_version" in out
    assert 0 <= out["confidence"] <= 1


def test_batch_predict_and_truncation():
    det = FakeNewsDetector()
    det.classifier = None
    det.max_length = 4  # force truncation threshold extremely low
    long_content = "x" * 10000
    batch = [{"id": 1, "title": "Title", "content": long_content}]
    out_list = det.batch_predict(batch)
    assert len(out_list) == 1
    assert out_list[0]["article_id"] == 1


def test_get_model_info():
    """Test model info method."""
    detector = FakeNewsDetector()
    info = detector.get_model_info()
    
    assert "model_name" in info
    assert "device" in info
    assert "model_version" in info


def test_manual_model_loading_fallback():
    """Test manual model loading when pipeline fails."""
    with patch('neuronews.ml.models.fake_news_detection.pipeline') as mock_pipeline:
        # Make pipeline fail
        mock_pipeline.side_effect = Exception("Pipeline failed")
        
        with patch('neuronews.ml.models.fake_news_detection.AutoTokenizer') as mock_tokenizer:
            with patch('neuronews.ml.models.fake_news_detection.AutoModelForSequenceClassification') as mock_model:
                # Mock successful manual loading
                mock_tokenizer.from_pretrained.return_value = Mock()
                mock_model_instance = Mock()
                mock_model.from_pretrained.return_value = mock_model_instance
                
                detector = FakeNewsDetector()
                
                # Verify manual loading was attempted
                mock_tokenizer.from_pretrained.assert_called_once()
                mock_model.from_pretrained.assert_called_once()
                mock_model_instance.to.assert_called_once()
                mock_model_instance.eval.assert_called_once()


def test_complete_model_initialization_failure():
    """Test complete model initialization failure."""
    with patch('neuronews.ml.models.fake_news_detection.pipeline') as mock_pipeline:
        with patch('neuronews.ml.models.fake_news_detection.AutoTokenizer') as mock_tokenizer:
            # Make both pipeline and manual loading fail
            mock_pipeline.side_effect = Exception("Pipeline failed")
            mock_tokenizer.from_pretrained.side_effect = Exception("Manual loading failed")
            
            detector = FakeNewsDetector()
            
            # Should fall back to rule-based
            assert detector.classifier is None
            assert detector.model is None


def test_transformer_prediction_error():
    """Test transformer prediction error handling."""
    with patch('neuronews.ml.models.fake_news_detection.pipeline') as mock_pipeline:
        mock_classifier = Mock()
        mock_classifier.side_effect = Exception("Prediction failed")
        mock_pipeline.return_value = mock_classifier
        
        detector = FakeNewsDetector()
        result = detector._predict_with_transformer("test text")
        
        # Should return fallback result
        assert result["is_real"] is True
        assert result["confidence"] == 0.5
        assert "error" in result


def test_batch_predict_error_handling():
    """Test batch prediction with individual article errors."""
    detector = FakeNewsDetector()
    
    # Mock predict_veracity to fail for specific article
    with patch.object(detector, 'predict_veracity') as mock_predict:
        def side_effect(*args, **kwargs):
            article_title = kwargs.get('title', '')
            if article_title == "error":
                raise Exception("Individual prediction failed")
            return {"is_real": True, "confidence": 0.8}
        
        mock_predict.side_effect = side_effect
        
        articles = [
            {"id": "1", "title": "Good article", "content": "Good content"},
            {"id": "2", "title": "error", "content": "Error content"},
            {"id": "3", "title": "Another good", "content": "More content"}
        ]
        
        results = detector.batch_predict(articles)
        
        assert len(results) == 3
        # First and third should succeed
        assert results[0]["is_real"] is True
        assert results[2]["is_real"] is True
        # Second should be fallback result
        assert "error" in results[1]


def test_explanation_research_content():
    """Test explanation generation for research content."""
    detector = FakeNewsDetector()
    
    result = {"is_real": True, "confidence": 0.8}
    explanation = detector._generate_explanation(
        "Scientific Study", 
        "This study shows that research findings are important", 
        result
    )
    
    assert "research or studies" in explanation


def test_explanation_expert_content():
    """Test explanation generation for expert content."""
    detector = FakeNewsDetector()
    
    result = {"is_real": True, "confidence": 0.8}
    explanation = detector._generate_explanation(
        "Expert Opinion", 
        "University experts recommend this approach", 
        result
    )
    
    assert "experts or academic sources" in explanation


def test_explanation_fake_sensational():
    """Test explanation generation for fake sensational content."""
    detector = FakeNewsDetector()
    
    result = {"is_real": False, "confidence": 0.8}
    explanation = detector._generate_explanation(
        "Shocking Miracle Secret", 
        "This shocking secret will change everything", 
        result
    )
    
    assert "sensational language" in explanation


def test_explanation_fake_instant_claims():
    """Test explanation generation for fake instant claims."""
    detector = FakeNewsDetector()
    
    result = {"is_real": False, "confidence": 0.8}
    explanation = detector._generate_explanation(
        "Instant Results", 
        "Get instant results with immediate effects", 
        result
    )
    
    assert "unrealistic claims" in explanation


def test_explanation_default_cases():
    """Test explanation generation default cases."""
    detector = FakeNewsDetector()
    
    # Real content without special keywords
    result_real = {"is_real": True, "confidence": 0.8}
    explanation_real = detector._generate_explanation(
        "Normal Title", 
        "Normal content without special keywords", 
        result_real
    )
    assert "factual and credible" in explanation_real
    
    # Fake content without special keywords
    result_fake = {"is_real": False, "confidence": 0.8}
    explanation_fake = detector._generate_explanation(
        "Normal Title", 
        "Normal content without special keywords", 
        result_fake
    )
    assert "questionable claims" in explanation_fake


def test_config_loading_exception():
    """Test config loading with file that causes exception."""
    # Create a file with invalid JSON to trigger exception
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write('{"invalid": json content}')  # Invalid JSON
        invalid_config_path = f.name
    
    try:
        detector = FakeNewsDetector()
        config = detector._load_config(invalid_config_path)
        # Should return default config when exception occurs
        assert "confidence_threshold" in config
        assert config["confidence_threshold"] == 0.7
    finally:
        # Clean up
        Path(invalid_config_path).unlink()


def test_predict_veracity_exception():
    """Test predict_veracity with exception during processing."""
    detector = FakeNewsDetector()
    
    # Mock a method to raise an exception during prediction
    with patch.object(detector, '_predict_with_rules') as mock_rules:
        mock_rules.side_effect = Exception("Processing failed")
        
        result = detector.predict_veracity("Test Title", "Test content")
        
        # Should return fallback result
        assert result["is_real"] is True
        assert result["confidence"] == 0.5
        assert "error" in result


def test_rule_based_neutral_case():
    """Test rule-based prediction with neutral scoring."""
    detector = FakeNewsDetector()
    
    # Text that doesn't trigger any fake or real indicators
    result = detector._predict_with_rules("Neutral Title", "Neutral content")
    
    # Should lean towards real with 0.5 confidence in neutral case
    assert result["is_real"] is True
    assert result["confidence"] == 0.5


def test_rule_based_high_real_score():
    """Test rule-based prediction with high real score."""
    detector = FakeNewsDetector()
    
    # Text with multiple real indicators
    result = detector._predict_with_rules(
        "Study Research Expert", 
        "This study from research shows data analysis evidence"
    )
    
    # Should be real with higher confidence
    assert result["is_real"] is True
    assert result["confidence"] > 0.6
