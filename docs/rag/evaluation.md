# RAG Evaluation Framework

This document describes the RAG (Retrieval-Augmented Generation) evaluation framework with MLflow integration for comprehensive performance tracking and analysis.

## Overview

The RAG evaluation framework provides systematic evaluation of the retrieval and generation pipeline using industry-standard metrics. All evaluation runs are tracked in MLflow with detailed metrics, configuration parameters, and artifacts.

## Evaluation Metrics

### Retrieval Metrics

#### Recall@k
- **Description**: Proportion of relevant documents retrieved in the top-k results
- **Formula**: `|relevant ∩ retrieved@k| / |relevant|`
- **Range**: [0, 1] (higher is better)
- **Interpretation**: How well the system finds relevant documents

#### nDCG@k (Normalized Discounted Cumulative Gain)
- **Description**: Ranking quality metric that considers position of relevant documents
- **Formula**: `DCG@k / IDCG@k`
- **Range**: [0, 1] (higher is better)
- **Interpretation**: How well relevant documents are ranked (position matters)

#### MRR (Mean Reciprocal Rank)
- **Description**: Average of reciprocal ranks of first relevant document
- **Formula**: `1 / rank_of_first_relevant_document`
- **Range**: [0, 1] (higher is better)
- **Interpretation**: How quickly users find relevant information

### Generation Metrics

#### Answer F1 Score
- **Description**: Token-level F1 score between generated and ground truth answers
- **Formula**: `2 * (precision * recall) / (precision + recall)`
- **Range**: [0, 1] (higher is better)
- **Interpretation**: Quality of generated answers compared to expected responses

## Usage

### Basic Evaluation

```python
from evals.run_eval import RAGEvaluator, create_sample_dataset

# Create evaluator
evaluator = RAGEvaluator(
    k_values=[1, 3, 5, 10],
    fusion_weights={"semantic": 0.7, "keyword": 0.3},
    reranker_enabled=True
)

# Load or create dataset
dataset = create_sample_dataset()

# Run evaluation
results = await evaluator.evaluate_dataset(
    dataset=dataset,
    experiment_name="my_rag_evaluation",
    run_name="baseline_v1"
)
```

### Dataset Format

Evaluation datasets should follow this format:

```python
dataset = [
    {
        "question": "What is artificial intelligence?",
        "ground_truth": "AI is the simulation of human intelligence in machines...",
        "relevant_docs": ["doc_1", "doc_3", "doc_7"]  # List of relevant document IDs
    },
    # ... more examples
]
```

### Configuration Parameters

The framework logs the following configuration parameters to MLflow:

#### Retrieval Configuration
- `k_values`: List of k values to evaluate (e.g., [1, 3, 5, 10])
- `max_k`: Maximum k value used for retrieval
- `reranker_enabled`: Whether document reranking is enabled

#### Fusion Weights
- `fusion_weight_semantic`: Weight for semantic search (0.0-1.0)
- `fusion_weight_keyword`: Weight for keyword search (0.0-1.0)

#### RAG Service Settings
- `rag_default_k`: Default number of documents to retrieve
- `rag_fusion_enabled`: Whether query fusion is enabled
- `rag_answer_provider`: Answer generation provider (openai/anthropic/local)

## MLflow Integration

### Logged Metrics

#### Performance Metrics
- `total_evaluation_time_s`: Total time for evaluation run
- `queries_evaluated`: Number of queries in dataset
- `avg_query_time_ms`: Average time per query
- `avg_retrieved_docs`: Average number of documents retrieved

#### Retrieval Quality
- `avg_recall_at_k`: Average Recall@k for each k value
- `avg_ndcg_at_k`: Average nDCG@k for each k value
- `avg_mrr`: Average Mean Reciprocal Rank

#### Generation Quality
- `avg_answer_f1`: Average F1 score for generated answers

### Artifacts

#### Per-Query Results CSV
- **File**: `evaluation_results/per_query_results.csv`
- **Content**: Detailed results for each query including:
  - Question and generated answer
  - All metric values (Recall@k, nDCG@k, MRR, Answer_F1)
  - Query processing time
  - Retrieved document count

### Experiment Organization

```
MLflow Experiments
├── rag_evaluation/
│   ├── baseline_v1/
│   │   ├── metrics: recall@k, nDCG@k, MRR, Answer_F1
│   │   ├── params: k_values, fusion_weights, reranker_enabled
│   │   └── artifacts: per_query_results.csv
│   ├── fusion_weights_tuning/
│   └── reranker_comparison/
```

## Evaluation Workflows

### 1. Baseline Evaluation

Establish baseline performance with default settings:

```bash
cd /workspaces/NeuroNews
python evals/run_eval.py
```

### 2. Parameter Tuning

Evaluate different configurations:

```python
# Test different k values
evaluator = RAGEvaluator(k_values=[1, 3, 5, 10, 20])

# Test fusion weights
evaluator = RAGEvaluator(fusion_weights={"semantic": 0.8, "keyword": 0.2})

# Test with/without reranker
evaluator = RAGEvaluator(reranker_enabled=False)
```

### 3. Model Comparison

Compare different answer generation providers:

```python
providers = ["openai", "anthropic", "local"]

for provider in providers:
    rag_service = RAGAnswerService(answer_provider=provider)
    evaluator = RAGEvaluator(rag_service=rag_service)
    
    results = await evaluator.evaluate_dataset(
        dataset=dataset,
        run_name=f"provider_{provider}"
    )
```

## Interpreting Results

### Good Performance Indicators
- **Recall@1 > 0.5**: System finds relevant documents quickly
- **Recall@5 > 0.8**: System has good coverage of relevant documents
- **nDCG@5 > 0.7**: Relevant documents are well-ranked
- **MRR > 0.6**: First relevant document appears early in results
- **Answer_F1 > 0.6**: Generated answers have good overlap with ground truth

### Performance Analysis

#### Low Recall@k
- **Possible Causes**: Poor embeddings, insufficient document coverage, weak query processing
- **Solutions**: Improve embeddings model, expand document corpus, enhance query expansion

#### Low nDCG@k but High Recall@k
- **Possible Causes**: Ranking algorithm issues, reranker problems
- **Solutions**: Tune reranking model, adjust fusion weights, improve scoring

#### Low MRR
- **Possible Causes**: Relevant documents ranked too low
- **Solutions**: Improve initial ranking, enhance query-document matching

#### Low Answer_F1
- **Possible Causes**: Poor generation model, insufficient context, bad prompting
- **Solutions**: Improve generation prompts, provide more context, tune generation parameters

## Best Practices

### Dataset Creation
1. **Diverse Questions**: Include various question types (factual, explanatory, comparative)
2. **Quality Ground Truth**: Ensure accurate and complete reference answers
3. **Relevant Documents**: Manually verify document relevance for accuracy
4. **Sufficient Size**: Use at least 50+ examples for reliable evaluation

### Evaluation Process
1. **Version Control**: Track dataset versions and changes
2. **Reproducibility**: Set random seeds and document configurations
3. **Multiple Runs**: Run multiple evaluations to account for variance
4. **Progressive Evaluation**: Start with small datasets, scale up gradually

### Monitoring and Alerts
1. **Performance Regression**: Set up alerts for significant metric drops
2. **Regular Evaluation**: Schedule periodic evaluations on production data
3. **A/B Testing**: Compare new models against baseline using evaluation framework

## Advanced Usage

### Custom Metrics

Add custom evaluation metrics by extending the `RAGEvaluator` class:

```python
class CustomRAGEvaluator(RAGEvaluator):
    def _calculate_custom_metric(self, generated_answer, ground_truth):
        # Implement custom metric calculation
        pass
        
    async def _evaluate_single_query(self, example):
        result = await super()._evaluate_single_query(example)
        # Add custom metrics to result
        result["custom_metric"] = self._calculate_custom_metric(
            result["generated_answer"], 
            result["ground_truth"]
        )
        return result
```

### Integration with CI/CD

Add evaluation to your continuous integration pipeline:

```yaml
# .github/workflows/rag_evaluation.yml
name: RAG Evaluation
on: [push, pull_request]

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run RAG Evaluation
        run: |
          python evals/run_eval.py
          # Fail if metrics below threshold
          python scripts/check_eval_thresholds.py
```

## Troubleshooting

### Common Issues

#### ImportError: Required modules not available
- **Solution**: Ensure you're running from project root directory
- **Check**: Python path and module imports

#### MLflow tracking errors
- **Solution**: Verify MLflow server is running and accessible
- **Check**: MLflow configuration and credentials

#### Memory issues with large datasets
- **Solution**: Process datasets in batches
- **Implementation**: Add batch processing to `evaluate_dataset` method

#### Inconsistent results across runs
- **Solution**: Set random seeds for reproducibility
- **Check**: Non-deterministic components in pipeline

### Performance Optimization

1. **Parallel Processing**: Evaluate multiple queries in parallel
2. **Caching**: Cache embeddings and model outputs
3. **Batch Processing**: Process queries in batches for efficiency
4. **Resource Management**: Monitor memory and GPU usage

## References

- [Information Retrieval Evaluation Metrics](https://en.wikipedia.org/wiki/Evaluation_measures_(information_retrieval))
- [MLflow Tracking Documentation](https://mlflow.org/docs/latest/tracking.html)
- [RAG System Architecture](../implementation/RAG_IMPLEMENTATION.md)
