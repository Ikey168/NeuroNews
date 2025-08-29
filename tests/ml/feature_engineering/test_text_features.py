from neuronews.ml.feature_engineering.text_features import extract_basic_features


def test_extract_basic_features():
    feats = extract_basic_features("Short Title", "Some content body here")
    assert feats["title_len"] > 0
    assert feats["content_word_count"] >= 3
