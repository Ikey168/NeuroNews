import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call 
import json # For loading LABELED_TEXTS
import os # For path joining

from src.nlp import SentimentAnalyzer, create_analyzer 

# Load LABELED_TEXTS from the JSON fixture file
def load_labeled_texts():
    fixture_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'labeled_data.json')
    with open(fixture_path, 'r') as f:
        data = json.load(f)
    labeled_texts = []
    for case in data.get("test_cases", []):
        labeled_texts.append({
            "text": case.get("text"),
            "expected_label": case.get("expected_sentiment", "NEUTRAL").upper() 
        })
    labeled_texts.append({"text": "", "expected_label": "ERROR"})
    labeled_texts.append({"text": "   ", "expected_label": "ERROR"})
    return labeled_texts

LABELED_TEXTS = load_labeled_texts()

EDGE_CASE_TEXTS_FOR_DEFAULT_ANALYZER = [
    ("", "ERROR", 0.0),
    ("   ", "ERROR", 0.0),
    ("!@#$%^", "NEUTRAL", 0.0), 
    ("This is a test.", "NEUTRAL", 0.0), 
    ("I love this product, it's amazing!", "POSITIVE", 0.0) 
]

@pytest.fixture
def mock_hf_analyzer(mocker):
    mock_pipeline_func = mocker.patch("src.nlp.sentiment_analysis.pipeline", autospec=True)
    mock_pipeline_instance = mocker.MagicMock() 
    mock_pipeline_func.return_value = mock_pipeline_instance
    # SentimentAnalyzer() will use its default model name, but pipeline is mocked.
    analyzer = SentimentAnalyzer() 
    assert analyzer.pipeline is mock_pipeline_instance, "Patching 'src.nlp.sentiment_analysis.pipeline' did not result in the mock being used."
    return analyzer

def test_default_analyzer_accuracy():
    # create_analyzer() uses SentimentAnalyzer.DEFAULT_MODEL by default
    analyzer = create_analyzer() 
    positive_text = "This is a wonderful and amazing experience, I am very happy!"
    negative_text = "This is a terrible and dreadful situation, I am very sad."
    neutral_text = "The weather today is partly cloudy with a chance of rain."

    pos_result = analyzer.analyze(positive_text)
    neg_result = analyzer.analyze(negative_text)
    neu_result = analyzer.analyze(neutral_text)

    assert pos_result["label"] == "POSITIVE"
    assert neg_result["label"] == "NEGATIVE"
    assert neu_result["label"] in ["NEUTRAL", "POSITIVE", "NEGATIVE"]

def test_batch_processing_default_analyzer():
    analyzer = create_analyzer()
    texts_for_live_test = [item["text"] for item in LABELED_TEXTS if item["expected_label"] != "ERROR" and item["text"] and item["text"].strip()]
    
    if not texts_for_live_test: 
        pytest.skip("No valid non-error texts from LABELED_TEXTS for batch processing.")

    results = analyzer.analyze_batch(texts_for_live_test)
    assert len(results) == len(texts_for_live_test)
    for result in results:
        assert result["label"] in ["POSITIVE", "NEGATIVE", "NEUTRAL"]

@pytest.mark.parametrize("text, expected_label, _score_not_used", EDGE_CASE_TEXTS_FOR_DEFAULT_ANALYZER)
def test_edge_cases_default_analyzer(text, expected_label, _score_not_used):
    analyzer = create_analyzer() # Uses default model
    result = analyzer.analyze(text)
    assert result["label"] == expected_label
    if expected_label == "ERROR":
        assert result["score"] == 0.0 
    else:
        assert isinstance(result["score"], float)

def test_hf_analyzer_mocked_call(mock_hf_analyzer: SentimentAnalyzer):
    test_text = "This is a great day!"
    mock_hf_analyzer.pipeline.return_value = [{"label": "POSITIVE", "score": 0.987}]
    result = mock_hf_analyzer.analyze(test_text)
    mock_hf_analyzer.pipeline.assert_called_once_with(test_text)
    assert result["label"] == "POSITIVE"
    assert result["score"] == 0.987

@pytest.mark.parametrize("test_case", LABELED_TEXTS)
def test_hf_analyzer_label_mapping(mock_hf_analyzer: SentimentAnalyzer, test_case):
    text_to_analyze = test_case["text"]
    expected_label_from_fixture = test_case["expected_label"].upper()

    if not text_to_analyze or not text_to_analyze.strip(): 
        result = mock_hf_analyzer.analyze(text_to_analyze)
        assert result["label"] == "ERROR"
        mock_hf_analyzer.pipeline.assert_not_called() 
    else:
        mock_hf_analyzer.pipeline.return_value = [{"label": expected_label_from_fixture, "score": 0.99}]
        result = mock_hf_analyzer.analyze(text_to_analyze)
        assert result["label"].upper() == expected_label_from_fixture
        mock_hf_analyzer.pipeline.assert_called_with(text_to_analyze)

def test_batch_processing_hf_analyzer(mock_hf_analyzer: SentimentAnalyzer):
    texts = [item["text"] for item in LABELED_TEXTS]
    valid_texts_for_pipeline = [t for t in texts if t and t.strip()]

    mock_pipeline_output = []
    for valid_text in valid_texts_for_pipeline:
        original_case = next(item for item in LABELED_TEXTS if item["text"] == valid_text)
        mock_pipeline_output.append({"label": original_case["expected_label"].upper(), "score": 0.95})
    
    mock_hf_analyzer.pipeline.return_value = mock_pipeline_output

    results = mock_hf_analyzer.analyze_batch(texts) 

    if not valid_texts_for_pipeline:
         mock_hf_analyzer.pipeline.assert_not_called()
    else:
        mock_hf_analyzer.pipeline.assert_called_once_with(valid_texts_for_pipeline)

    assert len(results) == len(texts)
    
    result_idx_for_mock_output = 0
    for i, original_text in enumerate(texts):
        if original_text and original_text.strip():
            expected_mock_item = mock_pipeline_output[result_idx_for_mock_output]
            assert results[i]["label"] == expected_mock_item["label"]
            assert results[i]["score"] == expected_mock_item["score"]
            result_idx_for_mock_output += 1
        else:
            assert results[i]["label"] == "ERROR"

def test_live_transformers_integration():
    # SentimentAnalyzer() will use its DEFAULT_MODEL
    analyzer = SentimentAnalyzer() 
    text = "Hugging Face models are quite useful for NLP tasks."
    result = analyzer.analyze(text)
    assert result["label"] in ["POSITIVE", "NEUTRAL", "NEGATIVE"]
    assert isinstance(result["score"], float)
    assert 0 <= result["score"] <= 1