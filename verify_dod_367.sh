#!/bin/bash

# DoD Verification Script for Issue 367: Versioning & Evolution Playbook
# Verifies that the evolution playbook meets all requirements

set -e

echo "🔍 Verifying DoD Requirements for Issue 367..."
echo "=============================================="

# Check 1: evolution.md exists and has required content
echo "✅ Check 1: Evolution playbook exists"
if [ ! -f "contracts/evolution.md" ]; then
    echo "❌ contracts/evolution.md not found"
    exit 1
fi
echo "   ✓ contracts/evolution.md exists"

# Check 2: Document has evolution rules section
echo ""
echo "✅ Check 2: Evolution rules documented"
if ! grep -q "## Evolution Rules" contracts/evolution.md; then
    echo "❌ Evolution rules section not found"
    exit 1
fi
echo "   ✓ Evolution rules section present"

# Check 3: Additive changes documented
echo ""
echo "✅ Check 3: Additive changes rules"
if ! grep -q "Additive Changes" contracts/evolution.md; then
    echo "❌ Additive changes rules not documented"
    exit 1
fi
echo "   ✓ Additive changes documented"

# Check 4: Deprecation strategy documented
echo ""
echo "✅ Check 4: Deprecation strategy (nullable+default)"
if ! grep -q "nullable + default" contracts/evolution.md; then
    echo "❌ Deprecation strategy not documented"
    exit 1
fi
echo "   ✓ Deprecation strategy documented"

# Check 5: Rename strategy documented (add+backfill+drop)
echo ""
echo "✅ Check 5: Rename strategy (add+backfill+drop)"
if ! grep -q "add + backfill + drop" contracts/evolution.md; then
    echo "❌ Rename strategy not documented"
    exit 1
fi
echo "   ✓ Rename strategy documented"

# Check 6: Dual-write strategy documented
echo ""
echo "✅ Check 6: Dual-write strategy"
if ! grep -q "## Dual-Write Strategy" contracts/evolution.md; then
    echo "❌ Dual-write strategy section not found"
    exit 1
fi
echo "   ✓ Dual-write strategy documented"

# Check 7: Dual-read with fallback documented
echo ""
echo "✅ Check 7: Dual-read with fallback"
if ! grep -q "## Dual-Read with Fallback" contracts/evolution.md; then
    echo "❌ Dual-read with fallback section not found"
    exit 1
fi
echo "   ✓ Dual-read with fallback documented"

# Check 8: Step-by-step procedures documented
echo ""
echo "✅ Check 8: Step-by-step procedures"
if ! grep -q "## Step-by-Step Procedures" contracts/evolution.md; then
    echo "❌ Step-by-step procedures section not found"
    exit 1
fi
echo "   ✓ Step-by-step procedures documented"

# Check 9: Runbook has clear procedures
echo ""
echo "✅ Check 9: Clear runbook procedures"
procedure_count=$(grep -c "### [0-9]\." contracts/evolution.md || echo "0")
if [ "$procedure_count" -lt 3 ]; then
    echo "❌ Insufficient step-by-step procedures found (need at least 3)"
    exit 1
fi
echo "   ✓ $procedure_count clear procedures documented"

# Check 10: Code examples present
echo ""
echo "✅ Check 10: Code examples included"
if ! grep -q "```python" contracts/evolution.md; then
    echo "❌ Python code examples not found"
    exit 1
fi
if ! grep -q "```json" contracts/evolution.md; then
    echo "❌ JSON examples not found"
    exit 1
fi
echo "   ✓ Code examples present (Python + JSON)"

# Check 11: Link from main README exists
echo ""
echo "✅ Check 11: Link from main README"
if ! grep -q "evolution.md" contracts/README.md; then
    echo "❌ Link to evolution.md not found in main README"
    exit 1
fi
echo "   ✓ Link from main README exists"

# Check 12: Monitoring and validation section
echo ""
echo "✅ Check 12: Monitoring and validation"
if ! grep -q "## Monitoring and Validation" contracts/evolution.md; then
    echo "❌ Monitoring and validation section not found"
    exit 1
fi
echo "   ✓ Monitoring and validation documented"

# Check 13: Rollback procedures documented
echo ""
echo "✅ Check 13: Rollback procedures"
if ! grep -q "## Rollback Procedures" contracts/evolution.md; then
    echo "❌ Rollback procedures section not found"
    exit 1
fi
echo "   ✓ Rollback procedures documented"

# Check 14: Examples section with real scenarios
echo ""
echo "✅ Check 14: Real-world examples"
if ! grep -q "## Examples" contracts/evolution.md; then
    echo "❌ Examples section not found"
    exit 1
fi
example_count=$(grep -c "### Example [0-9]" contracts/evolution.md || echo "0")
if [ "$example_count" -lt 3 ]; then
    echo "❌ Insufficient examples found (need at least 3)"
    exit 1
fi
echo "   ✓ $example_count real-world examples documented"

# Check 15: Quick reference section
echo ""
echo "✅ Check 15: Quick reference guide"
if ! grep -q "## Quick Reference" contracts/evolution.md; then
    echo "❌ Quick reference section not found"
    exit 1
fi
echo "   ✓ Quick reference guide present"

# Summary
echo ""
echo "🎉 SUCCESS: All DoD requirements verified!"
echo "=============================================="
echo ""
echo "📋 Summary:"
echo "   ✓ Clear, step-by-step runbook exists"
echo "   ✓ Evolution rules documented (additive changes only)"
echo "   ✓ Deprecation strategy (nullable+default)"
echo "   ✓ Rename strategy (add+backfill+drop)"
echo "   ✓ Dual-write strategy outlined"
echo "   ✓ Dual-read with fallback documented"
echo "   ✓ Link from main README established"
echo "   ✓ Comprehensive examples and procedures"
echo ""
echo "📄 File Details:"
echo "   - contracts/evolution.md: $(wc -l < contracts/evolution.md) lines"
echo "   - Main sections: $(grep -c "^## " contracts/evolution.md)"
echo "   - Code examples: $(grep -c "\`\`\`" contracts/evolution.md)"
echo "   - Step-by-step procedures: $procedure_count"
echo "   - Real-world examples: $example_count"
echo ""
echo "✅ Issue 367 DoD requirements fully satisfied!"
