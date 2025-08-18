#!/usr/bin/env python3
"""
NLP Jobs Validation Script
Issue #74: Deploy NLP & AI Processing as Kubernetes Jobs

This script validates the deployment and performs comprehensive testing
of the NLP & AI processing infrastructure in Kubernetes.
"""

import os
import sys
import asyncio
import argparse
import logging
import json
import time
import subprocess
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class NLPJobsValidator:
    """Validator for NLP Jobs deployment in Kubernetes."""
    
    def __init__(self, namespace: str = "neuronews", verbose: bool = False):
        """
        Initialize the validator.
        
        Args:
            namespace: Kubernetes namespace to validate
            verbose: Enable verbose output
        """
        self.namespace = namespace
        self.verbose = verbose
        self.validation_results = {
            'timestamp': datetime.now(timezone.utc),
            'namespace': namespace,
            'tests': {},
            'summary': {
                'total_tests': 0,
                'passed_tests': 0,
                'failed_tests': 0,
                'warnings': 0
            }
        }
        
        logger.info(f"Initialized NLP Jobs Validator for namespace: {namespace}")
    
    def run_kubectl_command(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """
        Run a kubectl command and return the result.
        
        Args:
            args: kubectl command arguments
            check: Whether to check return code
            
        Returns:
            CompletedProcess result
        """
        cmd = ['kubectl'] + args
        if self.verbose:
            logger.debug(f"Running command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        if check and result.returncode != 0:
            logger.error(f"Command failed: {' '.join(cmd)}")
            logger.error(f"Error: {result.stderr}")
        
        return result
    
    def test_cluster_connectivity(self) -> bool:
        """Test if we can connect to the Kubernetes cluster."""
        test_name = "cluster_connectivity"
        self.validation_results['tests'][test_name] = {
            'name': 'Cluster Connectivity',
            'status': 'running',
            'start_time': datetime.now(timezone.utc)
        }
        
        try:
            result = self.run_kubectl_command(['cluster-info'])
            if result.returncode == 0:
                self.validation_results['tests'][test_name]['status'] = 'passed'
                self.validation_results['tests'][test_name]['message'] = 'Successfully connected to cluster'
                logger.info("✓ Cluster connectivity test passed")
                return True
            else:
                self.validation_results['tests'][test_name]['status'] = 'failed'
                self.validation_results['tests'][test_name]['message'] = f"Failed to connect: {result.stderr}"
                logger.error("✗ Cluster connectivity test failed")
                return False
                
        except Exception as e:
            self.validation_results['tests'][test_name]['status'] = 'failed'
            self.validation_results['tests'][test_name]['message'] = f"Exception: {str(e)}"
            logger.error(f"✗ Cluster connectivity test failed: {e}")
            return False
        finally:
            self.validation_results['tests'][test_name]['end_time'] = datetime.now(timezone.utc)
    
    def test_namespace_exists(self) -> bool:
        """Test if the target namespace exists."""
        test_name = "namespace_exists"
        self.validation_results['tests'][test_name] = {
            'name': 'Namespace Exists',
            'status': 'running',
            'start_time': datetime.now(timezone.utc)
        }
        
        try:
            result = self.run_kubectl_command(['get', 'namespace', self.namespace])
            if result.returncode == 0:
                self.validation_results['tests'][test_name]['status'] = 'passed'
                self.validation_results['tests'][test_name]['message'] = f'Namespace {self.namespace} exists'
                logger.info(f"✓ Namespace {self.namespace} exists")
                return True
            else:
                self.validation_results['tests'][test_name]['status'] = 'failed'
                self.validation_results['tests'][test_name]['message'] = f'Namespace {self.namespace} not found'
                logger.error(f"✗ Namespace {self.namespace} not found")
                return False
                
        except Exception as e:
            self.validation_results['tests'][test_name]['status'] = 'failed'
            self.validation_results['tests'][test_name]['message'] = f"Exception: {str(e)}"
            logger.error(f"✗ Namespace test failed: {e}")
            return False
        finally:
            self.validation_results['tests'][test_name]['end_time'] = datetime.now(timezone.utc)
    
    def test_priority_classes(self) -> bool:
        """Test if priority classes are created."""
        test_name = "priority_classes"
        self.validation_results['tests'][test_name] = {
            'name': 'Priority Classes',
            'status': 'running',
            'start_time': datetime.now(timezone.utc)
        }
        
        expected_classes = [
            'nlp-critical', 'nlp-high', 'nlp-medium', 'nlp-low', 'nlp-maintenance'
        ]
        
        try:
            missing_classes = []
            for pc in expected_classes:
                result = self.run_kubectl_command(['get', 'priorityclass', pc], check=False)
                if result.returncode != 0:
                    missing_classes.append(pc)
            
            if not missing_classes:
                self.validation_results['tests'][test_name]['status'] = 'passed'
                self.validation_results['tests'][test_name]['message'] = 'All priority classes exist'
                logger.info("✓ All priority classes exist")
                return True
            else:
                self.validation_results['tests'][test_name]['status'] = 'failed'
                self.validation_results['tests'][test_name]['message'] = f'Missing priority classes: {missing_classes}'
                logger.error(f"✗ Missing priority classes: {missing_classes}")
                return False
                
        except Exception as e:
            self.validation_results['tests'][test_name]['status'] = 'failed'
            self.validation_results['tests'][test_name]['message'] = f"Exception: {str(e)}"
            logger.error(f"✗ Priority classes test failed: {e}")
            return False
        finally:
            self.validation_results['tests'][test_name]['end_time'] = datetime.now(timezone.utc)
    
    def test_rbac_resources(self) -> bool:
        """Test if RBAC resources are created."""
        test_name = "rbac_resources"
        self.validation_results['tests'][test_name] = {
            'name': 'RBAC Resources',
            'status': 'running',
            'start_time': datetime.now(timezone.utc)
        }
        
        try:
            missing_resources = []
            
            # Check ServiceAccount
            result = self.run_kubectl_command(['get', 'sa', 'nlp-processor', '-n', self.namespace], check=False)
            if result.returncode != 0:
                missing_resources.append('ServiceAccount nlp-processor')
            
            # Check Role
            result = self.run_kubectl_command(['get', 'role', 'nlp-processor', '-n', self.namespace], check=False)
            if result.returncode != 0:
                missing_resources.append('Role nlp-processor')
            
            # Check RoleBinding
            result = self.run_kubectl_command(['get', 'rolebinding', 'nlp-processor', '-n', self.namespace], check=False)
            if result.returncode != 0:
                missing_resources.append('RoleBinding nlp-processor')
            
            # Check ClusterRole
            result = self.run_kubectl_command(['get', 'clusterrole', 'nlp-gpu-access'], check=False)
            if result.returncode != 0:
                missing_resources.append('ClusterRole nlp-gpu-access')
            
            if not missing_resources:
                self.validation_results['tests'][test_name]['status'] = 'passed'
                self.validation_results['tests'][test_name]['message'] = 'All RBAC resources exist'
                logger.info("✓ All RBAC resources exist")
                return True
            else:
                self.validation_results['tests'][test_name]['status'] = 'failed'
                self.validation_results['tests'][test_name]['message'] = f'Missing RBAC resources: {missing_resources}'
                logger.error(f"✗ Missing RBAC resources: {missing_resources}")
                return False
                
        except Exception as e:
            self.validation_results['tests'][test_name]['status'] = 'failed'
            self.validation_results['tests'][test_name]['message'] = f"Exception: {str(e)}"
            logger.error(f"✗ RBAC resources test failed: {e}")
            return False
        finally:
            self.validation_results['tests'][test_name]['end_time'] = datetime.now(timezone.utc)
    
    def test_storage_resources(self) -> bool:
        """Test if storage resources are created and bound."""
        test_name = "storage_resources"
        self.validation_results['tests'][test_name] = {
            'name': 'Storage Resources',
            'status': 'running',
            'start_time': datetime.now(timezone.utc)
        }
        
        expected_pvcs = ['nlp-models', 'nlp-results', 'nlp-cache']
        
        try:
            pvc_status = {}
            for pvc in expected_pvcs:
                result = self.run_kubectl_command(['get', 'pvc', pvc, '-n', self.namespace, '-o', 'jsonpath={.status.phase}'], check=False)
                if result.returncode == 0:
                    pvc_status[pvc] = result.stdout.strip()
                else:
                    pvc_status[pvc] = 'Missing'
            
            # Check if all PVCs are bound
            unbound_pvcs = [pvc for pvc, status in pvc_status.items() if status != 'Bound']
            
            if not unbound_pvcs:
                self.validation_results['tests'][test_name]['status'] = 'passed'
                self.validation_results['tests'][test_name]['message'] = 'All PVCs are bound'
                self.validation_results['tests'][test_name]['details'] = pvc_status
                logger.info("✓ All PVCs are bound")
                return True
            else:
                if any(status == 'Missing' for status in pvc_status.values()):
                    self.validation_results['tests'][test_name]['status'] = 'failed'
                    logger.error(f"✗ Missing PVCs: {unbound_pvcs}")
                else:
                    self.validation_results['tests'][test_name]['status'] = 'warning'
                    logger.warning(f"⚠ Unbound PVCs: {unbound_pvcs}")
                
                self.validation_results['tests'][test_name]['message'] = f'Unbound PVCs: {unbound_pvcs}'
                self.validation_results['tests'][test_name]['details'] = pvc_status
                return False
                
        except Exception as e:
            self.validation_results['tests'][test_name]['status'] = 'failed'
            self.validation_results['tests'][test_name]['message'] = f"Exception: {str(e)}"
            logger.error(f"✗ Storage resources test failed: {e}")
            return False
        finally:
            self.validation_results['tests'][test_name]['end_time'] = datetime.now(timezone.utc)
    
    def test_configmap(self) -> bool:
        """Test if ConfigMap is created with expected keys."""
        test_name = "configmap"
        self.validation_results['tests'][test_name] = {
            'name': 'ConfigMap',
            'status': 'running',
            'start_time': datetime.now(timezone.utc)
        }
        
        try:
            result = self.run_kubectl_command(['get', 'cm', 'nlp-config', '-n', self.namespace, '-o', 'json'], check=False)
            if result.returncode != 0:
                self.validation_results['tests'][test_name]['status'] = 'failed'
                self.validation_results['tests'][test_name]['message'] = 'ConfigMap nlp-config not found'
                logger.error("✗ ConfigMap nlp-config not found")
                return False
            
            configmap_data = json.loads(result.stdout)
            expected_keys = [
                'BATCH_SIZE', 'MAX_WORKERS', 'USE_GPU', 'SENTIMENT_MODEL',
                'NER_MODEL', 'TOPIC_EMBEDDING_MODEL', 'NUM_TOPICS'
            ]
            
            data_keys = configmap_data.get('data', {}).keys()
            missing_keys = [key for key in expected_keys if key not in data_keys]
            
            if not missing_keys:
                self.validation_results['tests'][test_name]['status'] = 'passed'
                self.validation_results['tests'][test_name]['message'] = 'ConfigMap has all expected keys'
                self.validation_results['tests'][test_name]['details'] = {'keys': list(data_keys)}
                logger.info("✓ ConfigMap has all expected keys")
                return True
            else:
                self.validation_results['tests'][test_name]['status'] = 'warning'
                self.validation_results['tests'][test_name]['message'] = f'Missing ConfigMap keys: {missing_keys}'
                self.validation_results['tests'][test_name]['details'] = {'missing_keys': missing_keys}
                logger.warning(f"⚠ Missing ConfigMap keys: {missing_keys}")
                return False
                
        except Exception as e:
            self.validation_results['tests'][test_name]['status'] = 'failed'
            self.validation_results['tests'][test_name]['message'] = f"Exception: {str(e)}"
            logger.error(f"✗ ConfigMap test failed: {e}")
            return False
        finally:
            self.validation_results['tests'][test_name]['end_time'] = datetime.now(timezone.utc)
    
    def test_gpu_availability(self) -> bool:
        """Test GPU availability in the cluster."""
        test_name = "gpu_availability"
        self.validation_results['tests'][test_name] = {
            'name': 'GPU Availability',
            'status': 'running',
            'start_time': datetime.now(timezone.utc)
        }
        
        try:
            # Check for GPU nodes
            result = self.run_kubectl_command(['get', 'nodes', '-l', 'nvidia.com/gpu.present=true', '--no-headers'], check=False)
            if result.returncode != 0 or not result.stdout.strip():
                # Try alternative label
                result = self.run_kubectl_command(['get', 'nodes', '-l', 'accelerator=nvidia-tesla-k80', '--no-headers'], check=False)
            
            gpu_nodes = result.stdout.strip().split('\n') if result.stdout.strip() else []
            gpu_count = len([node for node in gpu_nodes if node.strip()])
            
            if gpu_count > 0:
                self.validation_results['tests'][test_name]['status'] = 'passed'
                self.validation_results['tests'][test_name]['message'] = f'Found {gpu_count} GPU nodes'
                self.validation_results['tests'][test_name]['details'] = {'gpu_nodes': gpu_nodes}
                logger.info(f"✓ Found {gpu_count} GPU nodes")
                return True
            else:
                self.validation_results['tests'][test_name]['status'] = 'warning'
                self.validation_results['tests'][test_name]['message'] = 'No GPU nodes found'
                logger.warning("⚠ No GPU nodes found - GPU features will not work")
                return False
                
        except Exception as e:
            self.validation_results['tests'][test_name]['status'] = 'failed'
            self.validation_results['tests'][test_name]['message'] = f"Exception: {str(e)}"
            logger.error(f"✗ GPU availability test failed: {e}")
            return False
        finally:
            self.validation_results['tests'][test_name]['end_time'] = datetime.now(timezone.utc)
    
    def test_nvidia_device_plugin(self) -> bool:
        """Test if NVIDIA device plugin is available."""
        test_name = "nvidia_device_plugin"
        self.validation_results['tests'][test_name] = {
            'name': 'NVIDIA Device Plugin',
            'status': 'running',
            'start_time': datetime.now(timezone.utc)
        }
        
        try:
            # Check for NVIDIA device plugin DaemonSet
            result = self.run_kubectl_command(['get', 'ds', 'nvidia-device-plugin-daemonset', '-n', 'gpu-operator'], check=False)
            if result.returncode != 0:
                # Try kube-system namespace
                result = self.run_kubectl_command(['get', 'ds', 'nvidia-device-plugin-daemonset', '-n', 'kube-system'], check=False)
            
            if result.returncode == 0:
                self.validation_results['tests'][test_name]['status'] = 'passed'
                self.validation_results['tests'][test_name]['message'] = 'NVIDIA device plugin is running'
                logger.info("✓ NVIDIA device plugin is running")
                return True
            else:
                self.validation_results['tests'][test_name]['status'] = 'warning'
                self.validation_results['tests'][test_name]['message'] = 'NVIDIA device plugin not found'
                logger.warning("⚠ NVIDIA device plugin not found - GPU scheduling may not work")
                return False
                
        except Exception as e:
            self.validation_results['tests'][test_name]['status'] = 'failed'
            self.validation_results['tests'][test_name]['message'] = f"Exception: {str(e)}"
            logger.error(f"✗ NVIDIA device plugin test failed: {e}")
            return False
        finally:
            self.validation_results['tests'][test_name]['end_time'] = datetime.now(timezone.utc)
    
    def test_monitoring_resources(self) -> bool:
        """Test if monitoring resources are created."""
        test_name = "monitoring_resources"
        self.validation_results['tests'][test_name] = {
            'name': 'Monitoring Resources',
            'status': 'running',
            'start_time': datetime.now(timezone.utc)
        }
        
        try:
            # Check for ServiceMonitor
            result = self.run_kubectl_command(['get', 'servicemonitor', 'nlp-jobs-monitor', '-n', self.namespace], check=False)
            servicemonitor_exists = result.returncode == 0
            
            # Check for PrometheusRule
            result = self.run_kubectl_command(['get', 'prometheusrule', 'nlp-jobs-alerts', '-n', self.namespace], check=False)
            prometheusrule_exists = result.returncode == 0
            
            # Check for ConfigMap (Grafana dashboard)
            result = self.run_kubectl_command(['get', 'cm', 'nlp-grafana-dashboard', '-n', self.namespace], check=False)
            dashboard_exists = result.returncode == 0
            
            monitoring_components = {
                'ServiceMonitor': servicemonitor_exists,
                'PrometheusRule': prometheusrule_exists,
                'Grafana Dashboard': dashboard_exists
            }
            
            existing_components = [name for name, exists in monitoring_components.items() if exists]
            missing_components = [name for name, exists in monitoring_components.items() if not exists]
            
            if len(existing_components) == len(monitoring_components):
                self.validation_results['tests'][test_name]['status'] = 'passed'
                self.validation_results['tests'][test_name]['message'] = 'All monitoring resources exist'
                logger.info("✓ All monitoring resources exist")
                return True
            elif existing_components:
                self.validation_results['tests'][test_name]['status'] = 'warning'
                self.validation_results['tests'][test_name]['message'] = f'Some monitoring resources missing: {missing_components}'
                self.validation_results['tests'][test_name]['details'] = monitoring_components
                logger.warning(f"⚠ Some monitoring resources missing: {missing_components}")
                return False
            else:
                self.validation_results['tests'][test_name]['status'] = 'failed'
                self.validation_results['tests'][test_name]['message'] = 'No monitoring resources found'
                logger.error("✗ No monitoring resources found")
                return False
                
        except Exception as e:
            self.validation_results['tests'][test_name]['status'] = 'failed'
            self.validation_results['tests'][test_name]['message'] = f"Exception: {str(e)}"
            logger.error(f"✗ Monitoring resources test failed: {e}")
            return False
        finally:
            self.validation_results['tests'][test_name]['end_time'] = datetime.now(timezone.utc)
    
    def test_job_creation(self) -> bool:
        """Test if NLP jobs can be created and are properly configured."""
        test_name = "job_creation"
        self.validation_results['tests'][test_name] = {
            'name': 'Job Creation',
            'status': 'running',
            'start_time': datetime.now(timezone.utc)
        }
        
        expected_jobs = ['sentiment-analysis-job', 'entity-extraction-job', 'topic-modeling-job']
        
        try:
            job_status = {}
            for job in expected_jobs:
                result = self.run_kubectl_command(['get', 'job', job, '-n', self.namespace, '-o', 'json'], check=False)
                if result.returncode == 0:
                    job_data = json.loads(result.stdout)
                    status = job_data.get('status', {})
                    job_status[job] = {
                        'exists': True,
                        'conditions': status.get('conditions', []),
                        'active': status.get('active', 0),
                        'succeeded': status.get('succeeded', 0),
                        'failed': status.get('failed', 0)
                    }
                else:
                    job_status[job] = {'exists': False}
            
            existing_jobs = [job for job, status in job_status.items() if status['exists']]
            missing_jobs = [job for job, status in job_status.items() if not status['exists']]
            
            if len(existing_jobs) == len(expected_jobs):
                self.validation_results['tests'][test_name]['status'] = 'passed'
                self.validation_results['tests'][test_name]['message'] = 'All expected jobs exist'
                self.validation_results['tests'][test_name]['details'] = job_status
                logger.info("✓ All expected jobs exist")
                return True
            elif existing_jobs:
                self.validation_results['tests'][test_name]['status'] = 'warning'
                self.validation_results['tests'][test_name]['message'] = f'Some jobs missing: {missing_jobs}'
                self.validation_results['tests'][test_name]['details'] = job_status
                logger.warning(f"⚠ Some jobs missing: {missing_jobs}")
                return False
            else:
                self.validation_results['tests'][test_name]['status'] = 'failed'
                self.validation_results['tests'][test_name]['message'] = 'No jobs found'
                logger.error("✗ No jobs found")
                return False
                
        except Exception as e:
            self.validation_results['tests'][test_name]['status'] = 'failed'
            self.validation_results['tests'][test_name]['message'] = f"Exception: {str(e)}"
            logger.error(f"✗ Job creation test failed: {e}")
            return False
        finally:
            self.validation_results['tests'][test_name]['end_time'] = datetime.now(timezone.utc)
    
    def compile_summary(self):
        """Compile validation summary."""
        for test_name, test_data in self.validation_results['tests'].items():
            self.validation_results['summary']['total_tests'] += 1
            
            if test_data['status'] == 'passed':
                self.validation_results['summary']['passed_tests'] += 1
            elif test_data['status'] == 'failed':
                self.validation_results['summary']['failed_tests'] += 1
            elif test_data['status'] == 'warning':
                self.validation_results['summary']['warnings'] += 1
    
    def save_results(self, output_file: str = None):
        """Save validation results to file."""
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"nlp_jobs_validation_{timestamp}.json"
        
        with open(output_file, 'w') as f:
            json.dump(self.validation_results, f, indent=2, default=str)
        
        logger.info(f"Validation results saved to: {output_file}")
        return output_file
    
    def print_summary(self):
        """Print validation summary."""
        summary = self.validation_results['summary']
        
        print("\n" + "="*60)
        print("NLP JOBS VALIDATION SUMMARY")
        print("="*60)
        print(f"Namespace: {self.namespace}")
        print(f"Timestamp: {self.validation_results['timestamp']}")
        print(f"Total Tests: {summary['total_tests']}")
        print(f"Passed: {summary['passed_tests']} ✓")
        print(f"Failed: {summary['failed_tests']} ✗")
        print(f"Warnings: {summary['warnings']} ⚠")
        
        success_rate = (summary['passed_tests'] / summary['total_tests'] * 100) if summary['total_tests'] > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")
        
        print("\n" + "="*60)
        print("DETAILED RESULTS")
        print("="*60)
        
        for test_name, test_data in self.validation_results['tests'].items():
            status_symbol = {
                'passed': '✓',
                'failed': '✗',
                'warning': '⚠'
            }.get(test_data['status'], '?')
            
            print(f"{status_symbol} {test_data['name']}: {test_data['message']}")
            
            if self.verbose and 'details' in test_data:
                print(f"   Details: {test_data['details']}")
        
        print("="*60)
    
    async def run_all_tests(self) -> bool:
        """Run all validation tests."""
        logger.info("Starting NLP Jobs validation")
        
        tests = [
            self.test_cluster_connectivity,
            self.test_namespace_exists,
            self.test_priority_classes,
            self.test_rbac_resources,
            self.test_storage_resources,
            self.test_configmap,
            self.test_gpu_availability,
            self.test_nvidia_device_plugin,
            self.test_monitoring_resources,
            self.test_job_creation
        ]
        
        for test in tests:
            try:
                test()
            except Exception as e:
                logger.error(f"Test {test.__name__} failed with exception: {e}")
        
        self.compile_summary()
        return self.validation_results['summary']['failed_tests'] == 0

async def main():
    """Main entry point for the validation script."""
    parser = argparse.ArgumentParser(description='Validate NLP Jobs deployment in Kubernetes')
    parser.add_argument('--namespace', default='neuronews', help='Kubernetes namespace')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--output', help='Output file for results')
    parser.add_argument('--quiet', action='store_true', help='Suppress detailed output')
    
    args = parser.parse_args()
    
    # Set logging level based on arguments
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    elif args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create validator and run tests
    validator = NLPJobsValidator(namespace=args.namespace, verbose=args.verbose)
    
    success = await validator.run_all_tests()
    
    # Save results
    output_file = validator.save_results(args.output)
    
    # Print summary unless quiet
    if not args.quiet:
        validator.print_summary()
    
    # Exit with appropriate code
    if success:
        logger.info("All critical tests passed")
        sys.exit(0)
    else:
        logger.error("Some tests failed")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
