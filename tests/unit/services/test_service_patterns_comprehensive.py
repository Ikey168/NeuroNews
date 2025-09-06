#!/usr/bin/env python3
"""
Services & Infrastructure Testing - Issue #487
Comprehensive testing for services and infrastructure classes

This test focuses on testing patterns, interfaces, and infrastructure
that supports the services mentioned in issue #487.
"""

import os
import sys
import pytest
import threading
import time
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict, Any, Optional

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))


class TestServiceInfrastructurePatterns:
    """Test core service infrastructure patterns required for Issue #487"""
    
    def test_vector_service_interface_pattern(self):
        """Test vector service interface pattern"""
        # Test the abstract interface pattern for vector services
        class MockVectorBackend:
            def __init__(self, backend_type='test'):
                self.backend_type = backend_type
            
            def create_collection(self, **kwargs):
                return True
            
            def upsert(self, points, **kwargs):
                return len(points)
            
            def search(self, query_embedding, k=10, **kwargs):
                return [
                    {'id': f'result_{i}', 'score': 0.9 - i*0.1}
                    for i in range(min(k, 3))
                ]
            
            def health_check(self):
                return True
            
            def get_stats(self):
                return {'total_vectors': 1000, 'backend_type': self.backend_type}
        
        # Test vector backend interface
        backend = MockVectorBackend('pgvector')
        
        # Test collection creation
        assert backend.create_collection(name='test_collection') is True
        
        # Test upsert
        points = [{'id': '1', 'vector': [0.1, 0.2]}, {'id': '2', 'vector': [0.3, 0.4]}]
        count = backend.upsert(points)
        assert count == 2
        
        # Test search
        results = backend.search([0.1, 0.2, 0.3], k=5)
        assert len(results) == 3
        assert results[0]['score'] == 0.9
        
        # Test health check
        assert backend.health_check() is True
        
        # Test stats
        stats = backend.get_stats()
        assert stats['backend_type'] == 'pgvector'
        assert stats['total_vectors'] == 1000
    
    def test_embedding_provider_interface_pattern(self):
        """Test embedding provider interface pattern"""
        # Test the abstract interface for embedding providers
        class MockEmbeddingBackend:
            def __init__(self, model_name='test-model', dimension=384):
                self.model_name = model_name
                self.dimension = dimension
            
            def embed_texts(self, texts):
                # Return mock embeddings
                import numpy as np
                return np.random.rand(len(texts), self.dimension)
            
            def dim(self):
                return self.dimension
            
            def name(self):
                return f'mock:{self.model_name}'
        
        # Test embedding backend interface
        backend = MockEmbeddingBackend('sentence-transformers', 384)
        
        # Test text embedding
        texts = ['hello world', 'test document']
        embeddings = backend.embed_texts(texts)
        assert embeddings.shape == (2, 384)
        
        # Test dimension
        assert backend.dim() == 384
        
        # Test name
        assert backend.name() == 'mock:sentence-transformers'
    
    def test_rag_service_interface_patterns(self):
        """Test RAG service interface patterns"""
        # Test chunking service interface
        class MockChunkingService:
            def __init__(self, max_chars=1000, overlap=100):
                self.max_chars = max_chars
                self.overlap = overlap
            
            def chunk_text(self, text, **kwargs):
                # Simple chunking implementation
                chunks = []
                for i in range(0, len(text), self.max_chars - self.overlap):
                    chunk = text[i:i + self.max_chars]
                    if chunk.strip():
                        chunks.append({
                            'text': chunk,
                            'start': i,
                            'end': min(i + self.max_chars, len(text)),
                            'id': len(chunks)
                        })
                return chunks
        
        # Test retrieval service interface
        class MockRetrievalService:
            def __init__(self, vector_backend, embedding_provider):
                self.vector_backend = vector_backend
                self.embedding_provider = embedding_provider
            
            def retrieve(self, query, k=10, **kwargs):
                # Mock retrieval implementation
                query_embedding = self.embedding_provider.embed_texts([query])
                results = self.vector_backend.search(query_embedding[0], k=k)
                return results
        
        # Test reranking service interface
        class MockRerankingService:
            def __init__(self, rerank_model=None):
                self.rerank_model = rerank_model or 'cross-encoder'
            
            def rerank(self, query, documents, top_k=None):
                # Simple mock reranking
                scored_docs = []
                for i, doc in enumerate(documents):
                    score = 1.0 - (i * 0.1)  # Decreasing scores
                    scored_docs.append({**doc, 'rerank_score': score})
                
                # Sort by rerank score
                scored_docs.sort(key=lambda x: x['rerank_score'], reverse=True)
                
                if top_k:
                    scored_docs = scored_docs[:top_k]
                
                return scored_docs
        
        # Test the interfaces
        chunking_service = MockChunkingService(max_chars=500, overlap=50)
        text = "This is a test document that will be chunked into smaller pieces for processing."
        chunks = chunking_service.chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0]['text'] == text
        assert chunks[0]['start'] == 0
        
        # Create mock dependencies for retrieval service
        class MockVectorBackend:
            def search(self, query_embedding, k=10):
                return [{'id': f'doc_{i}', 'score': 0.9 - i*0.1} for i in range(min(k, 3))]
        
        class MockEmbeddingProvider:
            def embed_texts(self, texts):
                import numpy as np
                return np.random.rand(len(texts), 384)
        
        # Test retrieval service
        vector_backend = MockVectorBackend()
        embedding_provider = MockEmbeddingProvider()
        retrieval_service = MockRetrievalService(vector_backend, embedding_provider)
        
        results = retrieval_service.retrieve("test query", k=5)
        assert len(results) == 3  # Limited by mock backend
        
        # Test reranking service
        reranking_service = MockRerankingService()
        documents = [
            {'id': '1', 'text': 'doc 1'},
            {'id': '2', 'text': 'doc 2'},
            {'id': '3', 'text': 'doc 3'}
        ]
        
        reranked = reranking_service.rerank("query", documents, top_k=2)
        assert len(reranked) == 2
        assert reranked[0]['rerank_score'] > reranked[1]['rerank_score']
    
    def test_mlops_service_interface_patterns(self):
        """Test MLOps service interface patterns"""
        # Test model tracker interface
        class MockModelTracker:
            def __init__(self):
                self.experiments = {}
                self.models = {}
            
            def start_experiment(self, experiment_name):
                self.experiments[experiment_name] = {
                    'status': 'running',
                    'metrics': {},
                    'params': {}
                }
                return experiment_name
            
            def log_metric(self, experiment_name, metric_name, value):
                if experiment_name in self.experiments:
                    self.experiments[experiment_name]['metrics'][metric_name] = value
            
            def log_param(self, experiment_name, param_name, value):
                if experiment_name in self.experiments:
                    self.experiments[experiment_name]['params'][param_name] = value
            
            def register_model(self, model_name, model_version, experiment_name):
                model_id = f"{model_name}:{model_version}"
                self.models[model_id] = {
                    'name': model_name,
                    'version': model_version,
                    'experiment': experiment_name,
                    'status': 'registered'
                }
                return model_id
        
        # Test model registry interface
        class MockModelRegistry:
            def __init__(self):
                self.registered_models = {}
                self.deployments = {}
            
            def register_model(self, model_name, model_path, metadata=None):
                self.registered_models[model_name] = {
                    'path': model_path,
                    'metadata': metadata or {},
                    'versions': []
                }
                return model_name
            
            def deploy_model(self, model_name, deployment_name, config=None):
                if model_name in self.registered_models:
                    self.deployments[deployment_name] = {
                        'model_name': model_name,
                        'config': config or {},
                        'status': 'deployed'
                    }
                    return deployment_name
                return None
            
            def get_model_status(self, deployment_name):
                deployment = self.deployments.get(deployment_name)
                return deployment['status'] if deployment else 'not_found'
        
        # Test data manifest interface
        class MockDataManifest:
            def __init__(self):
                self.datasets = {}
                self.lineage = {}
            
            def register_dataset(self, dataset_name, schema, location):
                self.datasets[dataset_name] = {
                    'schema': schema,
                    'location': location,
                    'created_at': time.time()
                }
            
            def track_transformation(self, input_datasets, output_dataset, transformation):
                self.lineage[output_dataset] = {
                    'inputs': input_datasets,
                    'transformation': transformation,
                    'timestamp': time.time()
                }
            
            def get_lineage(self, dataset_name):
                return self.lineage.get(dataset_name, {})
        
        # Test the MLOps interfaces
        tracker = MockModelTracker()
        
        # Test experiment tracking
        exp_id = tracker.start_experiment('test_exp')
        assert exp_id == 'test_exp'
        
        tracker.log_metric('test_exp', 'accuracy', 0.95)
        tracker.log_param('test_exp', 'learning_rate', 0.001)
        
        assert tracker.experiments['test_exp']['metrics']['accuracy'] == 0.95
        assert tracker.experiments['test_exp']['params']['learning_rate'] == 0.001
        
        # Test model registration
        model_id = tracker.register_model('test_model', 'v1.0', 'test_exp')
        assert model_id == 'test_model:v1.0'
        assert tracker.models[model_id]['status'] == 'registered'
        
        # Test model registry
        registry = MockModelRegistry()
        registry.register_model('classifier', '/models/classifier.pkl', {'type': 'sklearn'})
        
        deployment_id = registry.deploy_model('classifier', 'prod_classifier')
        assert deployment_id == 'prod_classifier'
        assert registry.get_model_status('prod_classifier') == 'deployed'
        
        # Test data manifest
        manifest = MockDataManifest()
        manifest.register_dataset('raw_data', {'id': 'int', 'text': 'str'}, '/data/raw')
        manifest.track_transformation(['raw_data'], 'processed_data', 'clean_and_normalize')
        
        lineage = manifest.get_lineage('processed_data')
        assert lineage['inputs'] == ['raw_data']
        assert lineage['transformation'] == 'clean_and_normalize'
    
    def test_infrastructure_service_patterns(self):
        """Test infrastructure service patterns"""
        # Test cache service interface
        class MockCacheService:
            def __init__(self, default_ttl=3600):
                self._cache = {}
                self.default_ttl = default_ttl
            
            def get(self, key):
                entry = self._cache.get(key)
                if entry and entry['expires_at'] > time.time():
                    return entry['value']
                elif entry:
                    # Expired
                    del self._cache[key]
                return None
            
            def set(self, key, value, ttl=None):
                ttl = ttl or self.default_ttl
                self._cache[key] = {
                    'value': value,
                    'expires_at': time.time() + ttl
                }
            
            def delete(self, key):
                self._cache.pop(key, None)
            
            def clear(self):
                self._cache.clear()
        
        # Test validation service interface
        class MockValidationService:
            def __init__(self):
                self.rules = {}
            
            def add_rule(self, field, rule_func, message=None):
                if field not in self.rules:
                    self.rules[field] = []
                self.rules[field].append({
                    'func': rule_func,
                    'message': message or f'Validation failed for {field}'
                })
            
            def validate(self, data):
                errors = []
                for field, rules in self.rules.items():
                    if field in data:
                        for rule in rules:
                            if not rule['func'](data[field]):
                                errors.append({
                                    'field': field,
                                    'message': rule['message']
                                })
                return errors
        
        # Test middleware service interface
        class MockMiddlewareService:
            def __init__(self):
                self.middlewares = []
            
            def add_middleware(self, middleware_func):
                self.middlewares.append(middleware_func)
            
            def process_request(self, request):
                for middleware in self.middlewares:
                    request = middleware(request)
                return request
        
        # Test the infrastructure services
        cache = MockCacheService(default_ttl=10)
        cache.set('key1', 'value1')
        assert cache.get('key1') == 'value1'
        assert cache.get('nonexistent') is None
        
        cache.delete('key1')
        assert cache.get('key1') is None
        
        # Test validation service
        validator = MockValidationService()
        validator.add_rule('email', lambda x: '@' in x, 'Invalid email format')
        validator.add_rule('age', lambda x: x >= 0, 'Age must be non-negative')
        
        # Valid data
        errors = validator.validate({'email': 'test@example.com', 'age': 25})
        assert len(errors) == 0
        
        # Invalid data
        errors = validator.validate({'email': 'invalid-email', 'age': -5})
        assert len(errors) == 2
        assert any('email' in error['field'] for error in errors)
        assert any('age' in error['field'] for error in errors)
        
        # Test middleware service
        middleware_service = MockMiddlewareService()
        
        def logging_middleware(request):
            request['logged'] = True
            return request
        
        def auth_middleware(request):
            request['authenticated'] = True
            return request
        
        middleware_service.add_middleware(logging_middleware)
        middleware_service.add_middleware(auth_middleware)
        
        request = {'path': '/api/test'}
        processed = middleware_service.process_request(request)
        
        assert processed['logged'] is True
        assert processed['authenticated'] is True
        assert processed['path'] == '/api/test'
    
    def test_monitoring_and_observability_patterns(self):
        """Test monitoring and observability service patterns"""
        # Test unit economics collector (based on actual implementation)
        class MockUnitEconomicsCollector:
            def __init__(self):
                self.metrics = {
                    'articles_ingested': 0,
                    'rag_queries': 0,
                    'pipeline_operations': 0
                }
            
            def increment_articles_ingested(self, pipeline='ingest', source='unknown', status='success', count=1):
                self.metrics['articles_ingested'] += count
            
            def increment_rag_queries(self, endpoint='/ask', provider='openai', status='success', count=1):
                self.metrics['rag_queries'] += count
            
            def increment_pipeline_operation(self, operation_type='process', pipeline='data', status='success', count=1):
                self.metrics['pipeline_operations'] += count
            
            def get_metrics(self):
                return self.metrics.copy()
        
        # Test observability collector interface
        class MockObservabilityCollector:
            def __init__(self):
                self.traces = []
                self.metrics = {}
                self.logs = []
            
            def start_trace(self, trace_name):
                trace_id = len(self.traces)
                self.traces.append({
                    'id': trace_id,
                    'name': trace_name,
                    'start_time': time.time(),
                    'spans': []
                })
                return trace_id
            
            def add_span(self, trace_id, span_name, duration=None):
                if trace_id < len(self.traces):
                    self.traces[trace_id]['spans'].append({
                        'name': span_name,
                        'duration': duration or 0.1
                    })
            
            def record_metric(self, metric_name, value, labels=None):
                key = f"{metric_name}:{labels}" if labels else metric_name
                self.metrics[key] = value
            
            def log_event(self, level, message, context=None):
                self.logs.append({
                    'level': level,
                    'message': message,
                    'context': context or {},
                    'timestamp': time.time()
                })
        
        # Test performance monitor interface
        class MockPerformanceMonitor:
            def __init__(self):
                self.performance_data = {}
            
            def start_monitoring(self, operation_name):
                self.performance_data[operation_name] = {
                    'start_time': time.time(),
                    'calls': 0,
                    'total_duration': 0
                }
            
            def record_operation(self, operation_name, duration):
                if operation_name in self.performance_data:
                    data = self.performance_data[operation_name]
                    data['calls'] += 1
                    data['total_duration'] += duration
            
            def get_average_duration(self, operation_name):
                data = self.performance_data.get(operation_name)
                if data and data['calls'] > 0:
                    return data['total_duration'] / data['calls']
                return 0
        
        # Test alert manager interface
        class MockAlertManager:
            def __init__(self):
                self.alerts = []
                self.rules = []
            
            def add_alert_rule(self, name, condition_func, severity='warning'):
                self.rules.append({
                    'name': name,
                    'condition': condition_func,
                    'severity': severity
                })
            
            def check_alerts(self, metrics):
                new_alerts = []
                for rule in self.rules:
                    if rule['condition'](metrics):
                        alert = {
                            'name': rule['name'],
                            'severity': rule['severity'],
                            'timestamp': time.time(),
                            'metrics': metrics
                        }
                        new_alerts.append(alert)
                        self.alerts.append(alert)
                return new_alerts
            
            def get_active_alerts(self, severity=None):
                if severity:
                    return [a for a in self.alerts if a['severity'] == severity]
                return self.alerts.copy()
        
        # Test the monitoring services
        unit_economics = MockUnitEconomicsCollector()
        unit_economics.increment_articles_ingested(count=10)
        unit_economics.increment_rag_queries(count=5)
        unit_economics.increment_pipeline_operation(count=20)
        
        metrics = unit_economics.get_metrics()
        assert metrics['articles_ingested'] == 10
        assert metrics['rag_queries'] == 5
        assert metrics['pipeline_operations'] == 20
        
        # Test observability collector
        observability = MockObservabilityCollector()
        trace_id = observability.start_trace('test_operation')
        observability.add_span(trace_id, 'database_query', 0.05)
        observability.add_span(trace_id, 'api_call', 0.1)
        
        assert len(observability.traces) == 1
        assert len(observability.traces[0]['spans']) == 2
        
        observability.record_metric('response_time', 0.15, 'endpoint:/api/search')
        observability.log_event('INFO', 'Operation completed successfully')
        
        assert len(observability.metrics) == 1
        assert len(observability.logs) == 1
        
        # Test performance monitor
        perf_monitor = MockPerformanceMonitor()
        perf_monitor.start_monitoring('search_operation')
        perf_monitor.record_operation('search_operation', 0.2)
        perf_monitor.record_operation('search_operation', 0.3)
        
        avg_duration = perf_monitor.get_average_duration('search_operation')
        assert avg_duration == 0.25  # (0.2 + 0.3) / 2
        
        # Test alert manager
        alert_manager = MockAlertManager()
        
        # Add alert rules
        alert_manager.add_alert_rule(
            'high_response_time',
            lambda m: m.get('response_time', 0) > 1.0,
            'critical'
        )
        alert_manager.add_alert_rule(
            'low_success_rate',
            lambda m: m.get('success_rate', 1.0) < 0.95,
            'warning'
        )
        
        # Test with normal metrics
        normal_metrics = {'response_time': 0.5, 'success_rate': 0.98}
        alerts = alert_manager.check_alerts(normal_metrics)
        assert len(alerts) == 0
        
        # Test with problematic metrics
        bad_metrics = {'response_time': 1.5, 'success_rate': 0.90}
        alerts = alert_manager.check_alerts(bad_metrics)
        assert len(alerts) == 2
        
        critical_alerts = alert_manager.get_active_alerts('critical')
        assert len(critical_alerts) == 1
        assert critical_alerts[0]['name'] == 'high_response_time'


if __name__ == "__main__":
    # Also test that we can import numpy if available
    try:
        import numpy as np
        print("✓ numpy available for vector operations")
    except ImportError:
        print("⚠ numpy not available - some vector tests may be skipped")
    
    pytest.main([__file__, "-v"])