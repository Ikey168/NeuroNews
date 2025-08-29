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
    accuracy          logger        result=detector.predict_trustworthiness(article)
        logger.info(f"Article {i + 1}: {article[:100]}...")
        logger.info("Trustworthiness: {0}%".format(result["trustworthiness_score"]))
        logger.info(
            f"Classification: {result['classification']} (confidence: {result['confidence']}%)"
        )sting predictions:")
    for i, article in enumerate(test_articles):
        result=detector.predict_trustworthiness(article)
        logger.info(f"Article {i + 1}: {article[:100]}...")
        logger.info("Trustworthiness: {0}%".format(result["trustworthiness_score"]))
        logger.info(
            f"Classification: {result['classification']} (confidence: {result['confidence']}%)"
        )le in enumerate(test_articles):
        result=detector.predict_trustworthiness(article)
        logger.info(f"Article {i + 1}: {article[:100]}...")
        logger.info("Trustworthiness: {0}%".format(result["trustworthiness_score"]))
        logger.info(
            f"Classification: {result['classification']} (confidence: {result['confidence']}%)"
        )lt=detector.predict_trustworthiness(article)
        logger.info(f"Article {i + 1}: {article[:100]}...")
        logger.info("Trustworthiness: {0}%".format(result["trustworthiness_score"]))
        logger.info(
            f"Classification: {result['classification']} (confidence: {result['confidence']}%)"    confusion_matrix,
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
        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu")

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
