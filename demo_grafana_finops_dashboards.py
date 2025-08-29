#!/usr/bin/env python3

"""
NeuroNews Grafana FinOps Dashboards Demo

This script demonstrates the Grafana dashboard functionality including:
- Dashboard installation and configuration
- Cost visualization by pipeline, team, and environment
- Integration with OpenCost for real-time cost data
- FinOps labeling integration for accurate attribution
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any

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

class GrafanaDashboardDemo:
    """Demo class for Grafana FinOps dashboards."""
    
    def __init__(self):
        self.namespace_monitoring = "monitoring"
        self.namespace_opencost = "opencost"
        self.grafana_port = 3000
        self.prometheus_port = 9090
        self.opencost_port = 9003
        
    def check_prerequisites(self) -> bool:
        """Check if required components are available."""
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
        
        # Check Grafana
        try:
            run_command(f"kubectl get deployment grafana -n {self.namespace_monitoring}")
            log("✓ Grafana deployment found")
        except subprocess.CalledProcessError:
            log("✗ Grafana deployment not found", "WARNING")
        
        # Check OpenCost
        try:
            run_command(f"kubectl get deployment opencost -n {self.namespace_opencost}")
            log("✓ OpenCost deployment found")
        except subprocess.CalledProcessError:
            log("✗ OpenCost deployment not found", "WARNING")
        
        # Check Prometheus
        try:
            run_command(f"kubectl get deployment prometheus-server -n {self.namespace_monitoring}")
            log("✓ Prometheus deployment found")
        except subprocess.CalledProcessError:
            log("✗ Prometheus deployment not found", "WARNING")
        
        return True
    
    def demonstrate_dashboard_structure(self) -> None:
        """Show the structure and features of each dashboard."""
        log("Demonstrating dashboard structure...")
        
        print("\n" + "="*60)
        print("GRAFANA FINOPS DASHBOARDS OVERVIEW")
        print("="*60)
        
        # Parse dashboard files and show structure
        try:
            import os
            script_dir = os.path.dirname(os.path.abspath(__file__))
            dashboard_dir = os.path.join(script_dir, "grafana", "dashboards")
            
            for dashboard_file in os.listdir(dashboard_dir):
                if dashboard_file.endswith('.json'):
                    with open(os.path.join(dashboard_dir, dashboard_file), 'r') as f:
                        dashboard = json.load(f)
                    
                    print(f"\n📊 Dashboard: {dashboard.get('title', 'Unknown')}")
                    print(f"   UID: {dashboard.get('uid', 'N/A')}")
                    print(f"   Tags: {', '.join(dashboard.get('tags', []))}")
                    print(f"   Panels: {len(dashboard.get('panels', []))}")
                    
                    # Show panel details
                    for i, panel in enumerate(dashboard.get('panels', [])[:5]):  # Show first 5
                        print(f"   • Panel {i+1}: {panel.get('title', 'Untitled')}")
                        print(f"     Type: {panel.get('type', 'unknown')}")
                        if panel.get('description'):
                            print(f"     Description: {panel['description'][:50]}...")
                    
                    if len(dashboard.get('panels', [])) > 5:
                        print(f"   ... and {len(dashboard['panels']) - 5} more panels")
                    
        except Exception as e:
            log(f"Could not parse dashboard files: {e}", "WARNING")
    
    def demonstrate_key_queries(self) -> None:
        """Show the key PromQL queries used in dashboards."""
        log("Demonstrating key PromQL queries...")
        
        print("\n" + "="*60)
        print("KEY PROMQL QUERIES FOR FINOPS")
        print("="*60)
        
        queries = {
            "Monthly Cluster Cost": {
                "query": "sum(opencost_node_cost_hourly) * 730",
                "description": "Total monthly infrastructure cost calculation"
            },
            "Cost by Pipeline": {
                "query": """sum by (pipeline) (
  (avg(kube_pod_container_resource_requests{resource="cpu"}) * on(node) group_left() avg(opencost_node_cost_hourly{cost_type="compute"}))
  +
  ((avg(kube_pod_container_resource_requests{resource="memory"})/(1024^3)) * on(node) group_left() avg(opencost_node_cost_hourly{cost_type="memory"}))
) * on(pod) group_right() kube_pod_labels{label_pipeline!=""}""",
                "description": "Cost allocation by business pipeline (ingest, transform, api, rag, etc.)"
            },
            "Cost by Team": {
                "query": """sum by (team) (
  (avg(kube_pod_container_resource_requests{resource="cpu"}) * on(node) group_left() avg(opencost_node_cost_hourly{cost_type="compute"}))
  +
  ((avg(kube_pod_container_resource_requests{resource="memory"})/(1024^3)) * on(node) group_left() avg(opencost_node_cost_hourly{cost_type="memory"}))
) * on(pod) group_right() kube_pod_labels{label_team!=""}""",
                "description": "Cost allocation by team ownership"
            },
            "Load Balancer Costs": {
                "query": "sum(opencost_load_balancer_cost) by (namespace)",
                "description": "Network load balancer costs by namespace"
            },
            "Storage Costs": {
                "query": "sum by (namespace) (kube_persistentvolume_capacity_bytes * on(persistentvolume) group_left() opencost_pv_cost_hourly) / 1024^3",
                "description": "Persistent volume costs by namespace"
            },
            "Resource Efficiency": {
                "query": """avg by (pipeline) (
  rate(container_cpu_usage_seconds_total[5m]) / 
  on(pod) group_left() kube_pod_container_resource_requests{resource="cpu"}
) * on(pod) group_right() kube_pod_labels{label_pipeline!=""}""",
                "description": "CPU utilization efficiency by pipeline"
            }
        }
        
        for name, details in queries.items():
            print(f"\n🔍 {name}")
            print(f"   Description: {details['description']}")
            print(f"   Query: {details['query']}")
    
    def start_port_forwards(self) -> Dict[str, subprocess.Popen]:
        """Start port forwards for services."""
        log("Starting port forwards for demo...")
        
        port_forwards = {}
        
        # Grafana port forward
        try:
            pf = subprocess.Popen([
                "kubectl", "port-forward", 
                f"svc/grafana", 
                f"{self.grafana_port}:80",
                "-n", self.namespace_monitoring
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            port_forwards['grafana'] = pf
            log(f"✓ Grafana port forward started on {self.grafana_port}")
        except Exception as e:
            log(f"Could not start Grafana port forward: {e}", "WARNING")
        
        # Prometheus port forward
        try:
            pf = subprocess.Popen([
                "kubectl", "port-forward",
                f"svc/prometheus-server",
                f"{self.prometheus_port}:80", 
                "-n", self.namespace_monitoring
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            port_forwards['prometheus'] = pf
            log(f"✓ Prometheus port forward started on {self.prometheus_port}")
        except Exception as e:
            log(f"Could not start Prometheus port forward: {e}", "WARNING")
        
        # OpenCost port forward
        try:
            pf = subprocess.Popen([
                "kubectl", "port-forward",
                f"svc/opencost",
                f"{self.opencost_port}:9003",
                "-n", self.namespace_opencost
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            port_forwards['opencost'] = pf
            log(f"✓ OpenCost port forward started on {self.opencost_port}")
        except Exception as e:
            log(f"Could not start OpenCost port forward: {e}", "WARNING")
        
        # Wait for services to be ready
        time.sleep(5)
        return port_forwards
    
    def test_connectivity(self) -> None:
        """Test connectivity to forwarded services."""
        log("Testing service connectivity...")
        
        # Test Grafana
        try:
            result = run_command(f"curl -s --max-time 5 http://localhost:{self.grafana_port}/api/health", check=False)
            if result.returncode == 0:
                log("✓ Grafana is accessible")
            else:
                log("✗ Grafana is not accessible", "WARNING")
        except Exception as e:
            log(f"Could not test Grafana connectivity: {e}", "WARNING")
        
        # Test Prometheus
        try:
            result = run_command(f"curl -s --max-time 5 http://localhost:{self.prometheus_port}/api/v1/query?query=up", check=False)
            if result.returncode == 0 and "success" in result.stdout:
                log("✓ Prometheus is accessible")
            else:
                log("✗ Prometheus is not accessible", "WARNING")
        except Exception as e:
            log(f"Could not test Prometheus connectivity: {e}", "WARNING")
        
        # Test OpenCost
        try:
            result = run_command(f"curl -s --max-time 5 http://localhost:{self.opencost_port}/metrics", check=False)
            if result.returncode == 0 and "opencost_" in result.stdout:
                log("✓ OpenCost metrics are accessible")
            else:
                log("✗ OpenCost metrics are not accessible", "WARNING")
        except Exception as e:
            log(f"Could not test OpenCost connectivity: {e}", "WARNING")
    
    def demonstrate_finops_labeling(self) -> None:
        """Show FinOps labeling examples and coverage."""
        log("Demonstrating FinOps labeling integration...")
        
        print("\n" + "="*60)
        print("FINOPS LABELING INTEGRATION")
        print("="*60)
        
        # Show labeled workloads
        try:
            result = run_command(
                'kubectl get deployments --all-namespaces -o jsonpath=\'{range .items[*]}'
                '{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}'
                '{.metadata.labels.pipeline}{"\t"}{.metadata.labels.team}{"\t"}'
                '{.metadata.labels.env}{"\t"}{.metadata.labels.cost_center}{"\n"}{end}\'',
                check=False
            )
            
            if result.returncode == 0:
                print("\nDeployments with FinOps Labels:")
                print("Namespace\t\tDeployment\t\tPipeline\tTeam\t\tEnv\tCost Center")
                print("-" * 90)
                
                lines = result.stdout.strip().split('\n')
                labeled_count = 0
                
                for line in lines:
                    if line and not line.count('\t') == line.count('\t\t'):  # Has some labels
                        print(line)
                        labeled_count += 1
                
                print(f"\nFound {labeled_count} deployments with FinOps labels")
                
                if labeled_count == 0:
                    print("\n⚠️  No workloads found with FinOps labels!")
                    print("   Run the FinOps labeling governance setup to add required labels.")
                    print("   See: k8s/finops/install.sh")
            
        except Exception as e:
            log(f"Could not check FinOps labeling: {e}", "WARNING")
        
        # Show required labels schema
        print("\n📋 Required FinOps Labels:")
        labels = {
            "app": "Application or service name",
            "component": "Component type (backend, frontend, database, etc.)",
            "pipeline": "Business pipeline (ingest, transform, api, rag, monitoring, infra)",
            "team": "Owning team (neuronews, data-engineering, platform, etc.)",
            "env": "Environment (dev, staging, prod, test)",
            "cost_center": "Cost center (product, data-platform, infrastructure)"
        }
        
        for label, description in labels.items():
            print(f"   • {label}: {description}")
    
    def demonstrate_cost_allocation(self) -> None:
        """Show cost allocation examples using actual cluster data."""
        log("Demonstrating cost allocation queries...")
        
        print("\n" + "="*60)
        print("COST ALLOCATION DEMONSTRATION")
        print("="*60)
        
        # Test basic Prometheus queries if available
        basic_queries = [
            ("Cluster Nodes", "count(kube_node_info)"),
            ("Running Pods", "count(kube_pod_info{phase=\"Running\"})"),
            ("Total CPU Requests", "sum(kube_pod_container_resource_requests{resource=\"cpu\"})"),
            ("Total Memory Requests", "sum(kube_pod_container_resource_requests{resource=\"memory\"}) / 1024^3"),
        ]
        
        for name, query in basic_queries:
            try:
                result = run_command(
                    f'curl -s --max-time 5 "http://localhost:{self.prometheus_port}/api/v1/query?query={query}"',
                    check=False
                )
                
                if result.returncode == 0:
                    try:
                        response = json.loads(result.stdout)
                        if response.get('status') == 'success' and response.get('data', {}).get('result'):
                            value = response['data']['result'][0]['value'][1]
                            print(f"   • {name}: {value}")
                        else:
                            print(f"   • {name}: No data")
                    except (json.JSONDecodeError, KeyError, IndexError):
                        print(f"   • {name}: Query error")
                else:
                    print(f"   • {name}: Connection error")
            except Exception as e:
                print(f"   • {name}: Error - {e}")
        
        # Show OpenCost API examples
        print("\n🔗 OpenCost API Examples:")
        print("   These queries show cost allocation by different dimensions")
        
        opencost_examples = [
            ("Cost by namespace", "/allocation?window=7d&aggregate=namespace"),
            ("Cost by team", "/allocation?window=7d&aggregate=label:team"),
            ("Cost by pipeline", "/allocation?window=7d&aggregate=label:pipeline"),
            ("Cost by environment", "/allocation?window=7d&aggregate=label:env"),
            ("Multi-dimensional", "/allocation?window=7d&aggregate=label:team,label:pipeline")
        ]
        
        for name, endpoint in opencost_examples:
            print(f"   • {name}: curl http://localhost:{self.opencost_port}{endpoint}")
    
    def show_dashboard_access(self) -> None:
        """Show how to access the dashboards."""
        log("Dashboard access information...")
        
        print("\n" + "="*60)
        print("DASHBOARD ACCESS")
        print("="*60)
        
        print(f"\n🌐 Grafana Web Interface:")
        print(f"   URL: http://localhost:{self.grafana_port}")
        print(f"   Default credentials: admin/admin (change on first login)")
        
        print(f"\n📊 Available Dashboards:")
        print(f"   • OpenCost Overview")
        print(f"     - Located in: OpenCost folder")
        print(f"     - Features: Cluster cost overview, resource efficiency")
        print(f"   • NeuroNews FinOps")
        print(f"     - Located: FinOps folder")
        print(f"     - Features: Pipeline costs, team allocation, business metrics")
        
        print(f"\n🔧 Data Sources:")
        print(f"   • Prometheus: http://localhost:{self.prometheus_port}")
        print(f"   • OpenCost: http://localhost:{self.opencost_port}")
        
        print(f"\n💡 Tips:")
        print(f"   • Use time range selector to view historical costs")
        print(f"   • Filter by pipeline/team using dashboard variables") 
        print(f"   • Set up alerts for cost thresholds")
        print(f"   • Export data for further analysis")
    
    def cleanup_port_forwards(self, port_forwards: Dict[str, subprocess.Popen]) -> None:
        """Clean up port forward processes."""
        log("Cleaning up port forwards...")
        
        for service, process in port_forwards.items():
            try:
                process.terminate()
                process.wait(timeout=5)
                log(f"✓ Stopped {service} port forward")
            except subprocess.TimeoutExpired:
                process.kill()
                log(f"✓ Killed {service} port forward")
            except Exception as e:
                log(f"Could not stop {service} port forward: {e}", "WARNING")
    
    def run_demo(self) -> None:
        """Run the complete Grafana dashboard demo."""
        log("Starting NeuroNews Grafana FinOps Dashboards Demo", "SUCCESS")
        print("="*60)
        
        port_forwards = {}
        
        try:
            # Prerequisites
            if not self.check_prerequisites():
                log("Prerequisites not met. Some demo features may not work.", "WARNING")
            
            # Dashboard structure
            self.demonstrate_dashboard_structure()
            
            # Key queries
            self.demonstrate_key_queries()
            
            # Start port forwards
            port_forwards = self.start_port_forwards()
            
            # Test connectivity
            if port_forwards:
                self.test_connectivity()
            
            # FinOps labeling
            self.demonstrate_finops_labeling()
            
            # Cost allocation
            if port_forwards.get('prometheus'):
                self.demonstrate_cost_allocation()
            
            # Access information
            self.show_dashboard_access()
            
            print("\n" + "="*60)
            log("Demo completed successfully!", "SUCCESS")
            print("="*60)
            
            if port_forwards:
                print(f"\n🚀 Services are now accessible:")
                if 'grafana' in port_forwards:
                    print(f"   • Grafana: http://localhost:{self.grafana_port}")
                if 'prometheus' in port_forwards:
                    print(f"   • Prometheus: http://localhost:{self.prometheus_port}")
                if 'opencost' in port_forwards:
                    print(f"   • OpenCost: http://localhost:{self.opencost_port}")
                
                print(f"\nPress Ctrl+C or Enter to stop port forwards and exit...")
                try:
                    input()
                except KeyboardInterrupt:
                    pass
            
        except KeyboardInterrupt:
            log("Demo interrupted by user", "WARNING")
        except Exception as e:
            log(f"Demo failed with error: {e}", "ERROR")
        finally:
            self.cleanup_port_forwards(port_forwards)

def main():
    """Main entry point."""
    demo = GrafanaDashboardDemo()
    demo.run_demo()

if __name__ == "__main__":
    main()
