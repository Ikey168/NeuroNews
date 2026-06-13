"""Re-export of the canonical fake-news detector.

The implementation lives in :mod:`src.ml.fake_news_detection`; this module
preserves the ``ml.models.fake_news_detection`` import path used by
``src.ml.inference.service`` and the model test suite.
"""

from src.ml.fake_news_detection import FakeNewsDetector  # noqa: F401

__all__ = ["FakeNewsDetector"]
