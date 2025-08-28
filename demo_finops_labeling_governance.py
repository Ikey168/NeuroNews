#!/usr/bin/env python3

"""
NeuroNews FinOps Labeling Governance Demo

This script demonstrates the FinOps cost allocation labeling system including:
- Label schema enforcement via Kyverno policies
- Cost attribution by team, pipeline, and business unit
- Compliance reporting and governance workflows
- Integration with OpenCost for financial visibility
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any
import yaml

def run_command(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    """Execute shell command and return result."""
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True, check=check
    )

def log(message: str, level: str = "INFO") -> None:
    """Log message with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    colors = {
        "INFO": "\033[0;34m",    # Blue
        "SUCCESS": "\033[0;32m", # Green
        "WARNING": "\033[1;33m", # Yellow
        "ERROR": "\033[0;31m",   # Red
        "RESET": "\033[0m"       # Reset
    }
    color = colors.get(level, colors["INFO"])
    reset = colors["RESET"]
    print(f"{color}[{timestamp}] {level}: {message}{reset}")

class FinOpsLabelingDemo:
    """Demo class for FinOps labeling governance system."""
    
    def __init__(self):
        self.demo_namespace = "finops-demo"
        self.required_labels = [
            "app", "component", "pipeline", "team", "env", "cost_center"
        ]
        self.pipeline_values = [
            "ingest", "transform", "dbt", "api", "rag", "monitoring", "infra"
        ]
        self.env_values = ["dev", "staging", "prod", "test"]
        
    def check_prerequisites(self) -> bool:
        """Check if required tools and policies are available."""
        log("Checking prerequisites...")
        
        # Check kubectl
        try:
            run_command("kubectl version --client")
            log("✓ kubectl is available")
        except subprocess.CalledProcessError:
            log("✗ kubectl is not available", "ERROR")
            return False
        
        # Check cluster connectivity
        try:
            run_command("kubectl cluster-info")
            log("✓ Cluster connection is working")
        except subprocess.CalledProcessError:
            log("✗ Cannot connect to cluster", "ERROR")
            return False
        
        # Check Kyverno policies
        policies = [
            "require-finops-labels",
            "validate-finops-label-values", 
            "generate-missing-finops-labels"
        ]
        
        all_policies_exist = True
        for policy in policies:
            try:
                run_command(f"kubectl get clusterpolicy {policy}")
                log(f"✓ Policy {policy} is installed")
            except subprocess.CalledProcessError:
                log(f"✗ Policy {policy} is missing", "WARNING")
                all_policies_exist = False
        
        if not all_policies_exist:
            log("Some policies are missing. Run 'k8s/finops/install.sh' first", "WARNING")
        
        return True
    
    def setup_demo_environment(self) -> None:
        """Create demo namespace and resources."""
        log("Setting up demo environment...")
        
        # Create demo namespace
        try:
            run_command(f"kubectl create namespace {self.demo_namespace}")
            log(f"✓ Created namespace {self.demo_namespace}")
        except subprocess.CalledProcessError:
            log(f"Namespace {self.demo_namespace} already exists", "WARNING")
        
        time.sleep(2)
    
    def demonstrate_valid_workload(self) -> None:
        """Deploy workload with proper FinOps labels."""
        log("Demonstrating valid workload deployment...")
        
        deployment_yaml = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "demo-valid-api",
                "namespace": self.demo_namespace,
                "labels": {
                    "app": "demo-api",
                    "component": "backend",
                    "pipeline": "api",
                    "team": "neuronews",
                    "env": "demo",
                    "cost_center": "product",
                    "version": "v1.0.0"
                }
            },
            "spec": {
                "replicas": 1,
                "selector": {
                    "matchLabels": {"app": "demo-api"}
                },
                "template": {
                    "metadata": {
                        "labels": {
                            "app": "demo-api",
                            "component": "backend",
                            "pipeline": "api",
                            "team": "neuronews",
                            "env": "demo",
                            "cost_center": "product"
                        }
                    },
                    "spec": {
                        "containers": [{
                            "name": "api",
                            "image": "nginx:alpine",
                            "resources": {
                                "requests": {
                                    "cpu": "100m",
                                    "memory": "128Mi"
                                }
                            }
                        }]
                    }
                }
            }
        }
        
        # Write deployment to temp file
        with open("/tmp/demo-valid-deployment.yaml", "w") as f:
            yaml.dump(deployment_yaml, f)
        
        try:
            run_command("kubectl apply -f /tmp/demo-valid-deployment.yaml")
            log("✓ Valid deployment created successfully")
            
            # Wait for deployment to be ready
            run_command(
                f"kubectl wait --for=condition=Available "
                f"deployment/demo-valid-api -n {self.demo_namespace} --timeout=60s"
            )
            log("✓ Deployment is ready")
            
        except subprocess.CalledProcessError as e:
            log(f"✗ Failed to create valid deployment: {e}", "ERROR")
    
    def demonstrate_invalid_workload(self) -> None:
        """Attempt to deploy workload without required labels."""
        log("Demonstrating invalid workload deployment (missing labels)...")
        
        invalid_deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "demo-invalid-api",
                "namespace": self.demo_namespace,
                "labels": {
                    "app": "demo-invalid",
                    # Missing: component, pipeline, team, env, cost_center
                }
            },
            "spec": {
                "replicas": 1,
                "selector": {
                    "matchLabels": {"app": "demo-invalid"}
                },
                "template": {
                    "metadata": {
                        "labels": {"app": "demo-invalid"}
                    },
                    "spec": {
                        "containers": [{
                            "name": "api",
                            "image": "nginx:alpine"
                        }]
                    }
                }
            }
        }
        
        with open("/tmp/demo-invalid-deployment.yaml", "w") as f:
            yaml.dump(invalid_deployment, f)
        
        try:
            result = run_command(
                "kubectl apply -f /tmp/demo-invalid-deployment.yaml", 
                check=False
            )
            
            if result.returncode != 0:
                log("✓ Invalid deployment correctly blocked by policy")
                log(f"Policy message: {result.stderr.strip()}")
            else:
                log("⚠ Invalid deployment was allowed (policies in audit mode)", "WARNING")
                
        except Exception as e:
            log(f"Error testing invalid deployment: {e}", "ERROR")
    
    def demonstrate_invalid_values(self) -> None:
        """Attempt to deploy workload with invalid label values."""
        log("Demonstrating invalid label values...")
        
        invalid_values_deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "demo-invalid-values",
                "namespace": self.demo_namespace,
                "labels": {
                    "app": "demo-app",
                    "component": "backend",
                    "pipeline": "invalid-pipeline",  # Invalid value
                    "team": "demo-team",
                    "env": "invalid-env",  # Invalid value
                    "cost_center": "demo-center"
                }
            },
            "spec": {
                "replicas": 1,
                "selector": {
                    "matchLabels": {"app": "demo-app"}
                },
                "template": {
                    "metadata": {
                        "labels": {
                            "app": "demo-app",
                            "pipeline": "invalid-pipeline",
                            "env": "invalid-env"
                        }
                    },
                    "spec": {
                        "containers": [{
                            "name": "app",
                            "image": "nginx:alpine"
                        }]
                    }
                }
            }
        }
        
        with open("/tmp/demo-invalid-values.yaml", "w") as f:
            yaml.dump(invalid_values_deployment, f)
        
        try:
            result = run_command(
                "kubectl apply -f /tmp/demo-invalid-values.yaml",
                check=False
            )
            
            if result.returncode != 0:
                log("✓ Invalid label values correctly blocked by policy")
                log(f"Policy message: {result.stderr.strip()}")
            else:
                log("⚠ Invalid values were allowed (policies in audit mode)", "WARNING")
                
        except Exception as e:
            log(f"Error testing invalid values: {e}", "ERROR")
    
    def demonstrate_cost_allocation(self) -> None:
        """Show cost allocation by different dimensions."""
        log("Demonstrating cost allocation views...")
        
        # Deploy multiple workloads with different labels
        workloads = [
            {
                "name": "data-ingest",
                "labels": {
                    "app": "kafka-connect",
                    "component": "stream-processor", 
                    "pipeline": "ingest",
                    "team": "data-engineering",
                    "env": "demo",
                    "cost_center": "data-platform"
                }
            },
            {
                "name": "ml-inference",
                "labels": {
                    "app": "rag-service",
                    "component": "ml-inference",
                    "pipeline": "rag", 
                    "team": "ml-engineering",
                    "env": "demo",
                    "cost_center": "product"
                }
            },
            {
                "name": "monitoring",
                "labels": {
                    "app": "prometheus",
                    "component": "metrics-collector",
                    "pipeline": "monitoring",
                    "team": "platform",
                    "env": "demo", 
                    "cost_center": "infrastructure"
                }
            }
        ]
        
        for workload in workloads:
            deployment = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {
                    "name": f"demo-{workload['name']}",
                    "namespace": self.demo_namespace,
                    "labels": workload["labels"]
                },
                "spec": {
                    "replicas": 1,
                    "selector": {
                        "matchLabels": {"app": workload["labels"]["app"]}
                    },
                    "template": {
                        "metadata": {
                            "labels": workload["labels"]
                        },
                        "spec": {
                            "containers": [{
                                "name": "app",
                                "image": "nginx:alpine",
                                "resources": {
                                    "requests": {
                                        "cpu": "100m",
                                        "memory": "128Mi"
                                    }
                                }
                            }]
                        }
                    }
                }
            }
            
            with open(f"/tmp/demo-{workload['name']}.yaml", "w") as f:
                yaml.dump(deployment, f)
            
            try:
                run_command(f"kubectl apply -f /tmp/demo-{workload['name']}.yaml")
                log(f"✓ Deployed {workload['name']} workload")
            except subprocess.CalledProcessError:
                log(f"✗ Failed to deploy {workload['name']}", "ERROR")
        
        # Wait for deployments to be ready
        time.sleep(5)
        
        # Show cost allocation views
        self.show_cost_allocation_by_team()
        self.show_cost_allocation_by_pipeline()
        self.show_cost_allocation_by_cost_center()
    
    def show_cost_allocation_by_team(self) -> None:
        """Show resource allocation by team."""
        log("Cost allocation by team:")
        
        try:
            result = run_command(
                f'kubectl get pods -n {self.demo_namespace} '
                '-o jsonpath=\'{range .items[*]}{.metadata.labels.team}{"\t"}'
                '{.metadata.name}{"\t"}{.spec.containers[0].resources.requests.cpu}{"\t"}'
                '{.spec.containers[0].resources.requests.memory}{"\n"}{end}\''
            )
            
            print("\nTeam\t\tPod\t\t\tCPU\tMemory")
            print("="*60)
            print(result.stdout)
            
        except subprocess.CalledProcessError:
            log("Could not retrieve team allocation", "WARNING")
    
    def show_cost_allocation_by_pipeline(self) -> None:
        """Show resource allocation by pipeline."""
        log("Cost allocation by pipeline:")
        
        try:
            result = run_command(
                f'kubectl get pods -n {self.demo_namespace} '
                '-o jsonpath=\'{range .items[*]}{.metadata.labels.pipeline}{"\t"}'
                '{.metadata.name}{"\t"}{.spec.containers[0].resources.requests.cpu}{"\t"}'
                '{.spec.containers[0].resources.requests.memory}{"\n"}{end}\''
            )
            
            print("\nPipeline\tPod\t\t\tCPU\tMemory")
            print("="*60)
            print(result.stdout)
            
        except subprocess.CalledProcessError:
            log("Could not retrieve pipeline allocation", "WARNING")
    
    def show_cost_allocation_by_cost_center(self) -> None:
        """Show resource allocation by cost center."""
        log("Cost allocation by cost center:")
        
        try:
            result = run_command(
                f'kubectl get pods -n {self.demo_namespace} '
                '-o jsonpath=\'{range .items[*]}{.metadata.labels.cost_center}{"\t"}'
                '{.metadata.name}{"\t"}{.spec.containers[0].resources.requests.cpu}{"\t"}'
                '{.spec.containers[0].resources.requests.memory}{"\n"}{end}\''
            )
            
            print("\nCost Center\t\tPod\t\t\tCPU\tMemory")
            print("="*60)
            print(result.stdout)
            
        except subprocess.CalledProcessError:
            log("Could not retrieve cost center allocation", "WARNING")
    
    def demonstrate_compliance_reporting(self) -> None:
        """Generate and display compliance report."""
        log("Generating compliance report...")
        
        # Check policy compliance
        try:
            result = run_command("kubectl get clusterpolicy")
            log("Kyverno Policy Status:")
            print(result.stdout)
            
        except subprocess.CalledProcessError:
            log("Could not retrieve policy status", "WARNING")
        
        # Check for policy violations
        try:
            result = run_command(
                f"kubectl get events -n {self.demo_namespace} "
                "--field-selector reason=PolicyViolation"
            )
            
            if result.stdout.strip():
                log("Policy violations found:")
                print(result.stdout)
            else:
                log("✓ No policy violations found")
                
        except subprocess.CalledProcessError:
            log("Could not check policy violations", "WARNING")
        
        # Show workload compliance
        self.show_workload_compliance()
    
    def show_workload_compliance(self) -> None:
        """Show compliance status of workloads."""
        log("Workload compliance status:")
        
        try:
            # Get all deployments and check their labels
            result = run_command(
                f'kubectl get deployments -n {self.demo_namespace} '
                '-o jsonpath=\'{range .items[*]}{.metadata.name}{"\t"}'
                '{.metadata.labels.app}{"\t"}{.metadata.labels.component}{"\t"}'
                '{.metadata.labels.pipeline}{"\t"}{.metadata.labels.team}{"\t"}'
                '{.metadata.labels.env}{"\t"}{.metadata.labels.cost_center}{"\n"}{end}\''
            )
            
            print("\nDeployment\t\tApp\t\tComponent\tPipeline\tTeam\t\tEnv\tCost Center")
            print("="*100)
            
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if line:
                    parts = line.split('\t')
                    # Check if all required labels are present
                    missing_labels = []
                    for i, label in enumerate(self.required_labels):
                        if i + 1 >= len(parts) or not parts[i + 1]:
                            missing_labels.append(label)
                    
                    status = "✓ COMPLIANT" if not missing_labels else f"✗ MISSING: {', '.join(missing_labels)}"
                    print(f"{line}\t{status}")
                    
        except subprocess.CalledProcessError:
            log("Could not retrieve workload compliance", "WARNING")
    
    def demonstrate_opencost_integration(self) -> None:
        """Show integration with OpenCost for financial visibility."""
        log("Demonstrating OpenCost integration...")
        
        # Check if OpenCost is available
        try:
            run_command("kubectl get deployment opencost -n opencost")
            log("✓ OpenCost is installed")
            
            # Show example API calls for cost allocation
            self.show_opencost_examples()
            
        except subprocess.CalledProcessError:
            log("OpenCost is not installed. Install using k8s/opencost/install.sh", "WARNING")
            log("Example OpenCost API calls for cost allocation:")
            self.show_opencost_examples()
    
    def show_opencost_examples(self) -> None:
        """Show example OpenCost API calls."""
        examples = [
            "# Cost by team (last 7 days)",
            "curl 'http://opencost:9003/allocation?window=7d&aggregate=label:team'",
            "",
            "# Cost by pipeline (last 24 hours)", 
            "curl 'http://opencost:9003/allocation?window=1d&aggregate=label:pipeline'",
            "",
            "# Cost by cost center (last month)",
            "curl 'http://opencost:9003/allocation?window=30d&aggregate=label:cost_center'",
            "",
            "# Multi-dimensional cost breakdown",
            "curl 'http://opencost:9003/allocation?window=7d&aggregate=label:team,label:pipeline,label:env'",
            "",
            "# Cost efficiency metrics",
            "curl 'http://opencost:9003/allocation?window=7d&includeIdle=false&format=json'"
        ]
        
        print("\nOpenCost API Examples:")
        print("="*50)
        for example in examples:
            print(example)
    
    def cleanup_demo_environment(self) -> None:
        """Clean up demo resources."""
        log("Cleaning up demo environment...")
        
        try:
            run_command(f"kubectl delete namespace {self.demo_namespace}")
            log(f"✓ Deleted namespace {self.demo_namespace}")
        except subprocess.CalledProcessError:
            log("Could not delete demo namespace", "WARNING")
        
        # Clean up temp files
        import glob
        temp_files = glob.glob("/tmp/demo-*.yaml")
        for file in temp_files:
            try:
                run_command(f"rm -f {file}")
            except:
                pass
    
    def run_demo(self) -> None:
        """Run the complete FinOps labeling demo."""
        log("Starting NeuroNews FinOps Labeling Governance Demo", "SUCCESS")
        print("="*60)
        
        try:
            # Prerequisites
            if not self.check_prerequisites():
                log("Prerequisites not met. Please install required components.", "ERROR")
                return
            
            # Setup
            self.setup_demo_environment()
            
            # Demo scenarios
            print("\n" + "="*60)
            print("DEMO SCENARIO 1: Valid Workload Deployment")
            print("="*60)
            self.demonstrate_valid_workload()
            
            print("\n" + "="*60)
            print("DEMO SCENARIO 2: Invalid Workload (Missing Labels)")
            print("="*60)
            self.demonstrate_invalid_workload()
            
            print("\n" + "="*60)
            print("DEMO SCENARIO 3: Invalid Label Values")
            print("="*60)
            self.demonstrate_invalid_values()
            
            print("\n" + "="*60)
            print("DEMO SCENARIO 4: Cost Allocation Views")
            print("="*60)
            self.demonstrate_cost_allocation()
            
            print("\n" + "="*60)
            print("DEMO SCENARIO 5: Compliance Reporting")
            print("="*60)
            self.demonstrate_compliance_reporting()
            
            print("\n" + "="*60)
            print("DEMO SCENARIO 6: OpenCost Integration")
            print("="*60)
            self.demonstrate_opencost_integration()
            
            print("\n" + "="*60)
            log("Demo completed successfully!", "SUCCESS")
            print("="*60)
            
            # Wait before cleanup
            input("\nPress Enter to cleanup demo environment...")
            
        except KeyboardInterrupt:
            log("Demo interrupted by user", "WARNING")
        except Exception as e:
            log(f"Demo failed with error: {e}", "ERROR")
        finally:
            self.cleanup_demo_environment()

def main():
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "--no-cleanup":
        demo = FinOpsLabelingDemo()
        demo.run_demo()
    else:
        demo = FinOpsLabelingDemo()
        demo.run_demo()

if __name__ == "__main__":
    main()
