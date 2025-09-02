#!/bin/bash

# Simplified Carbon Tracking Validation
# Quick validation of Issue #342 implementation

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Carbon Tracking Implementation Validation ==="
echo "Date: $(date)"
echo "Directory: $SCRIPT_DIR"
echo

# Check files exist
echo "🔍 Checking file existence..."
files=(
    "opencost-carbon.yaml"
    "prometheus-carbon-rules.yaml" 
    "grafana-carbon-dashboard.json"
    "install-carbon-tracking.sh"
)

all_files_exist=true
for file in "${files[@]}"; do
    if [[ -f "$SCRIPT_DIR/$file" ]]; then
        echo "✅ $file - EXISTS"
    else
        echo "❌ $file - MISSING"
        all_files_exist=false
    fi
done

echo

# Check OpenCost configuration
echo "🔍 Validating OpenCost carbon configuration..."
config_file="$SCRIPT_DIR/opencost-carbon.yaml"

if [[ -f "$config_file" ]]; then
    # Check for carbon intensity data
    if grep -q "carbon_intensity:" "$config_file"; then
        echo "✅ Carbon intensity data found"
    else
        echo "❌ Carbon intensity data missing"
    fi
    
    # Check for AWS regions
    if grep -q "us-east-1:" "$config_file"; then
        echo "✅ AWS region data found"
    else
        echo "❌ AWS region data missing"
    fi
    
    # Check for instance power data
    if grep -q "power_consumption:" "$config_file"; then
        echo "✅ Instance power data found"
    else
        echo "❌ Instance power data missing"
    fi
fi

echo

# Check Prometheus rules
echo "🔍 Validating Prometheus carbon rules..."
rules_file="$SCRIPT_DIR/prometheus-carbon-rules.yaml"

if [[ -f "$rules_file" ]]; then
    # Check for carbon metrics
    if grep -q "neuronews:carbon:" "$rules_file"; then
        echo "✅ Carbon metrics rules found"
    else
        echo "❌ Carbon metrics rules missing"
    fi
    
    # Check for pipeline metrics
    if grep -q "pipeline_emissions" "$rules_file"; then
        echo "✅ Pipeline carbon tracking found"
    else
        echo "❌ Pipeline carbon tracking missing"
    fi
    
    # Check for cluster metrics
    if grep -q "cluster_total" "$rules_file"; then
        echo "✅ Cluster total carbon tracking found"
    else
        echo "❌ Cluster total carbon tracking missing"
    fi
fi

echo

# Check Grafana dashboard
echo "🔍 Validating Grafana dashboard..."
dashboard_file="$SCRIPT_DIR/grafana-carbon-dashboard.json"

if [[ -f "$dashboard_file" ]]; then
    # Check if it's valid JSON
    if python3 -m json.tool "$dashboard_file" > /dev/null 2>&1; then
        echo "✅ Dashboard JSON is valid"
    else
        echo "❌ Dashboard JSON is invalid"
    fi
    
    # Check for carbon panels
    if grep -q "Carbon Emissions" "$dashboard_file"; then
        echo "✅ Carbon emissions panels found"
    else
        echo "❌ Carbon emissions panels missing"
    fi
    
    # Check for pipeline breakdown
    if grep -q "pipeline" "$dashboard_file"; then
        echo "✅ Pipeline breakdown panels found"
    else
        echo "❌ Pipeline breakdown panels missing"
    fi
fi

echo

# Check installation script
echo "🔍 Validating installation script..."
install_file="$SCRIPT_DIR/install-carbon-tracking.sh"

if [[ -f "$install_file" && -x "$install_file" ]]; then
    echo "✅ Installation script exists and is executable"
    
    # Check for OpenCost installation
    if grep -q "opencost" "$install_file"; then
        echo "✅ OpenCost installation code found"
    else
        echo "❌ OpenCost installation code missing"
    fi
    
    # Check for dashboard import
    if grep -q "dashboard" "$install_file"; then
        echo "✅ Dashboard import code found"
    else
        echo "❌ Dashboard import code missing"
    fi
else
    echo "❌ Installation script missing or not executable"
fi

echo

# DoD Validation
echo "🎯 Definition of Done Validation..."

dod_passed=0
dod_total=3

# DoD 1: Dashboard shows carbon per pipeline
if grep -q "pipeline.*carbon\|carbon.*pipeline" "$dashboard_file" 2>/dev/null; then
    echo "✅ DoD 1: Dashboard shows carbon per pipeline"
    ((dod_passed++))
else
    echo "❌ DoD 1: Dashboard shows carbon per pipeline"
fi

# DoD 2: Dashboard shows cluster total  
if grep -q "cluster.*total\|total.*cluster" "$dashboard_file" 2>/dev/null; then
    echo "✅ DoD 2: Dashboard shows cluster total"
    ((dod_passed++))
else
    echo "❌ DoD 2: Dashboard shows cluster total"
fi

# DoD 3: OpenCost integration with Prometheus
if grep -q "opencost" "$rules_file" 2>/dev/null && grep -q "prometheus" "$config_file" 2>/dev/null; then
    echo "✅ DoD 3: OpenCost integration with Prometheus"
    ((dod_passed++))
else
    echo "❌ DoD 3: OpenCost integration with Prometheus"
fi

echo

# Summary
echo "📊 VALIDATION SUMMARY"
echo "===================="
echo "Files created: $(([[ $all_files_exist == true ]] && echo "4/4" || echo "X/4"))"
echo "DoD requirements: $dod_passed/$dod_total"

if [[ $all_files_exist == true && $dod_passed -eq $dod_total ]]; then
    echo "🎉 SUCCESS: Carbon tracking implementation is complete and ready!"
    exit 0
else
    echo "⚠️  WARNING: Some validation checks failed"
    exit 1
fi
