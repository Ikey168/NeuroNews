"""
Sentiment Analysis Pipeline for NeuroNews
Supports both Hugging Face transformers and AWS Comprehend for sentiment analysis.
"""

from typing import Dict, Union, List, Optional, Literal
import logging
import boto3
from abc import ABC, abstractmethod
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

class BaseSentimentAnalyzer(ABC):
    """Base class for sentiment analysis implementations."""
    
    def preprocess_text(self, text: str) -> str:
        """
        Preprocess the input text before sentiment analysis.
        
        Args:
            text (str): Input text to preprocess.
            
        Returns:
            str: Preprocessed text.
        """
        if not isinstance(text, str):
            raise ValueError("Input must be a string")
            
        # Remove extra whitespace
        text = " ".join(text.split())
        
        # Basic cleaning
        text = text.strip()
        
        return text

    @abstractmethod
    def analyze_sentiment(self, text: str, return_all_scores: bool = False) -> Dict[str, Union[str, float, List[Dict]]]:
        """Analyze sentiment of given text."""
        pass

    @abstractmethod
    def batch_analyze(self, texts: List[str], batch_size: Optional[int] = 32) -> List[Dict]:
        """Analyze sentiment of multiple texts."""
        pass

class HuggingFaceSentimentAnalyzer(BaseSentimentAnalyzer):
    """Sentiment analysis using Hugging Face transformers."""
    
    def __init__(self, model_name: str = "finiteautomata/bertweet-base-sentiment-analysis"):
        """
        Initialize the Hugging Face sentiment analyzer.
        
        Args:
            model_name (str): Name of the pre-trained model to use.
        """
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
            self.sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model=self.model,
                tokenizer=self.tokenizer
            )
            logger.info(f"Successfully initialized HuggingFace pipeline with model: {model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize HuggingFace pipeline: {str(e)}")
            raise

    def analyze_sentiment(self, text: str, return_all_scores: bool = False) -> Dict[str, Union[str, float, List[Dict]]]:
        """
        Analyze sentiment using Hugging Face model.
        
        Args:
            text (str): Text to analyze.
            return_all_scores (bool): Whether to return scores for all sentiment classes.
            
        Returns:
            dict: Sentiment analysis results.
        """
        try:
            processed_text = self.preprocess_text(text)
            
            if not processed_text:
                raise ValueError("Text is empty after preprocessing")

            result = self.sentiment_pipeline(processed_text, return_all_scores=return_all_scores)[0]
            
            response = {
                "text": text,
                "sentiment": result["label"],
                "confidence": result["score"],
                "provider": "huggingface"
            }
            
            if return_all_scores:
                response["all_scores"] = result
                
            return response
            
        except Exception as e:
            logger.error(f"Error during HuggingFace sentiment analysis: {str(e)}")
            raise

    def batch_analyze(self, texts: List[str], batch_size: Optional[int] = 32) -> List[Dict]:
        """
        Perform batch sentiment analysis using Hugging Face model.
        
        Args:
            texts (List[str]): List of texts to analyze.
            batch_size (int, optional): Size of batches for processing.
            
        Returns:
            List[Dict]: List of sentiment analysis results.
        """
        try:
            results = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                processed_batch = [self.preprocess_text(text) for text in batch]
                batch_results = self.sentiment_pipeline(processed_batch)
                
                for text, result in zip(batch, batch_results):
                    results.append({
                        "text": text,
                        "sentiment": result["label"],
                        "confidence": result["score"],
                        "provider": "huggingface"
                    })
                    
            return results
            
        except Exception as e:
            logger.error(f"Error during batch HuggingFace sentiment analysis: {str(e)}")
            raise

class AWSComprehendAnalyzer(BaseSentimentAnalyzer):
    """Sentiment analysis using AWS Comprehend."""
    
    def __init__(self, region_name: Optional[str] = None, aws_access_key_id: Optional[str] = None,
                 aws_secret_access_key: Optional[str] = None):
        """
        Initialize AWS Comprehend client.
        
        Args:
            region_name (str, optional): AWS region name.
            aws_access_key_id (str, optional): AWS access key ID.
            aws_secret_access_key (str, optional): AWS secret access key.
        """
        try:
            self.client = boto3.client(
                'comprehend',
                region_name=region_name,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key
            )
            logger.info("Successfully initialized AWS Comprehend client")
        except Exception as e:
            logger.error(f"Failed to initialize AWS Comprehend client: {str(e)}")
            raise

    def _map_aws_sentiment(self, aws_sentiment: str) -> str:
        """Map AWS sentiment labels to standard format."""
        mapping = {
            'POSITIVE': 'positive',
            'NEGATIVE': 'negative',
            'NEUTRAL': 'neutral',
            'MIXED': 'mixed'
        }
        return mapping.get(aws_sentiment, aws_sentiment.lower())

    def analyze_sentiment(self, text: str, return_all_scores: bool = False) -> Dict[str, Union[str, float, List[Dict]]]:
        """
        Analyze sentiment using AWS Comprehend.
        
        Args:
            text (str): Text to analyze.
            return_all_scores (bool): Whether to return scores for all sentiment classes.
            
        Returns:
            dict: Sentiment analysis results.
        """
        try:
            processed_text = self.preprocess_text(text)
            
            if not processed_text:
                raise ValueError("Text is empty after preprocessing")

            result = self.client.detect_sentiment(Text=processed_text, LanguageCode='en')
            
            response = {
                "text": text,
                "sentiment": self._map_aws_sentiment(result['Sentiment']),
                "confidence": max(result['SentimentScore'].values()),
                "provider": "aws"
            }
            
            if return_all_scores:
                response["all_scores"] = {
                    k.lower(): v for k, v in result['SentimentScore'].items()
                }
                
            return response
            
        except (BotoCoreError, ClientError) as e:
            logger.error(f"AWS Comprehend API error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error during AWS sentiment analysis: {str(e)}")
            raise

    def batch_analyze(self, texts: List[str], batch_size: Optional[int] = 25) -> List[Dict]:
        """
        Perform batch sentiment analysis using AWS Comprehend.
        
        Args:
            texts (List[str]): List of texts to analyze.
            batch_size (int, optional): Size of batches for processing (max 25 for AWS).
            
        Returns:
            List[Dict]: List of sentiment analysis results.
        """
        try:
            results = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + min(batch_size, 25)]  # AWS limit is 25
                processed_batch = [self.preprocess_text(text) for text in batch]
                
                batch_results = self.client.batch_detect_sentiment(
                    TextList=processed_batch,
                    LanguageCode='en'
                )
                
                for text, result in zip(batch, batch_results['ResultList']):
                    results.append({
                        "text": text,
                        "sentiment": self._map_aws_sentiment(result['Sentiment']),
                        "confidence": max(result['SentimentScore'].values()),
                        "provider": "aws"
                    })
                    
            return results
            
        except (BotoCoreError, ClientError) as e:
            logger.error(f"AWS Comprehend API error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error during batch AWS sentiment analysis: {str(e)}")
            raise

def create_analyzer(provider: Literal["huggingface", "aws"] = "huggingface", **kwargs) -> BaseSentimentAnalyzer:
    """
    Factory function to create sentiment analyzer instance.
    
    Args:
        provider (str): The provider to use ("huggingface" or "aws")
        **kwargs: Additional arguments passed to the analyzer constructor
        
    Returns:
        BaseSentimentAnalyzer: Configured sentiment analyzer instance
    """
    if provider == "huggingface":
        return HuggingFaceSentimentAnalyzer(**kwargs)
    elif provider == "aws":
        return AWSComprehendAnalyzer(**kwargs)
    else:
        raise ValueError(f"Unknown provider: {provider}")

# Example usage
if __name__ == "__main__":
    # Initialize analyzers
    hf_analyzer = create_analyzer("huggingface")
    aws_analyzer = create_analyzer("aws", region_name="us-west-2")
    
    # Example text
    sample_text = "The company reported strong earnings growth and positive outlook for the next quarter."
    
    # Compare results from both providers
    hf_result = hf_analyzer.analyze_sentiment(sample_text, return_all_scores=True)
    aws_result = aws_analyzer.analyze_sentiment(sample_text, return_all_scores=True)
    
    print(f"HuggingFace Result: {hf_result}")
    print(f"AWS Comprehend Result: {aws_result}")