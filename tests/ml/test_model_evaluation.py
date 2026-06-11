"""
Tests for ML model evaluation and metrics calculation.

This module tests model evaluation metrics, performance measurement,
and evaluation pipeline components.
"""

import json
import math
import os
import sys
import tempfile
from unittest.mock import Mock, MagicMock, patch

import pytest
import torch
import numpy as np

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), "../../.."))


class TestModelEvaluation:
    """Test suite for model evaluation and metrics."""

    @pytest.fixture
    def sample_predictions(self):
        """Sample model predictions for testing."""
        return {
            "predictions": [0.8, 0.2, 0.9, 0.1, 0.7, 0.3],  # Confidence scores for "real"
            "labels": [1, 0, 1, 0, 1, 0],  # True labels: 1=real, 0=fake
            "logits": [
                [0.2, 0.8], [0.8, 0.2], [0.1, 0.9],
                [0.9, 0.1], [0.3, 0.7], [0.7, 0.3]
            ]
        }

    @pytest.fixture
    def evaluation_config(self):
        """Configuration for evaluation."""
        return {
            "threshold": 0.5,
            "metrics": ["accuracy", "precision", "recall", "f1", "auc"],
            "save_predictions": True,
            "save_confusion_matrix": True
        }

    def test_accuracy_calculation(self, sample_predictions):
        """Test accuracy metric calculation."""
        predictions = sample_predictions["predictions"]
        labels = sample_predictions["labels"]
        threshold = 0.5
        
        # Convert predictions to binary using threshold
        binary_preds = [1 if p >= threshold else 0 for p in predictions]
        
        # Calculate accuracy
        correct = sum(1 for pred, label in zip(binary_preds, labels) if pred == label)
        accuracy = correct / len(labels)
        
        # Verify calculation
        expected_binary_preds = [1, 0, 1, 0, 1, 0]  # Based on threshold
        assert binary_preds == expected_binary_preds
        assert accuracy == 1.0  # Perfect accuracy for this sample

    def test_precision_calculation(self, sample_predictions):
        """Test precision metric calculation."""
        predictions = sample_predictions["predictions"]
        labels = sample_predictions["labels"]
        threshold = 0.5
        
        # Convert to binary predictions
        binary_preds = [1 if p >= threshold else 0 for p in predictions]
        
        # Calculate precision for positive class (real news)
        true_positives = sum(1 for pred, label in zip(binary_preds, labels) 
                           if pred == 1 and label == 1)
        predicted_positives = sum(binary_preds)
        
        precision = true_positives / predicted_positives if predicted_positives > 0 else 0
        
        # Verify calculation
        assert true_positives == 3  # All positive predictions are correct
        assert predicted_positives == 3
        assert precision == 1.0

    def test_recall_calculation(self, sample_predictions):
        """Test recall metric calculation."""
        predictions = sample_predictions["predictions"]
        labels = sample_predictions["labels"]
        threshold = 0.5
        
        # Convert to binary predictions
        binary_preds = [1 if p >= threshold else 0 for p in predictions]
        
        # Calculate recall for positive class (real news)
        true_positives = sum(1 for pred, label in zip(binary_preds, labels) 
                           if pred == 1 and label == 1)
        actual_positives = sum(labels)
        
        recall = true_positives / actual_positives if actual_positives > 0 else 0
        
        # Verify calculation
        assert true_positives == 3
        assert actual_positives == 3  # 3 real news samples
        assert recall == 1.0

    def test_f1_score_calculation(self, sample_predictions):
        """Test F1 score calculation."""
        predictions = sample_predictions["predictions"]
        labels = sample_predictions["labels"]
        threshold = 0.5
        
        # Convert to binary predictions
        binary_preds = [1 if p >= threshold else 0 for p in predictions]
        
        # Calculate precision and recall
        true_positives = sum(1 for pred, label in zip(binary_preds, labels) 
                           if pred == 1 and label == 1)
        predicted_positives = sum(binary_preds)
        actual_positives = sum(labels)
        
        precision = true_positives / predicted_positives if predicted_positives > 0 else 0
        recall = true_positives / actual_positives if actual_positives > 0 else 0
        
        # Calculate F1 score
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        # Verify calculation
        assert f1 == 1.0  # Perfect F1 score

    def test_confusion_matrix_calculation(self, sample_predictions):
        """Test confusion matrix calculation."""
        predictions = sample_predictions["predictions"]
        labels = sample_predictions["labels"]
        threshold = 0.5
        
        # Convert to binary predictions
        binary_preds = [1 if p >= threshold else 0 for p in predictions]
        
        # Calculate confusion matrix
        true_positives = sum(1 for pred, label in zip(binary_preds, labels) 
                           if pred == 1 and label == 1)
        true_negatives = sum(1 for pred, label in zip(binary_preds, labels) 
                           if pred == 0 and label == 0)
        false_positives = sum(1 for pred, label in zip(binary_preds, labels) 
                            if pred == 1 and label == 0)
        false_negatives = sum(1 for pred, label in zip(binary_preds, labels) 
                            if pred == 0 and label == 1)
        
        confusion_matrix = {
            "tp": true_positives,
            "tn": true_negatives,
            "fp": false_positives,
            "fn": false_negatives
        }
        
        # Verify confusion matrix
        assert confusion_matrix["tp"] == 3
        assert confusion_matrix["tn"] == 3
        assert confusion_matrix["fp"] == 0
        assert confusion_matrix["fn"] == 0

    def test_auc_calculation_mock(self, sample_predictions):
        """Test AUC calculation (mocked)."""
        predictions = sample_predictions["predictions"]
        labels = sample_predictions["labels"]
        
        # Mock AUC calculation (in real implementation, would use sklearn)
        # For perfect classification, AUC should be 1.0
        mock_auc = 1.0
        
        # Verify AUC is in valid range
        assert 0.0 <= mock_auc <= 1.0

    def test_roc_curve_calculation_mock(self, sample_predictions):
        """Test ROC curve calculation (mocked)."""
        predictions = sample_predictions["predictions"]
        labels = sample_predictions["labels"]
        
        # Mock ROC curve points
        mock_fpr = [0.0, 0.0, 1.0]  # False positive rates
        mock_tpr = [0.0, 1.0, 1.0]  # True positive rates
        mock_thresholds = [1.0, 0.5, 0.0]
        
        # Verify ROC curve properties
        assert len(mock_fpr) == len(mock_tpr)
        assert len(mock_fpr) == len(mock_thresholds)
        assert all(0.0 <= fpr <= 1.0 for fpr in mock_fpr)
        assert all(0.0 <= tpr <= 1.0 for tpr in mock_tpr)

    def test_per_class_metrics(self, sample_predictions):
        """Test per-class metrics calculation."""
        predictions = sample_predictions["predictions"]
        labels = sample_predictions["labels"]
        threshold = 0.5
        
        binary_preds = [1 if p >= threshold else 0 for p in predictions]
        
        # Calculate metrics for each class
        classes = [0, 1]  # Fake, Real
        class_metrics = {}
        
        for cls in classes:
            # True positives for this class
            tp = sum(1 for pred, label in zip(binary_preds, labels) 
                    if pred == cls and label == cls)
            
            # False positives for this class
            fp = sum(1 for pred, label in zip(binary_preds, labels) 
                    if pred == cls and label != cls)
            
            # False negatives for this class
            fn = sum(1 for pred, label in zip(binary_preds, labels) 
                    if pred != cls and label == cls)
            
            # Calculate class-specific metrics
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
            
            class_metrics[cls] = {
                "precision": precision,
                "recall": recall,
                "f1": f1
            }
        
        # Verify class metrics
        assert 0 in class_metrics  # Fake news class
        assert 1 in class_metrics  # Real news class
        
        # For this perfect classification sample
        assert class_metrics[0]["precision"] == 1.0
        assert class_metrics[0]["recall"] == 1.0
        assert class_metrics[1]["precision"] == 1.0
        assert class_metrics[1]["recall"] == 1.0

    def test_macro_averaged_metrics(self, sample_predictions):
        """Test macro-averaged metrics calculation."""
        predictions = sample_predictions["predictions"]
        labels = sample_predictions["labels"]
        threshold = 0.5
        
        binary_preds = [1 if p >= threshold else 0 for p in predictions]
        
        # Calculate per-class metrics first
        classes = [0, 1]
        class_precisions = []
        class_recalls = []
        class_f1s = []
        
        for cls in classes:
            tp = sum(1 for pred, label in zip(binary_preds, labels) 
                    if pred == cls and label == cls)
            fp = sum(1 for pred, label in zip(binary_preds, labels) 
                    if pred == cls and label != cls)
            fn = sum(1 for pred, label in zip(binary_preds, labels) 
                    if pred != cls and label == cls)
            
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
            
            class_precisions.append(precision)
            class_recalls.append(recall)
            class_f1s.append(f1)
        
        # Calculate macro averages
        macro_precision = sum(class_precisions) / len(class_precisions)
        macro_recall = sum(class_recalls) / len(class_recalls)
        macro_f1 = sum(class_f1s) / len(class_f1s)
        
        # Verify macro averages
        assert macro_precision == 1.0
        assert macro_recall == 1.0
        assert macro_f1 == 1.0

    def test_weighted_averaged_metrics(self, sample_predictions):
        """Test weighted-averaged metrics calculation."""
        predictions = sample_predictions["predictions"]
        labels = sample_predictions["labels"]
        threshold = 0.5
        
        binary_preds = [1 if p >= threshold else 0 for p in predictions]
        
        # Calculate class weights (support)
        class_supports = {}
        for cls in [0, 1]:
            class_supports[cls] = sum(1 for label in labels if label == cls)
        
        total_support = sum(class_supports.values())
        
        # Calculate weighted metrics
        weighted_precision = 0
        weighted_recall = 0
        weighted_f1 = 0
        
        for cls in [0, 1]:
            tp = sum(1 for pred, label in zip(binary_preds, labels) 
                    if pred == cls and label == cls)
            fp = sum(1 for pred, label in zip(binary_preds, labels) 
                    if pred == cls and label != cls)
            fn = sum(1 for pred, label in zip(binary_preds, labels) 
                    if pred != cls and label == cls)
            
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
            
            weight = class_supports[cls] / total_support
            weighted_precision += precision * weight
            weighted_recall += recall * weight
            weighted_f1 += f1 * weight
        
        # Verify weighted averages
        assert weighted_precision == 1.0
        assert weighted_recall == 1.0
        assert weighted_f1 == 1.0

    def test_threshold_sensitivity_analysis(self, sample_predictions):
        """Test model performance across different thresholds."""
        predictions = sample_predictions["predictions"]
        labels = sample_predictions["labels"]
        
        thresholds = [0.1, 0.3, 0.5, 0.7, 0.9]
        threshold_results = {}
        
        for threshold in thresholds:
            binary_preds = [1 if p >= threshold else 0 for p in predictions]
            
            # Calculate accuracy for this threshold
            correct = sum(1 for pred, label in zip(binary_preds, labels) if pred == label)
            accuracy = correct / len(labels)
            
            threshold_results[threshold] = accuracy
        
        # Verify results for each threshold
        assert len(threshold_results) == len(thresholds)
        for threshold, accuracy in threshold_results.items():
            assert 0.0 <= accuracy <= 1.0

    def test_evaluation_batch_processing(self, sample_predictions):
        """Test evaluation with batch processing."""
        batch_size = 2
        predictions = sample_predictions["predictions"]
        labels = sample_predictions["labels"]
        
        # Process in batches
        total_correct = 0
        total_samples = 0
        
        for i in range(0, len(predictions), batch_size):
            batch_preds = predictions[i:i+batch_size]
            batch_labels = labels[i:i+batch_size]
            
            # Convert to binary predictions
            binary_preds = [1 if p >= 0.5 else 0 for p in batch_preds]
            
            # Count correct predictions in batch
            batch_correct = sum(1 for pred, label in zip(binary_preds, batch_labels) 
                              if pred == label)
            
            total_correct += batch_correct
            total_samples += len(batch_labels)
        
        # Calculate overall accuracy
        accuracy = total_correct / total_samples
        assert accuracy == 1.0

    def test_evaluation_with_missing_labels(self):
        """Test evaluation handling when some labels are missing."""
        predictions = [0.8, 0.2, 0.9, 0.1]
        labels = [1, 0, None, 0]  # One missing label
        
        # Filter out samples with missing labels
        valid_pairs = [(pred, label) for pred, label in zip(predictions, labels) 
                      if label is not None]
        
        if valid_pairs:
            valid_preds, valid_labels = zip(*valid_pairs)
            
            # Calculate accuracy on valid samples only
            binary_preds = [1 if p >= 0.5 else 0 for p in valid_preds]
            correct = sum(1 for pred, label in zip(binary_preds, valid_labels) 
                         if pred == label)
            accuracy = correct / len(valid_labels)
            
            assert len(valid_pairs) == 3  # One sample filtered out
            assert accuracy == 1.0

    def test_evaluation_error_handling(self):
        """Test evaluation error handling for edge cases."""
        # Test with empty predictions
        with pytest.raises((ValueError, ZeroDivisionError)):
            predictions = []
            labels = []
            accuracy = sum(1 for pred, label in zip(predictions, labels) 
                          if pred == label) / len(labels)
        
        # Test with mismatched lengths
        with pytest.raises((ValueError, AssertionError)):
            predictions = [0.8, 0.2]
            labels = [1, 0, 1]  # Different length
            assert len(predictions) == len(labels)

    def test_model_calibration(self, sample_predictions):
        """Test model calibration analysis."""
        predictions = sample_predictions["predictions"]
        labels = sample_predictions["labels"]
        
        # Bin predictions by confidence level
        bins = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
        bin_accuracies = {}
        bin_confidences = {}
        bin_counts = {}
        
        for i in range(len(bins) - 1):
            bin_start, bin_end = bins[i], bins[i + 1]
            
            # Find predictions in this bin
            bin_indices = [j for j, pred in enumerate(predictions) 
                          if bin_start <= pred < bin_end or (bin_end == 1.0 and pred == 1.0)]
            
            if bin_indices:
                bin_preds = [predictions[j] for j in bin_indices]
                bin_labels = [labels[j] for j in bin_indices]
                
                # Calculate bin accuracy and average confidence
                binary_preds = [1 if p >= 0.5 else 0 for p in bin_preds]
                bin_accuracy = sum(1 for pred, label in zip(binary_preds, bin_labels) 
                                 if pred == label) / len(bin_labels)
                bin_confidence = sum(bin_preds) / len(bin_preds)
                
                bin_accuracies[i] = bin_accuracy
                bin_confidences[i] = bin_confidence
                bin_counts[i] = len(bin_indices)
        
        # Verify calibration data
        for bin_idx in bin_accuracies:
            assert 0.0 <= bin_accuracies[bin_idx] <= 1.0
            assert 0.0 <= bin_confidences[bin_idx] <= 1.0
            assert bin_counts[bin_idx] > 0

    def test_evaluation_metrics_export(self, sample_predictions, evaluation_config):
        """Test exporting evaluation metrics to file."""
        predictions = sample_predictions["predictions"]
        labels = sample_predictions["labels"]
        
        # Calculate metrics
        binary_preds = [1 if p >= 0.5 else 0 for p in predictions]
        accuracy = sum(1 for pred, label in zip(binary_preds, labels) 
                      if pred == label) / len(labels)
        
        # Create metrics report
        metrics_report = {
            "accuracy": accuracy,
            "num_samples": len(labels),
            "threshold": 0.5,
            "timestamp": "2025-08-29T12:00:00Z",
            "config": evaluation_config
        }
        
        # Verify report structure
        assert "accuracy" in metrics_report
        assert "num_samples" in metrics_report
        assert "threshold" in metrics_report
        assert "timestamp" in metrics_report
        assert "config" in metrics_report

    def test_cross_validation_evaluation(self):
        """Test cross-validation evaluation setup."""
        # Mock cross-validation folds
        num_folds = 5
        fold_results = []
        
        for fold in range(num_folds):
            # Mock fold evaluation
            mock_accuracy = 0.85 + (fold * 0.02)  # Varying accuracy per fold
            fold_results.append({
                "fold": fold,
                "accuracy": mock_accuracy,
                "precision": mock_accuracy + 0.01,
                "recall": mock_accuracy - 0.01,
                "f1": mock_accuracy
            })
        
        # Calculate cross-validation statistics
        cv_accuracy = sum(result["accuracy"] for result in fold_results) / num_folds
        cv_std = math.sqrt(sum((result["accuracy"] - cv_accuracy) ** 2 
                              for result in fold_results) / num_folds)
        
        # Verify cross-validation results
        assert len(fold_results) == num_folds
        assert 0.0 <= cv_accuracy <= 1.0
        assert cv_std >= 0.0

    def test_evaluation_memory_efficiency(self):
        """Test memory-efficient evaluation for large datasets."""
        # Mock large dataset evaluation
        total_samples = 10000
        batch_size = 100
        
        running_accuracy = 0.0
        processed_samples = 0
        
        # Simulate batch processing
        for batch_start in range(0, total_samples, batch_size):
            batch_end = min(batch_start + batch_size, total_samples)
            batch_size_actual = batch_end - batch_start
            
            # Mock batch accuracy
            batch_accuracy = 0.85  # Fixed for simulation
            
            # Update running statistics
            running_accuracy = (running_accuracy * processed_samples + 
                              batch_accuracy * batch_size_actual) / (processed_samples + batch_size_actual)
            processed_samples += batch_size_actual
        
        # Verify final results
        assert processed_samples == total_samples
        assert abs(running_accuracy - 0.85) < 1e-6


if __name__ == "__main__":
    pytest.main([__file__])
