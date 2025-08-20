"""
AI-Based Fake News Detection Module

This module implements fake news detection using transformer models like RoBERTa/DeBERTa.
It includes model training, inference, and integration with the NeuroNews pipeline.
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DebertaForSequenceClassification,
    DebertaTokenizer,
    EvalPrediction,
    RobertaForSequenceClassification,
    RobertaTokenizer,
    Trainer,
    TrainingArguments,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FakeNewsDataset(Dataset):
    """Dataset class for fake news detection training."""

    def __init__(
        self, texts: List[str], labels: List[int], tokenizer, max_length: int = 512
    ):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        text = str(self.texts[idx])
        label = self.labels[idx]

        encoding = self.tokenizer(
            text,
            truncation=True,
            padding="max_length",
            max_length=self.max_length,
            return_tensors="pt",
        )

        return {
            "input_ids": encoding["input_ids"].flatten(),
            "attention_mask": encoding["attention_mask"].flatten(),
            "labels": torch.tensor(label, dtype=torch.long),
        }


class FakeNewsDetector:
    """Main class for fake news detection using transformer models."""

    def __init__(self, model_name: str = "roberta-base", use_pretrained: bool = True):
        """
        Initialize the fake news detector.

        Args:
            model_name: Name of the transformer model to use
            use_pretrained: Whether to use a pretrained model
        """
        self.model_name = model_name
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Load tokenizer and model
        if "roberta" in model_name.lower():
            self.tokenizer = RobertaTokenizer.from_pretrained(model_name)
            if use_pretrained:
                self.model = RobertaForSequenceClassification.from_pretrained(
                    model_name, num_labels=2  # Binary classification: real vs fake
                )
            else:
                self.model = RobertaForSequenceClassification.from_pretrained(
                    model_name, num_labels=2, ignore_mismatched_sizes=True
                )
        elif "deberta" in model_name.lower():
            self.tokenizer = DebertaTokenizer.from_pretrained(model_name)
            if use_pretrained:
                self.model = DebertaForSequenceClassification.from_pretrained(
                    model_name, num_labels=2
                )
            else:
                self.model = DebertaForSequenceClassification.from_pretrained(
                    model_name, num_labels=2, ignore_mismatched_sizes=True
                )
        else:
            # Generic AutoModel
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(
                model_name, num_labels=2
            )

        self.model.to(self.device)
        logger.info("Initialized {0} on {1}".format(model_name, self.device))

    def prepare_liar_dataset(
        self, data_path: str = None
    ) -> Tuple[List[str], List[int]]:
        """
        Prepare the LIAR dataset for training.

        Args:
            data_path: Path to LIAR dataset

        Returns:
            Tuple of (texts, labels)
        """
        # For demo purposes, create synthetic data similar to LIAR dataset
        # In production, load actual LIAR dataset
        texts = [
            "The unemployment rate has dropped to historic lows under the current administration.",
            "Scientists have discovered that vaccines cause autism in children.",
            "The stock market reached record highs due to new economic policies.",
            "Climate change is a hoax created by the Chinese government.",
            "New infrastructure bill will create millions of jobs across the country.",
            "Drinking bleach can cure COVID-19 according to medical experts.",
            "Education funding increased by 15% in the latest budget proposal.",
            "5G towers are spreading coronavirus through radio waves.",
            "Renewable energy costs have decreased significantly over the past decade.",
            "The moon landing was staged in a Hollywood studio.",
            "Healthcare access has improved for rural communities.",
            "Flat Earth theory is supported by new scientific evidence.",
            "Economic growth exceeded expectations in the third quarter.",
            "Microchips in vaccines allow government tracking of citizens.",
            "Public transportation investments reduce urban congestion.",
            "Lizard people secretly control world governments.",
        ]

        # Labels: 0 = fake, 1 = real
        labels = [1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0]

        if data_path and os.path.exists(data_path):
            # Load actual LIAR dataset if available
            try:
                df = pd.read_csv(data_path, sep="\\t")
                texts = df["statement"].tolist()
                # Convert LIAR labels to binary (real vs fake)
                label_mapping = {
                    "true": 1,
                    "mostly-true": 1,
                    "half-true": 1,
                    "mostly-false": 0,
                    "false": 0,
                    "pants-fire": 0,
                }
                labels = [label_mapping.get(label, 0) for label in df["label"]]
                logger.info("Loaded {0} samples from LIAR dataset".format(len(texts)))
            except Exception as e:
                logger.warning(
                    "Could not load LIAR dataset: {0}. Using synthetic data.".format(e)
                )

        return texts, labels

    def train(
        self,
        texts: List[str],
        labels: List[int],
        output_dir: str = "./fake_news_model",
        validation_split: float = 0.2,
        num_epochs: int = 3,
        batch_size: int = 16,
    ) -> Dict[str, float]:
        """
        Train the fake news detection model.

        Args:
            texts: List of text samples
            labels: List of corresponding labels (0=fake, 1=real)
            output_dir: Directory to save the trained model
            validation_split: Fraction of data to use for validation
            num_epochs: Number of training epochs
            batch_size: Training batch size

        Returns:
            Training metrics
        """
        # Split data
        train_texts, val_texts, train_labels, val_labels = train_test_split(
            texts, labels, test_size=validation_split, random_state=42, stratify=labels
        )

        # Create datasets
        train_dataset = FakeNewsDataset(train_texts, train_labels, self.tokenizer)
        val_dataset = FakeNewsDataset(val_texts, val_labels, self.tokenizer)

        # Training arguments
        training_args = TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=num_epochs,
            per_device_train_batch_size=batch_size,
            per_device_eval_batch_size=batch_size,
            warmup_steps=500,
            weight_decay=0.01,
            logging_dir="{0}/logs".format(output_dir),
            evaluation_strategy="epoch",
            save_strategy="epoch",
            load_best_model_at_end=True,
            metric_for_best_model="accuracy",
            greater_is_better=True,
        )

        def compute_metrics(eval_pred: EvalPrediction) -> Dict[str, float]:
            predictions, labels = eval_pred
            predictions = np.argmax(predictions, axis=1)

            accuracy = accuracy_score(labels, predictions)
            precision, recall, f1, _ = precision_recall_fscore_support(
                labels, predictions, average="weighted"
            )

            return {
                "accuracy": accuracy,
                "f1": f1,
                "precision": precision,
                "recall": recall,
            }

        # Initialize trainer
        trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=val_dataset,
            compute_metrics=compute_metrics,
        )

        # Train the model
        logger.info("Starting training...")
        trainer.train()

        # Evaluate the model
        eval_results = trainer.evaluate()
        logger.info("Evaluation results: {0}".format(eval_results))

        # Save the model
        trainer.save_model()
        self.tokenizer.save_pretrained(output_dir)

        logger.info("Model saved to {0}".format(output_dir))
        return eval_results

    def predict_trustworthiness(self, text: str) -> Dict[str, Any]:
        """
        Predict the trustworthiness of a news article.

        Args:
            text: Article text to analyze

        Returns:
            Dictionary containing prediction results
        """
        # Tokenize input
        inputs = self.tokenizer(
            text, truncation=True, padding=True, max_length=512, return_tensors="pt"
        ).to(self.device)

        # Make prediction
        self.model.eval()
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits
            probabilities = torch.softmax(logits, dim=-1)
            predicted_class = torch.argmax(logits, dim=-1).item()

        # Convert to confidence scores
        fake_confidence = probabilities[0][0].item()
        real_confidence = probabilities[0][1].item()

        # Calculate trustworthiness score (0-100)
        trustworthiness_score = real_confidence * 100

        return {
            "trustworthiness_score": round(trustworthiness_score, 2),
            "classification": "real" if predicted_class == 1 else "fake",
            "confidence": round(max(fake_confidence, real_confidence) * 100, 2),
            "fake_probability": round(fake_confidence * 100, 2),
            "real_probability": round(real_confidence * 100, 2),
            "model_used": self.model_name,
            "timestamp": datetime.now().isoformat(),
        }

    def batch_predict(self, texts: List[str]) -> List[Dict[str, Any]]:
        """
        Predict trustworthiness for multiple texts.

        Args:
            texts: List of article texts

        Returns:
            List of prediction results
        """
        results = []
        for text in texts:
            result = self.predict_trustworthiness(text)
            results.append(result)
        return results

    def evaluate_on_dataset(
        self, texts: List[str], labels: List[int]
    ) -> Dict[str, float]:
        """
        Evaluate model performance on a test dataset.

        Args:
            texts: List of test texts
            labels: List of true labels

        Returns:
            Evaluation metrics
        """
        predictions = []
        for text in texts:
            result = self.predict_trustworthiness(text)
            pred_label = 1 if result["classification"] == "real" else 0
            predictions.append(pred_label)

        accuracy = accuracy_score(labels, predictions)
        precision, recall, f1, _ = precision_recall_fscore_support(
            labels, predictions, average="weighted"
        )

        # Confusion matrix
        cm = confusion_matrix(labels, predictions)

        return {
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "confusion_matrix": cm.tolist(),
            "num_samples": len(labels),
        }


class FakeNewsConfig:
    """Configuration for fake news detection."""

    # Model configurations
    MODELS = {
        "roberta-base": "roberta-base",
        "roberta-large": "roberta-large",
        "deberta-v3-base": "microsoft/deberta-v3-base",
        "deberta-v3-large": "microsoft/deberta-v3-large",
    }

    # Training parameters
    DEFAULT_EPOCHS = 3
    DEFAULT_BATCH_SIZE = 16
    DEFAULT_LEARNING_RATE = 2e-5
    DEFAULT_MAX_LENGTH = 512

    # Thresholds
    HIGH_CONFIDENCE_THRESHOLD = 80.0
    MEDIUM_CONFIDENCE_THRESHOLD = 60.0
    TRUSTWORTHINESS_THRESHOLD = 50.0

    # Database table
    VERACITY_TABLE = "article_veracity"


def main():
    """Demo function for fake news detection."""
    logger.info("=== NeuroNews Fake News Detection Demo ===")

    # Initialize detector
    detector = FakeNewsDetector(model_name="roberta-base")

    # Prepare training data
    texts, labels = detector.prepare_liar_dataset()
    logger.info("Prepared {0} training samples".format(len(texts)))

    # Train the model
    metrics = detector.train(texts, labels, num_epochs=2, batch_size=8)
    logger.info("Training completed!")

    # Test predictions
    test_articles = [
        "Breaking: Scientists discover that drinking water is essential for human survival.",
        "SHOCKING: New study reveals that the Earth is actually flat and governments are hiding it.",
        "Economic report shows steady growth in renewable energy sector investments.",
        "EXCLUSIVE: Aliens have been secretly living among us for decades, sources confirm.",
    ]

    logger.info("\\nTesting predictions:")
    for i, article in enumerate(test_articles):
        result = detector.predict_trustworthiness(article)
        logger.info("\\nArticle {0}: {1}...".format(i + 1, article[:100]))
        logger.info("Trustworthiness: {0}%".format(result["trustworthiness_score"]))
        logger.info(
            f"Classification: {
                result['classification']} (confidence: {
                result['confidence']}%)"
        )

    # Evaluate on test set
    eval_results = detector.evaluate_on_dataset(texts[-4:], labels[-4:])
    logger.info("\\nEvaluation results: {0}".format(eval_results))


if __name__ == "__main__":
    main()
