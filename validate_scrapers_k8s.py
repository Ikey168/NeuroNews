#!/usr/bin/env python3
"""
NeuroNews Scrapers Kubernetes Validation Script
Issue #73: Deploy Scrapers as Kubernetes CronJobs

This script validates that all scraper CronJobs are properly deployed and configured.
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# ANSI color codes
COLORS = {
    "GREEN": "\033[92m",
    "RED": "\033[91m",
    "YELLOW": "\033[93m",
    "BLUE": "\033[94m",
    "CYAN": "\033[96m",
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
}


def print_colored(message: str, color: str = "RESET") -> None:
    """Print colored message to console."""
    print(f"{COLORS.get(color, COLORS['RESET'])}{message}{COLORS['RESET']}")


def run_kubectl(command: str) -> Dict[str, Any]:
    """Run kubectl command and return JSON output."""
    try:
        full_command = "kubectl {0}".format(command)
        result = subprocess.run(
            full_command.split(), capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            print_colored("❌ Command failed: {0}".format(full_command), "RED")
            print_colored("Error: {0}".format(result.stderr), "RED")
            return {}

        if result.stdout.strip():
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"output": result.stdout.strip()}

        return {}

    except subprocess.TimeoutExpired:
        print_colored("❌ Command timed out: {0}".format(command), "RED")
        return {}
    except Exception as e:
        print_colored("❌ Command error: {0}".format(str(e)), "RED")
        return {}


def check_namespace() -> bool:
    """Check if neuronews namespace exists."""
    print_colored("🔍 Checking namespace...", "BLUE")

    result = run_kubectl("get namespace neuronews -o json")
    if result and "metadata" in result:
        print_colored("✅ Namespace 'neuronews' exists", "GREEN")

        # Check labels
        labels = result.get("metadata", {}).get("labels", {})
        if labels.get("name") == "neuronews":
            print_colored("✅ Namespace properly labeled", "GREEN")
        else:
            print_colored("⚠️  Namespace missing proper labels", "YELLOW")

        return True

    print_colored("❌ Namespace 'neuronews' not found", "RED")
    return False


def check_rbac() -> bool:
    """Check RBAC configuration."""
    print_colored("🔍 Checking RBAC configuration...", "BLUE")

    success = True

    # Check ServiceAccount
    sa_result = run_kubectl(
        "get serviceaccount neuronews-scrapers -n neuronews -o json"
    )
    if sa_result and "metadata" in sa_result:
        print_colored("✅ ServiceAccount 'neuronews-scrapers' exists", "GREEN")
    else:
        print_colored("❌ ServiceAccount 'neuronews-scrapers' not found", "RED")
        success = False

    # Check Role
    role_result = run_kubectl("get role neuronews-scrapers-role -n neuronews -o json")
    if role_result and "metadata" in role_result:
        print_colored("✅ Role 'neuronews-scrapers-role' exists", "GREEN")

        # Check role permissions
        rules = role_result.get("rules", [])
        expected_resources = ["jobs", "secrets", "configmaps"]
        has_job_permissions = any("jobs" in rule.get("resources", []) for rule in rules)

        if has_job_permissions:
            print_colored("✅ Role has required permissions", "GREEN")
        else:
            print_colored("⚠️  Role may be missing job permissions", "YELLOW")
    else:
        print_colored("❌ Role 'neuronews-scrapers-role' not found", "RED")
        success = False

    # Check RoleBinding
    rb_result = run_kubectl(
        "get rolebinding neuronews-scrapers-binding -n neuronews -o json"
    )
    if rb_result and "metadata" in rb_result:
        print_colored("✅ RoleBinding 'neuronews-scrapers-binding' exists", "GREEN")
    else:
        print_colored("❌ RoleBinding 'neuronews-scrapers-binding' not found", "RED")
        success = False

    return success


def check_configmaps() -> bool:
    """Check ConfigMap configuration."""
    print_colored("🔍 Checking ConfigMaps...", "BLUE")

    cm_result = run_kubectl(
        "get configmap neuronews-scraper-config -n neuronews -o json"
    )
    if cm_result and "metadata" in cm_result:
        print_colored("✅ ConfigMap 'neuronews-scraper-config' exists", "GREEN")

        # Check data fields
        data = cm_result.get("data", {})
        expected_keys = [
            "NEWS_SOURCES",
            "TECH_SOURCES",
            "AI_SOURCES",
            "RATE_LIMIT_REQUESTS",
        ]

        for key in expected_keys:
            if key in data:
                print_colored("✅ ConfigMap has {0}".format(key), "GREEN")
            else:
                print_colored("⚠️  ConfigMap missing {0}".format(key), "YELLOW")

        return True

    print_colored("❌ ConfigMap 'neuronews-scraper-config' not found", "RED")
    return False


def check_cronjobs() -> Dict[str, Any]:
    """Check CronJob configuration and status."""
    print_colored("🔍 Checking CronJobs...", "BLUE")

    cronjobs_result = run_kubectl(
        "get cronjobs -n neuronews -l app=neuronews-scrapers -o json"
    )
    if not cronjobs_result or "items" not in cronjobs_result:
        print_colored("❌ No CronJobs found", "RED")
        return {}

    cronjobs = cronjobs_result["items"]
    expected_cronjobs = [
        "neuronews-news-scraper",
        "neuronews-tech-scraper",
        "neuronews-ai-scraper",
    ]

    cronjob_info = {}

    for cronjob in cronjobs:
        name = cronjob["metadata"]["name"]
        schedule = cronjob["spec"]["schedule"]
        suspend = cronjob["spec"].get("suspend", False)

        cronjob_info[name] = {
            "schedule": schedule,
            "suspended": suspend,
            "last_schedule": cronjob.get("status", {}).get("lastScheduleTime"),
            "active_jobs": len(cronjob.get("status", {}).get("active", [])),
        }

        if name in expected_cronjobs:
            print_colored(f"✅ CronJob '{name}' exists", "GREEN")
            print_colored("   Schedule: {0}".format(schedule), "CYAN")
            if suspend:
                print_colored("   ⚠️  Currently suspended", "YELLOW")
            else:
                print_colored("   ✅ Active", "GREEN")
        else:
            print_colored(f"⚠️  Unexpected CronJob '{name}'", "YELLOW")

    # Check for missing CronJobs
    found_names = [cj["metadata"]["name"] for cj in cronjobs]
    for expected in expected_cronjobs:
        if expected not in found_names:
            print_colored(f"❌ Missing CronJob '{expected}'", "RED")

    return cronjob_info


def check_jobs() -> Dict[str, Any]:
    """Check recent job execution."""
    print_colored("🔍 Checking recent jobs...", "BLUE")

    jobs_result = run_kubectl("get jobs -n neuronews -l app=neuronews-scrapers -o json")
    if not jobs_result or "items" not in jobs_result:
        print_colored("ℹ️  No jobs found (this is normal for new deployments)", "CYAN")
        return {}

    jobs = jobs_result["items"]
    job_info = {
        "total": len(jobs),
        "successful": 0,
        "failed": 0,
        "active": 0,
        "recent_jobs": [],
    }

    for job in jobs:
        name = job["metadata"]["name"]
        status = job.get("status", {})
        creation_time = job["metadata"]["creationTimestamp"]

        job_data = {"name": name, "creation_time": creation_time, "status": "unknown"}

        if status.get("succeeded", 0) > 0:
            job_info["successful"] += 1
            job_data["status"] = "successful"
            print_colored(f"✅ Job '{name}' succeeded", "GREEN")
        elif status.get("failed", 0) > 0:
            job_info["failed"] += 1
            job_data["status"] = "failed"
            print_colored(f"❌ Job '{name}' failed", "RED")
        elif status.get("active", 0) > 0:
            job_info["active"] += 1
            job_data["status"] = "active"
            print_colored(f"🔄 Job '{name}' running", "YELLOW")

        job_info["recent_jobs"].append(job_data)

    print_colored(
        f"ℹ️  Job Summary: {job_info['successful']} successful, {job_info['failed']} failed, {job_info['active']} active",
        "CYAN",
    )
    return job_info


def check_monitoring() -> bool:
    """Check monitoring configuration."""
    print_colored("🔍 Checking monitoring configuration...", "BLUE")

    success = True

    # Check ServiceMonitor
    sm_result = run_kubectl(
        "get servicemonitor neuronews-scrapers-monitor -n neuronews -o json"
    )
    if sm_result and "metadata" in sm_result:
        print_colored("✅ ServiceMonitor exists", "GREEN")
    else:
        print_colored("⚠️  ServiceMonitor not found (may not be deployed)", "YELLOW")
        success = False

    # Check PrometheusRule
    pr_result = run_kubectl(
        "get prometheusrule neuronews-scrapers-alerts -n neuronews -o json"
    )
    if pr_result and "metadata" in pr_result:
        print_colored("✅ PrometheusRule exists", "GREEN")
    else:
        print_colored("⚠️  PrometheusRule not found (may not be deployed)", "YELLOW")
        success = False

    return success


def check_network_policies() -> bool:
    """Check network policies."""
    print_colored("🔍 Checking network policies...", "BLUE")

    np_result = run_kubectl(
        "get networkpolicy neuronews-scrapers-network-policy -n neuronews -o json"
    )
    if np_result and "metadata" in np_result:
        print_colored("✅ Network policy exists", "GREEN")
        return True
    else:
        print_colored("⚠️  Network policy not found", "YELLOW")
        return False


def check_resource_quotas() -> bool:
    """Check resource quotas and limits."""
    print_colored("🔍 Checking resource management...", "BLUE")

    success = True

    # Check ResourceQuota
    rq_result = run_kubectl(
        "get resourcequota neuronews-scrapers-quota -n neuronews -o json"
    )
    if rq_result and "metadata" in rq_result:
        print_colored("✅ ResourceQuota exists", "GREEN")

        # Check quota usage
        status = rq_result.get("status", {})
        if "used" in status and "hard" in status:
            used = status["used"]
            hard = status["hard"]
            print_colored(
                f"   CPU used: {used.get('requests.cpu', '0')} / {hard.get('requests.cpu', 'unlimited')}",
                "CYAN",
            )
            print_colored(
                f"   Memory used: {used.get('requests.memory', '0')} / {hard.get('requests.memory', 'unlimited')}",
                "CYAN",
            )
    else:
        print_colored("⚠️  ResourceQuota not found", "YELLOW")
        success = False

    # Check LimitRange
    lr_result = run_kubectl(
        "get limitrange neuronews-scrapers-limits -n neuronews -o json"
    )
    if lr_result and "metadata" in lr_result:
        print_colored("✅ LimitRange exists", "GREEN")
    else:
        print_colored("⚠️  LimitRange not found", "YELLOW")
        success = False

    return success


def test_job_creation() -> bool:
    """Test manual job creation capability."""
    print_colored("🔍 Testing job creation capability...", "BLUE")

    # Try to create a test job
    test_job_name = "test-scraper-job-{0}".format(int(time.time()))

    # Get a CronJob to use as template
    cronjobs_result = run_kubectl(
        "get cronjobs -n neuronews -l app=neuronews-scrapers -o json"
    )
    if not cronjobs_result or not cronjobs_result.get("items"):
        print_colored("❌ No CronJobs available for testing", "RED")
        return False

    # Use the first CronJob as template
    cronjob = cronjobs_result["items"][0]
    cronjob_name = cronjob["metadata"]["name"]

    print_colored("ℹ️  Attempting to create test job from {0}".format(cronjob_name), "CYAN")

    # Note: We'll just check if we have the permissions, not actually create the job
    # to avoid cluttering the cluster with test jobs
    auth_result = run_kubectl(
        "auth can-i create jobs --as=system:serviceaccount:neuronews:neuronews-scrapers -n neuronews"
    )
    if auth_result and auth_result.get("output", "").strip().lower() == "yes":
        print_colored("✅ Job creation permissions verified", "GREEN")
        return True
    else:
        print_colored("❌ Missing job creation permissions", "RED")
        return False


def generate_validation_report(results: Dict[str, Any]) -> None:
    """Generate a comprehensive validation report."""
    print_colored("\n" + "=" * 80, "BOLD")
    print_colored("📊 VALIDATION REPORT", "BOLD")
    print_colored("=" * 80, "BOLD")

    # Overall status
    all_passed = all(results.values())
    if all_passed:
        print_colored("🎉 ALL VALIDATIONS PASSED", "GREEN")
        print_colored(
            "✅ Scraper CronJobs are properly deployed and configured", "GREEN"
        )
    else:
        print_colored("⚠️  SOME VALIDATIONS FAILED", "YELLOW")
        print_colored(
            "🔧 Please review the issues above and redeploy if necessary", "YELLOW"
        )

    print()

    # Component status
    components = {
        "namespace": "Namespace Configuration",
        "rbac": "RBAC Security",
        "configmaps": "Configuration Management",
        "cronjobs": "CronJob Deployment",
        "monitoring": "Monitoring Setup",
        "network": "Network Policies",
        "resources": "Resource Management",
        "job_creation": "Job Creation Test",
    }

    for key, name in components.items():
        status = "✅ PASS" if results.get(key, False) else "❌ FAIL"
        color = "GREEN" if results.get(key, False) else "RED"
        print_colored("{0} {1}".format(name:<30, status), color)

    print()

    # Recommendations
    print_colored("📋 RECOMMENDATIONS:", "BOLD")

    if not results.get("monitoring", False):
        print_colored(
            "• Deploy monitoring components for better observability", "YELLOW"
        )

    if not results.get("network", False):
        print_colored("• Configure network policies for enhanced security", "YELLOW")

    if not results.get("resources", False):
        print_colored("• Set up resource quotas and limits for stability", "YELLOW")

    if not all_passed:
        print_colored(
            "• Run './scripts/deploy-k8s-scrapers.sh deploy' to fix missing components",
            "CYAN",
        )
        print_colored(
            "• Check logs with './scripts/deploy-k8s-scrapers.sh logs'", "CYAN"
        )
        print_colored(
            "• Validate again with './scripts/deploy-k8s-scrapers.sh validate'", "CYAN"
        )
    else:
        print_colored(
            "• Monitor job execution with './scripts/deploy-k8s-scrapers.sh monitor'",
            "CYAN",
        )
        print_colored(
            "• View status with './scripts/deploy-k8s-scrapers.sh status'", "CYAN"
        )
        print_colored(
            "• Trigger manual jobs with './scripts/deploy-k8s-scrapers.sh trigger [TYPE]'",
            "CYAN",
        )

    print_colored("\n" + "=" * 80, "BOLD")


def main():
    """Run comprehensive validation of scraper deployment."""
    print_colored("🚀 NeuroNews Scrapers Kubernetes Validation", "BOLD")
    print_colored("Issue #73: Deploy Scrapers as Kubernetes CronJobs", "CYAN")
    print_colored(
        f"Validation Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "CYAN"
    )
    print()

    # Run all validation checks
    results = {}

    try:
        results["namespace"] = check_namespace()
        print()

        results["rbac"] = check_rbac()
        print()

        results["configmaps"] = check_configmaps()
        print()

        cronjob_info = check_cronjobs()
        results["cronjobs"] = bool(cronjob_info)
        print()

        job_info = check_jobs()
        print()

        results["monitoring"] = check_monitoring()
        print()

        results["network"] = check_network_policies()
        print()

        results["resources"] = check_resource_quotas()
        print()

        results["job_creation"] = test_job_creation()
        print()

        # Generate report
        generate_validation_report(results)

        # Save results to file
        validation_results = {
            "timestamp": datetime.now().isoformat(),
            "issue": "Issue #73: Deploy Scrapers as Kubernetes CronJobs",
            "overall_status": "PASSED" if all(results.values()) else "FAILED",
            "component_results": results,
            "cronjob_info": cronjob_info,
            "job_info": job_info,
            "validation_summary": {
                "total_components": len(results),
                "passed": sum(1 for v in results.values() if v),
                "failed": sum(1 for v in results.values() if not v),
            },
        }

        with open("issue_73_validation_results.json", "w") as f:
            json.dump(validation_results, f, indent=2, default=str)

        print_colored(
            "💾 Validation results saved to issue_73_validation_results.json", "CYAN"
        )

        # Return appropriate exit code
        sys.exit(0 if all(results.values()) else 1)

    except KeyboardInterrupt:
        print_colored("\n⚠️  Validation interrupted by user", "YELLOW")
        sys.exit(1)
    except Exception as e:
        print_colored("\n❌ Validation failed with error: {0}".format(str(e)), "RED")
        sys.exit(1)


if __name__ == "__main__":
    main()
