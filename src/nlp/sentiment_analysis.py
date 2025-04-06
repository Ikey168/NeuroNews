"""
Sentiment Analysis Pipeline for NeuroNews
Uses transformers library to perform sentiment analysis on news articles.
"""

from typing import Dict, Union, List, Optional
import logging
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification

logger = logging.getLogger(__name__)

class SentimentAnalyzer:
    """
    A class to handle sentiment analysis of text using transformers.
    """
    
    def __init__(self, model_name: str = "finiteautomata/bertweet-base-sentiment-analysis"):
        """
        Initialize the sentiment analyzer with a specified model.
        
        Args:
            model_name (str): Name of the pre-trained model to use.
                            Defaults to bertweet-base-sentiment-analysis.
        """
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
            self.sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model=self.model,
                tokenizer=self.tokenizer
            )
            logger.info(f"Successfully initialized sentiment analysis pipeline with model: {model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize sentiment analysis pipeline: {str(e)}")
            raise

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

    def analyze_sentiment(self, text: str, return_all_scores: bool = False) -> Dict[str, Union[str, float, List[Dict]]]:
        """
        Analyze the sentiment of the given text.
        
        Args:
            text (str): Text to analyze.
            return_all_scores (bool): Whether to return scores for all sentiment classes.
            
        Returns:
            dict: Dictionary containing sentiment analysis results.
        """
        try:
            # Preprocess the text
            processed_text = self.preprocess_text(text)
            
            if not processed_text:
                raise ValueError("Text is empty after preprocessing")

            # Get sentiment predictions
            result = self.sentiment_pipeline(processed_text, return_all_scores=return_all_scores)[0]
            
            # Prepare response
            response = {
                "text": text,
                "sentiment": result["label"],
                "confidence": result["score"],
            }
            
            if return_all_scores:
                response["all_scores"] = result
                
            return response
            
        except Exception as e:
            logger.error(f"Error during sentiment analysis: {str(e)}")
            raise

    def batch_analyze(self, texts: List[str], batch_size: Optional[int] = 32) -> List[Dict]:
        """
        Perform sentiment analysis on a batch of texts.
        
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
                        "confidence": result["score"]
                    })
                    
            return results
            
        except Exception as e:
            logger.error(f"Error during batch sentiment analysis: {str(e)}")
            raise

# Example usage
if __name__ == "__main__":
    # Initialize the analyzer
    analyzer = SentimentAnalyzer()
    
    # Example text
    sample_text = "The company reported strong earnings growth and positive outlook for the next quarter."
    
    # Analyze sentiment
    result = analyzer.analyze_sentiment(sample_text, return_all_scores=True)
    print(f"Sentiment Analysis Result: {result}")