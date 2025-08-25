#!/usr/bin/env python3
"""
Demo script for RAG evaluation with realistic data
"""

import asyncio
import os
import sys

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from evals.run_eval import RAGEvaluator
from datetime import datetime


def create_realistic_dataset():
    """Create a more realistic evaluation dataset."""
    return [
        {
            "question": "What is artificial intelligence?",
            "ground_truth": "Artificial intelligence (AI) is the simulation of human intelligence processes by machines, especially computer systems that can learn and make decisions.",
            "relevant_docs": ["doc_0", "doc_1"],  # These will match simulated docs
        },
        {
            "question": "How does machine learning work?",
            "ground_truth": "Machine learning works by training algorithms on data to recognize patterns and make predictions without being explicitly programmed.",
            "relevant_docs": ["doc_0", "doc_2"],
        },
        {
            "question": "What are neural networks?",
            "ground_truth": "Neural networks are computing systems inspired by biological neural networks that can learn to recognize patterns and make decisions.",
            "relevant_docs": ["doc_1", "doc_3"],
        },
    ]


async def main():
    """Run realistic RAG evaluation demo."""
    print("Starting realistic RAG evaluation demo...")
    
    # Create dataset
    dataset = create_realistic_dataset()
    
    # Initialize evaluator
    evaluator = RAGEvaluator(
        k_values=[1, 3, 5],
        fusion_weights={"semantic": 0.7, "keyword": 0.3},
        reranker_enabled=True,
    )
    
    # Run evaluation
    results = await evaluator.evaluate_dataset(
        dataset=dataset,
        experiment_name="rag_evaluation_demo",
        run_name=f"realistic_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    
    # Print results
    print("\n" + "="*60)
    print("REALISTIC RAG EVALUATION RESULTS")
    print("="*60)
    
    print(f"\nDataset: {results['dataset_size']} queries")
    print(f"Processing time: {results['total_time']:.2f}s")
    
    print("\nKey Metrics:")
    metrics = results['overall_metrics']
    print(f"  Average MRR: {metrics['avg_mrr']:.4f}")
    print(f"  Average Answer F1: {metrics['avg_answer_f1']:.4f}")
    print(f"  Average Recall@1: {metrics['avg_recall_at_1']:.4f}")
    print(f"  Average Recall@3: {metrics['avg_recall_at_3']:.4f}")
    print(f"  Average nDCG@3: {metrics['avg_ndcg_at_3']:.4f}")
    
    print("\nPer-Query Results:")
    for i, result in enumerate(results['per_query_results']):
        print(f"\nQuery {i+1}: {result['question']}")
        print(f"  MRR: {result['mrr']:.4f}")
        print(f"  Answer F1: {result['answer_f1']:.4f}")
        print(f"  Recall@1: {result['recall_at_1']:.4f}")
    
    print(f"\n✅ Evaluation logged to MLflow experiment 'rag_evaluation_demo'")
    print(f"🔗 View at: http://localhost:5001")


if __name__ == "__main__":
    asyncio.run(main())
