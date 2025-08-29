"""
AWS Comprehend sentiment analysis implementation.
"""

import logging
from typing import Any, Dict, List

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class AWSComprehendSentimentAnalyzer:
    """AWS Comprehend-based sentiment analysis."""

    def __init__(self, region_name: str = "us-east-1", **kwargs):
        """
        Initialize AWS Comprehend sentiment analyzer.

        Args:
            region_name: AWS region for Comprehend service
            **kwargs: Additional boto3 client configuration
        """
        self.region_name = region_name
        try:
            self.client = boto3.client("comprehend", region_name=region_name, **kwargs)
            logger.info(
                "Initialized AWS Comprehend client in region {0}".format(region_name)
            )
        except Exception as e:
            logger.error(
                "Failed to initialize AWS Comprehend client: {0}".format(str(e))
            )
            raise

    def analyze(self, text: str, language_code: str = "en") -> Dict[str, Any]:
        """
        Analyze sentiment of a single text using AWS Comprehend.

        Args:
            text: Text to analyze (max 5000 UTF-8 bytes)
            language_code: Language code (en, es, fr, de, it, pt, ar, hi, ja, ko, zh, zh-TW)

        Returns:
            Dict with sentiment analysis results
        """
        if not text or not text.strip():
            return {
                "label": "ERROR",
                "score": 0.0,
                "text": text,
                "message": "Input text is empty or whitespace.",
                "provider": "aws_comprehend",
            }

        # Truncate text if too long for Comprehend
        text = text[:5000] if len(text.encode("utf-8")) > 5000 else text

        try:
            response = self.client.detect_sentiment(
                Text=text, LanguageCode=language_code
            )

            sentiment = response["Sentiment"]
            scores = response["SentimentScore"]

            # Get the confidence score for the detected sentiment
            confidence_map = {
                "POSITIVE": scores["Positive"],
                "NEGATIVE": scores["Negative"],
                "NEUTRAL": scores["Neutral"],
                "MIXED": scores["Mixed"],
            }

            return {
                "label": sentiment.upper(),
                "score": float(confidence_map[sentiment]),
                "text": text,
                "all_scores": {
                    "positive": float(scores["Positive"]),
                    "negative": float(scores["Negative"]),
                    "neutral": float(scores["Neutral"]),
                    "mixed": float(scores["Mixed"]),
                },
                "provider": "aws_comprehend",
                "language_code": language_code,
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"]["Message"]
            logger.error(
                "AWS Comprehend API error {0}: {1}".format(error_code, error_message)
            )

            return {
                "label": "ERROR",
                "score": 0.0,
                "text": text,
                "message": "AWS Comprehend error: {0}".format(error_message),
                "provider": "aws_comprehend",
            }

        except Exception as e:
            logger.error("Unexpected error in sentiment analysis: {0}".format(str(e)))
            return {
                "label": "ERROR",
                "score": 0.0,
                "text": text,
                "message": "Analysis failed: {0}".format(str(e)),
                "provider": "aws_comprehend",
            }

    def analyze_batch(
        self, texts: List[str], language_code: str = "en"
    ) -> List[Dict[str, Any]]:
        """
        Analyze sentiment for multiple texts using AWS Comprehend batch API.

        Args:
            texts: List of texts to analyze (max 25 items, 5000 UTF-8 bytes each)
            language_code: Language code for all texts

        Returns:
            List of sentiment analysis results
        """
        if not texts:
            return []

        # Filter out empty texts and prepare batch
        text_list = []
        index_map = {}  # Maps batch index to original index
        batch_index = 0

        for i, text in enumerate(texts):
            if text and text.strip():
                # Truncate if necessary
                clean_text = text[:5000] if len(text.encode("utf-8")) > 5000 else text
                text_list.append(clean_text)
                index_map[batch_index] = i
                batch_index += 1

        results = [None] * len(texts)  # Initialize results array

        if not text_list:
            # All texts were empty, return error results
            for i in range(len(texts)):
                results[i] = {
                    "label": "ERROR",
                    "score": 0.0,
                    "text": texts[i],
                    "message": "Input text is empty or whitespace.",
                    "provider": "aws_comprehend",
                }
            return results

        try:
            # AWS Comprehend batch API supports max 25 texts at a time
            batch_size = 25
            for batch_start in range(0, len(text_list), batch_size):
                batch_texts = text_list[batch_start : batch_start + batch_size]

                response = self.client.batch_detect_sentiment(
                    TextList=batch_texts, LanguageCode=language_code
                )

                # Process results
                for batch_idx, result in enumerate(response["ResultList"]):
                    original_idx = index_map[batch_start + batch_idx]
                    sentiment = result["Sentiment"]
                    scores = result["SentimentScore"]

                    confidence_map = {
                        "POSITIVE": scores["Positive"],
                        "NEGATIVE": scores["Negative"],
                        "NEUTRAL": scores["Neutral"],
                        "MIXED": scores["Mixed"],
                    }

                    results[original_idx] = {
                        "label": sentiment.upper(),
                        "score": float(confidence_map[sentiment]),
                        "text": texts[original_idx],
                        "all_scores": {
                            "positive": float(scores["Positive"]),
                            "negative": float(scores["Negative"]),
                            "neutral": float(scores["Neutral"]),
                            "mixed": float(scores["Mixed"]),
                        },
                        "provider": "aws_comprehend",
                        "language_code": language_code,
                    }

                # Process any errors
                for error in response.get("ErrorList", []):
                    error_idx = index_map[batch_start + error["Index"]]
                    results[error_idx] = {
                        "label": "ERROR",
                        "score": 0.0,
                        "text": texts[error_idx],
                        "message": f"AWS error {
                            error['ErrorCode']}: {
                            error['ErrorMessage']}",
                        "provider": "aws_comprehend",
                    }

        except Exception as e:
            logger.error("Batch sentiment analysis failed: {0}".format(str(e)))
            # Fill remaining None results with errors
            for i in range(len(results)):
                if results[i] is None:
                    results[i] = {
                        "label": "ERROR",
                        "score": 0.0,
                        "text": texts[i],
                        "message": "Batch analysis failed: {0}".format(str(e)),
                        "provider": "aws_comprehend",
                    }

        # Fill any empty slots with error results
        for i in range(len(results)):
            if results[i] is None:
                results[i] = {
                    "label": "ERROR",
                    "score": 0.0,
                    "text": texts[i],
                    "message": "Text was empty or whitespace.",
                    "provider": "aws_comprehend",
                }

        return results

    def batch_analyze(self, texts: List[str], **kwargs) -> List[Dict[str, Any]]:
        """Alias for analyze_batch to maintain compatibility."""
        return self.analyze_batch(texts, **kwargs)
