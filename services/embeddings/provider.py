"""
Embeddings Provider with MLflow Tracking
Issue #217: Instrument embeddings & indexer jobs with MLflow tracking

This module provides a unified interface for generating embeddings with
comprehensive MLflow tracking of parameters, metrics, and artifacts.
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))

try:
    from services.mlops.tracking import mlrun
    from src.nlp.article_embedder import ArticleEmbedder
except ImportError as e:
    print(f"Import error: {e}")
    print("Please ensure you're running from the project root directory")
    sys.exit(1)

# Configure logging
logger = logging.getLogger(__name__)


class EmbeddingsProvider:
    """
    Embeddings provider with MLflow tracking integration.
    
    Features:
    - Multiple embedding models support
    - Batch processing with configurable parameters
    - Comprehensive MLflow tracking
    - Performance metrics monitoring
    - Artifact generation for debugging
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        batch_size: int = 32,
        max_workers: int = 4,
        cache_dir: str = "/tmp/embeddings_cache",
    ):
        """
        Initialize embeddings provider.

        Args:
            model_name: Name of the sentence transformer model
            batch_size: Batch size for processing
            max_workers: Number of worker threads
            cache_dir: Directory for caching models and results
        """
        self.model_name = model_name
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.cache_dir = cache_dir

        # Initialize model
        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name, cache_folder=cache_dir)
        self.embedding_dimension = self.model.get_sentence_embedding_dimension()

        # Metrics tracking
        self.metrics = {
            "documents_processed": 0,
            "embeddings_generated": 0,
            "total_processing_time": 0.0,
            "failures": 0,
            "embeddings_per_second": 0.0,
        }

        # Artifacts storage
        self.artifacts = {
            "sample_embeddings": [],
            "latency_measurements": [],
            "processing_timestamps": [],
        }

    async def generate_embeddings(
        self,
        texts: List[str],
        experiment_name: str = "embeddings_generation",
        run_name: Optional[str] = None,
    ) -> Tuple[List[np.ndarray], Dict[str, Any]]:
        """
        Generate embeddings for a list of texts with MLflow tracking.

        Args:
            texts: List of texts to embed
            experiment_name: MLflow experiment name
            run_name: Optional run name for MLflow

        Returns:
            Tuple of (embeddings, metrics)
        """
        if not run_name:
            run_name = f"embeddings_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        with mlrun(
            experiment_name=experiment_name,
            run_name=run_name,
            description=f"Generate embeddings for {len(texts)} documents"
        ):
            # Log parameters
            import mlflow
            mlflow.log_param("provider", self.__class__.__name__)
            mlflow.log_param("model", self.model_name)
            mlflow.log_param("dimension", self.embedding_dimension)
            mlflow.log_param("batch_size", self.batch_size)
            mlflow.log_param("max_workers", self.max_workers)
            mlflow.log_param("input_count", len(texts))

            # Reset metrics for this run
            self._reset_metrics()

            start_time = time.time()
            embeddings = []
            failed_indices = []

            try:
                # Process in batches
                for i in range(0, len(texts), self.batch_size):
                    batch_start = time.time()
                    batch_texts = texts[i:i + self.batch_size]
                    
                    try:
                        # Generate embeddings for batch
                        batch_embeddings = self.model.encode(
                            batch_texts,
                            batch_size=len(batch_texts),
                            convert_to_numpy=True,
                            show_progress_bar=False,
                        )

                        embeddings.extend(batch_embeddings)
                        
                        # Track batch metrics
                        batch_time = time.time() - batch_start
                        batch_size_actual = len(batch_texts)
                        
                        self.metrics["documents_processed"] += batch_size_actual
                        self.metrics["embeddings_generated"] += batch_size_actual
                        self.metrics["total_processing_time"] += batch_time

                        # Store latency measurements
                        self.artifacts["latency_measurements"].append({
                            "batch_id": i // self.batch_size,
                            "batch_size": batch_size_actual,
                            "processing_time": batch_time,
                            "embeddings_per_second": batch_size_actual / batch_time,
                            "timestamp": datetime.now().isoformat(),
                        })

                        # Sample embeddings for artifacts (first 3 embeddings of first batch)
                        if i == 0 and batch_embeddings is not None:
                            for j, embedding in enumerate(batch_embeddings[:3]):
                                self.artifacts["sample_embeddings"].append({
                                    "text_preview": batch_texts[j][:100] + "..." if len(batch_texts[j]) > 100 else batch_texts[j],
                                    "embedding_norm": float(np.linalg.norm(embedding)),
                                    "embedding_mean": float(np.mean(embedding)),
                                    "embedding_std": float(np.std(embedding)),
                                    "dimensions": len(embedding),
                                })

                        logger.debug(
                            f"Processed batch {i//self.batch_size + 1}: "
                            f"{batch_size_actual} docs in {batch_time:.2f}s "
                            f"({batch_size_actual/batch_time:.1f} docs/sec)"
                        )

                    except Exception as e:
                        logger.error(f"Failed to process batch {i//self.batch_size}: {e}")
                        self.metrics["failures"] += len(batch_texts)
                        failed_indices.extend(range(i, i + len(batch_texts)))
                        # Add zero embeddings for failed items
                        embeddings.extend([np.zeros(self.embedding_dimension) for _ in batch_texts])

                # Calculate final metrics
                total_time = time.time() - start_time
                self.metrics["total_processing_time"] = total_time
                if total_time > 0:
                    self.metrics["embeddings_per_second"] = self.metrics["embeddings_generated"] / total_time

                # Log metrics to MLflow
                mlflow.log_metric("docs_processed", self.metrics["documents_processed"])
                mlflow.log_metric("embeddings_generated", self.metrics["embeddings_generated"])
                mlflow.log_metric("embeddings_per_second", self.metrics["embeddings_per_second"])
                mlflow.log_metric("failures", self.metrics["failures"])
                mlflow.log_metric("total_processing_time", self.metrics["total_processing_time"])
                mlflow.log_metric("success_rate", 
                    (self.metrics["embeddings_generated"] - self.metrics["failures"]) / max(1, self.metrics["embeddings_generated"]))

                # Log artifacts
                await self._log_artifacts(mlflow)

                logger.info(
                    f"Embeddings generation completed: "
                    f"{self.metrics['embeddings_generated']} embeddings in {total_time:.2f}s "
                    f"({self.metrics['embeddings_per_second']:.1f} embeddings/sec), "
                    f"{self.metrics['failures']} failures"
                )

                return embeddings, self.metrics

            except Exception as e:
                logger.error(f"Embeddings generation failed: {e}")
                mlflow.log_metric("failures", len(texts))
                raise

    async def _log_artifacts(self, mlflow):
        """Log artifacts to MLflow."""
        try:
            # Create temporary directory for artifacts
            import tempfile
            with tempfile.TemporaryDirectory() as temp_dir:
                
                # 1. Sample embeddings JSON
                sample_file = os.path.join(temp_dir, "sample_embeddings.json")
                with open(sample_file, "w") as f:
                    json.dump(self.artifacts["sample_embeddings"], f, indent=2)
                mlflow.log_artifact(sample_file, "embeddings_samples")

                # 2. Latency histogram data
                latency_file = os.path.join(temp_dir, "latency_histogram.json")
                latency_data = {
                    "measurements": self.artifacts["latency_measurements"],
                    "summary": {
                        "total_batches": len(self.artifacts["latency_measurements"]),
                        "avg_latency": np.mean([m["processing_time"] for m in self.artifacts["latency_measurements"]]) if self.artifacts["latency_measurements"] else 0,
                        "min_latency": np.min([m["processing_time"] for m in self.artifacts["latency_measurements"]]) if self.artifacts["latency_measurements"] else 0,
                        "max_latency": np.max([m["processing_time"] for m in self.artifacts["latency_measurements"]]) if self.artifacts["latency_measurements"] else 0,
                        "avg_throughput": np.mean([m["embeddings_per_second"] for m in self.artifacts["latency_measurements"]]) if self.artifacts["latency_measurements"] else 0,
                    }
                }
                with open(latency_file, "w") as f:
                    json.dump(latency_data, f, indent=2)
                mlflow.log_artifact(latency_file, "performance")

                # 3. Model info
                model_info_file = os.path.join(temp_dir, "model_info.json")
                model_info = {
                    "model_name": self.model_name,
                    "embedding_dimension": self.embedding_dimension,
                    "batch_size": self.batch_size,
                    "max_workers": self.max_workers,
                    "cache_dir": self.cache_dir,
                    "model_max_seq_length": getattr(self.model, "max_seq_length", "unknown"),
                }
                with open(model_info_file, "w") as f:
                    json.dump(model_info, f, indent=2)
                mlflow.log_artifact(model_info_file, "model")

                logger.debug("Artifacts logged to MLflow")

        except Exception as e:
            logger.warning(f"Failed to log artifacts: {e}")

    def _reset_metrics(self):
        """Reset metrics for a new run."""
        self.metrics = {
            "documents_processed": 0,
            "embeddings_generated": 0,
            "total_processing_time": 0.0,
            "failures": 0,
            "embeddings_per_second": 0.0,
        }
        
        self.artifacts = {
            "sample_embeddings": [],
            "latency_measurements": [],
            "processing_timestamps": [],
        }

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        return self.metrics.copy()

    def get_model_info(self) -> Dict[str, Any]:
        """Get model information."""
        return {
            "model_name": self.model_name,
            "embedding_dimension": self.embedding_dimension,
            "batch_size": self.batch_size,
            "max_workers": self.max_workers,
            "cache_dir": self.cache_dir,
        }


async def main():
    """Demo usage of EmbeddingsProvider with MLflow tracking."""
    provider = EmbeddingsProvider(
        model_name="all-MiniLM-L6-v2",
        batch_size=16,
    )

    # Sample texts
    sample_texts = [
        "Breaking news: Major technological breakthrough announced today",
        "Scientists discover new method for renewable energy production", 
        "Global markets respond positively to economic policy changes",
        "Artificial intelligence revolutionizes healthcare diagnostics",
        "Climate change summit reaches historic agreement",
    ]

    logger.info(f"Generating embeddings for {len(sample_texts)} sample texts")
    
    embeddings, metrics = await provider.generate_embeddings(
        sample_texts,
        experiment_name="embeddings_demo",
        run_name="demo_run"
    )

    print(f"Generated {len(embeddings)} embeddings")
    print(f"Metrics: {metrics}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
