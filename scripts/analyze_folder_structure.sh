#!/bin/bash

# NeuroNews Folder Structure Analysis Script
# Analyzes current project structure and provides recommendations

set -e

echo "🔍 NeuroNews Project Structure Analysis"
echo "======================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Count files in root directory
root_files=$(find . -maxdepth 1 -type f | wc -l)
echo -e "${BLUE}📊 Root Directory Analysis:${NC}"
echo "   Files in root: $root_files"

if [ $root_files -gt 20 ]; then
    echo -e "   ${RED}❌ Too many files in root ($root_files > 20)${NC}"
    echo -e "   ${YELLOW}💡 Recommendation: Move files to appropriate subdirectories${NC}"
else
    echo -e "   ${GREEN}✅ Root directory is manageable${NC}"
fi

# Analyze demo files
demo_files=$(find . -maxdepth 1 -name "demo_*.py" | wc -l)
echo -e "${BLUE}📋 Demo Files Analysis:${NC}"
echo "   Demo files in root: $demo_files"

if [ $demo_files -gt 10 ]; then
    echo -e "   ${RED}❌ Too many demo files in root ($demo_files > 10)${NC}"
    echo -e "   ${YELLOW}💡 Recommendation: Move to examples/ directory${NC}"
else
    echo -e "   ${GREEN}✅ Demo files are manageable${NC}"
fi

# Analyze test files
test_files_root=$(find . -maxdepth 1 -name "test_*.py" | wc -l)
echo -e "${BLUE}🧪 Test Files Analysis:${NC}"
echo "   Test files in root: $test_files_root"

if [ $test_files_root -gt 5 ]; then
    echo -e "   ${RED}❌ Too many test files in root ($test_files_root > 5)${NC}"
    echo -e "   ${YELLOW}💡 Recommendation: Move to tests/ directory${NC}"
else
    echo -e "   ${GREEN}✅ Test files are manageable${NC}"
fi

# Analyze source code structure
echo -e "${BLUE}🔧 Source Code Analysis:${NC}"
if [ -d "src" ]; then
    src_depth=$(find src -type d | wc -l)
    echo "   Source directories: $src_depth"
    
    # Check for common anti-patterns
    if [ -f "src/main.py" ] && [ -f "main.py" ]; then
        echo -e "   ${YELLOW}⚠️ Duplicate main.py files detected${NC}"
    fi
    
    # Check source organization
    if [ -d "src/api" ] && [ -d "src/ml" ] && [ -d "src/nlp" ]; then
        echo -e "   ${GREEN}✅ Good module separation${NC}"
    else
        echo -e "   ${YELLOW}💡 Consider better module organization${NC}"
    fi
else
    echo -e "   ${RED}❌ No src/ directory found${NC}"
    echo -e "   ${YELLOW}💡 Recommendation: Create src/ directory for source code${NC}"
fi

# Analyze configuration files
echo -e "${BLUE}⚙️ Configuration Analysis:${NC}"
config_dirs=$(find . -maxdepth 1 -type d -name "*config*" | wc -l)
echo "   Configuration directories: $config_dirs"

if [ $config_dirs -gt 1 ]; then
    echo -e "   ${YELLOW}⚠️ Multiple config directories detected${NC}"
    echo -e "   ${YELLOW}💡 Recommendation: Consolidate into single config/ directory${NC}"
fi

# Analyze infrastructure files
echo -e "${BLUE}🚀 Infrastructure Analysis:${NC}"
infra_dirs=$(find . -maxdepth 1 -type d \( -name "*infra*" -o -name "*deploy*" -o -name "*terraform*" \) | wc -l)
echo "   Infrastructure directories: $infra_dirs"

if [ $infra_dirs -gt 1 ]; then
    echo -e "   ${YELLOW}⚠️ Multiple infrastructure directories detected${NC}"
    echo -e "   ${YELLOW}💡 Recommendation: Consolidate into single deploy/ directory${NC}"
fi

# Analyze Docker files
docker_files=$(find . -maxdepth 1 -name "docker-compose*.yml" -o -name "Dockerfile*" | wc -l)
echo -e "${BLUE}🐳 Docker Analysis:${NC}"
echo "   Docker files in root: $docker_files"

if [ $docker_files -gt 3 ]; then
    echo -e "   ${YELLOW}⚠️ Many Docker files in root${NC}"
    echo -e "   ${YELLOW}💡 Recommendation: Move to deploy/docker/ directory${NC}"
fi

# Analyze documentation
echo -e "${BLUE}📚 Documentation Analysis:${NC}"
md_files_root=$(find . -maxdepth 1 -name "*.md" | wc -l)
echo "   Markdown files in root: $md_files_root"

if [ $md_files_root -gt 5 ]; then
    echo -e "   ${YELLOW}⚠️ Many documentation files in root${NC}"
    echo -e "   ${YELLOW}💡 Recommendation: Organize into docs/ subdirectories${NC}"
fi

# Check for docs directory
if [ -d "docs" ]; then
    docs_structure=$(find docs -type d | wc -l)
    echo "   Docs subdirectories: $docs_structure"
    if [ $docs_structure -lt 3 ]; then
        echo -e "   ${YELLOW}💡 Consider organizing docs into categories${NC}"
    fi
else
    echo -e "   ${YELLOW}💡 Consider creating docs/ directory${NC}"
fi

# Analyze requirements files
echo -e "${BLUE}📦 Dependencies Analysis:${NC}"
req_files=$(find . -maxdepth 1 -name "requirements*.txt" | wc -l)
echo "   Requirements files: $req_files"

if [ $req_files -gt 5 ]; then
    echo -e "   ${YELLOW}⚠️ Many requirements files${NC}"
    echo -e "   ${YELLOW}💡 Consider using pyproject.toml instead${NC}"
fi

# Check for pyproject.toml
if [ -f "pyproject.toml" ]; then
    echo -e "   ${GREEN}✅ pyproject.toml found${NC}"
else
    echo -e "   ${YELLOW}💡 Consider creating pyproject.toml${NC}"
fi

# Overall recommendations
echo ""
echo -e "${BLUE}🎯 Overall Recommendations:${NC}"
echo ""

total_issues=0

if [ $root_files -gt 20 ]; then
    echo -e "1. ${YELLOW}Root Directory Cleanup:${NC}"
    echo "   - Move demo files to examples/"
    echo "   - Move test files to tests/"
    echo "   - Move scripts to scripts/"
    echo "   - Keep only essential files in root"
    total_issues=$((total_issues + 1))
fi

if [ $demo_files -gt 10 ]; then
    echo -e "2. ${YELLOW}Demo Organization:${NC}"
    echo "   - Create examples/ directory"
    echo "   - Categorize by functionality (api/, ml/, nlp/)"
    echo "   - Add README.md in each category"
    total_issues=$((total_issues + 1))
fi

if [ $test_files_root -gt 5 ]; then
    echo -e "3. ${YELLOW}Test Organization:${NC}"
    echo "   - Move all tests to tests/ directory"
    echo "   - Organize by test type (unit/, integration/, e2e/)"
    echo "   - Mirror source code structure"
    total_issues=$((total_issues + 1))
fi

if [ $config_dirs -gt 1 ] || [ $infra_dirs -gt 1 ]; then
    echo -e "4. ${YELLOW}Configuration Consolidation:${NC}"
    echo "   - Merge config directories into config/"
    echo "   - Merge infrastructure into deploy/"
    echo "   - Use environment-specific subdirectories"
    total_issues=$((total_issues + 1))
fi

if [ ! -f "pyproject.toml" ]; then
    echo -e "5. ${YELLOW}Modern Python Configuration:${NC}"
    echo "   - Create pyproject.toml"
    echo "   - Migrate from setup.py if exists"
    echo "   - Define tool configurations"
    total_issues=$((total_issues + 1))
fi

echo -e "6. ${YELLOW}Clean Architecture Implementation:${NC}"
echo "   - Implement domain-driven design in src/"
echo "   - Separate API, core logic, and data layers"
echo "   - Use dependency inversion principle"

echo -e "7. ${YELLOW}Development Workflow Improvements:${NC}"
echo "   - Add Makefile for common tasks"
echo "   - Create development tools directory"
echo "   - Add pre-commit hooks"

echo ""
if [ $total_issues -eq 0 ]; then
    echo -e "${GREEN}🎉 Project structure is already well organized!${NC}"
else
    echo -e "${YELLOW}📊 Found $total_issues structural improvement opportunities${NC}"
    echo -e "${BLUE}💡 Run ./scripts/migrate_folder_structure.sh to implement improvements${NC}"
fi

# Generate a quick structure overview
echo ""
echo -e "${BLUE}📁 Current Structure Overview:${NC}"
echo "Root files: $root_files"
echo "Demo files: $demo_files"
echo "Test files: $test_files_root"
echo "Config dirs: $config_dirs"
echo "Infrastructure dirs: $infra_dirs"
echo "Docker files: $docker_files"
echo "Documentation files: $md_files_root"

# Create a simple recommendations file
cat > STRUCTURE_RECOMMENDATIONS.md << EOF
# NeuroNews Structure Analysis Report

**Analysis Date:** $(date)

## Current State
- Root files: $root_files
- Demo files in root: $demo_files
- Test files in root: $test_files_root
- Configuration directories: $config_dirs
- Infrastructure directories: $infra_dirs
- Docker files in root: $docker_files
- Documentation files in root: $md_files_root

## Priority Recommendations

### High Priority
1. **Root Directory Cleanup** - Move demo, test, and script files
2. **Test Organization** - Consolidate tests in tests/ directory
3. **Configuration Management** - Merge config directories

### Medium Priority
1. **Documentation Organization** - Categorize docs by purpose
2. **Infrastructure Consolidation** - Merge deployment configs
3. **Modern Python Setup** - Implement pyproject.toml

### Low Priority
1. **Clean Architecture** - Implement domain-driven design
2. **Development Tools** - Add automation and utilities

## Next Steps
1. Review the full proposal in docs/architecture/IMPROVED_FOLDER_STRUCTURE_PROPOSAL.md
2. Run ./scripts/migrate_folder_structure.sh for automated migration
3. Update team documentation and workflows
4. Train team on new structure

EOF

echo ""
echo -e "${GREEN}✅ Analysis complete!${NC}"
echo -e "${BLUE}📋 Report saved to STRUCTURE_RECOMMENDATIONS.md${NC}"
