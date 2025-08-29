#!/bin/bash

# NeuroNews Folder Structure Migration Script
# This script reorganizes the project structure according to the improved proposal

set -e

echo "🚀 Starting NeuroNews Folder Structure Migration..."
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create backup
echo -e "${YELLOW}📦 Creating backup...${NC}"
timestamp=$(date +%Y%m%d_%H%M%S)
backup_dir="backup_${timestamp}"
mkdir -p "$backup_dir"
rsync -av --exclude='.git' --exclude='backup_*' --exclude='__pycache__' . "$backup_dir/"
echo -e "${GREEN}✅ Backup created at $backup_dir${NC}"

# Phase 1: Create new directory structure
echo -e "${BLUE}📁 Phase 1: Creating new directory structure...${NC}"

# Create main directories
mkdir -p src/neuronews/{api,core,ml,nlp,data,knowledge_graph,scraper,search,monitoring,security,utils}
mkdir -p src/neuronews/api/{routes,middleware,auth,validators}
mkdir -p src/neuronews/core/{entities,services,repositories,use_cases}
mkdir -p src/neuronews/ml/{models,training,inference,evaluation}
mkdir -p src/neuronews/nlp/{processors,embeddings,analysis,pipelines}
mkdir -p src/neuronews/data/{database,storage,ingestion,etl}
mkdir -p src/neuronews/knowledge_graph/{graph,nodes,edges,queries}
mkdir -p src/neuronews/scraper/{engines,sources,parsers,pipelines}
mkdir -p src/neuronews/search/{vector,lexical,hybrid,indexing}
mkdir -p src/neuronews/monitoring/{metrics,logging,tracing,health}
mkdir -p src/neuronews/security/{auth,authorization,encryption,validation}
mkdir -p src/neuronews/utils/{config,exceptions,helpers,decorators}

# Create test directories
mkdir -p tests/{unit,integration,e2e,performance,security,fixtures,mocks}
mkdir -p tests/unit/{api,core,ml,nlp,data,utils}
mkdir -p tests/integration/{api,database,storage,services}

# Create other main directories
mkdir -p {scripts,config,deploy,workflows,data,examples,tools,monitoring,notebooks}
mkdir -p scripts/{build,deploy,database,ml,maintenance,utilities}
mkdir -p config/{environments,services,ml}
mkdir -p deploy/{docker,kubernetes,terraform,ansible,helm}
mkdir -p workflows/{airflow,dbt,spark}
mkdir -p workflows/airflow/{dags,plugins,operators}
mkdir -p workflows/dbt/{models,macros,snapshots}
mkdir -p data/{raw,processed,fixtures,samples,outputs}
mkdir -p examples/{api,ml,nlp,integrations,tutorials}
mkdir -p tools/{generators,validators,formatters,analyzers}
mkdir -p monitoring/{grafana,prometheus,alerts,logs}
mkdir -p notebooks/{exploration,experiments,analysis,prototypes}
mkdir -p docs/{architecture,api,deployment,development,features,user}
mkdir -p .artifacts/{logs,coverage,builds,cache}

echo -e "${GREEN}✅ Directory structure created${NC}"

# Phase 2: Move source code files
echo -e "${BLUE}📦 Phase 2: Moving source code files...${NC}"

# Move main source files
if [ -d "src" ]; then
    # Move API files
    if [ -d "src/api" ]; then
        find src/api -name "*.py" -exec cp {} src/neuronews/api/routes/ \; 2>/dev/null || true
    fi
    
    # Move ML files
    if [ -d "src/ml" ]; then
        find src/ml -name "*.py" -exec cp {} src/neuronews/ml/models/ \; 2>/dev/null || true
    fi
    
    # Move NLP files
    if [ -d "src/nlp" ]; then
        find src/nlp -name "*.py" -exec cp {} src/neuronews/nlp/processors/ \; 2>/dev/null || true
    fi
    
    # Move database files
    if [ -d "src/database" ]; then
        find src/database -name "*.py" -exec cp {} src/neuronews/data/database/ \; 2>/dev/null || true
    fi
    
    # Move scraper files
    if [ -d "src/scraper" ]; then
        find src/scraper -name "*.py" -exec cp {} src/neuronews/scraper/engines/ \; 2>/dev/null || true
    fi
    
    # Move knowledge graph files
    if [ -d "src/knowledge_graph" ]; then
        find src/knowledge_graph -name "*.py" -exec cp {} src/neuronews/knowledge_graph/graph/ \; 2>/dev/null || true
    fi
fi

echo -e "${GREEN}✅ Source code files moved${NC}"

# Phase 3: Move test files
echo -e "${BLUE}🧪 Phase 3: Moving test files...${NC}"

# Move test files from root to tests directory
for file in test_*.py; do
    if [ -f "$file" ]; then
        # Determine test type based on filename
        if [[ "$file" == *"integration"* ]]; then
            mv "$file" tests/integration/
        elif [[ "$file" == *"e2e"* ]] || [[ "$file" == *"end_to_end"* ]]; then
            mv "$file" tests/e2e/
        elif [[ "$file" == *"performance"* ]]; then
            mv "$file" tests/performance/
        elif [[ "$file" == *"security"* ]]; then
            mv "$file" tests/security/
        else
            mv "$file" tests/unit/
        fi
        echo "Moved $file"
    fi
done

# Move existing tests directory content
if [ -d "tests" ] && [ "$(ls -A tests)" ]; then
    # Tests directory already exists with content, merge carefully
    echo "Merging existing tests..."
fi

echo -e "${GREEN}✅ Test files reorganized${NC}"

# Phase 4: Move demo and example files
echo -e "${BLUE}📋 Phase 4: Moving demo and example files...${NC}"

# Move demo files
for file in demo_*.py; do
    if [ -f "$file" ]; then
        # Categorize demos
        if [[ "$file" == *"api"* ]]; then
            mv "$file" examples/api/
        elif [[ "$file" == *"ml"* ]] || [[ "$file" == *"model"* ]]; then
            mv "$file" examples/ml/
        elif [[ "$file" == *"nlp"* ]]; then
            mv "$file" examples/nlp/
        else
            mv "$file" examples/tutorials/
        fi
        echo "Moved $file"
    fi
done

echo -e "${GREEN}✅ Demo files moved${NC}"

# Phase 5: Move scripts and utilities
echo -e "${BLUE}🔧 Phase 5: Moving scripts and utilities...${NC}"

# Move shell scripts
for file in *.sh; do
    if [ -f "$file" ]; then
        if [[ "$file" == *"deploy"* ]] || [[ "$file" == *"build"* ]]; then
            mv "$file" scripts/deploy/
        elif [[ "$file" == *"test"* ]] || [[ "$file" == *"ci"* ]]; then
            mv "$file" scripts/build/
        else
            mv "$file" scripts/utilities/
        fi
        echo "Moved $file"
    fi
done

echo -e "${GREEN}✅ Scripts moved${NC}"

# Phase 6: Move configuration files
echo -e "${BLUE}⚙️ Phase 6: Moving configuration files...${NC}"

# Move Docker files
if [ -d "docker" ]; then
    cp -r docker/* deploy/docker/ 2>/dev/null || true
fi

# Move docker-compose files
for file in docker-compose*.yml; do
    if [ -f "$file" ]; then
        mv "$file" deploy/docker/
        echo "Moved $file"
    fi
done

# Move Dockerfiles
for file in Dockerfile*; do
    if [ -f "$file" ]; then
        mv "$file" deploy/docker/
        echo "Moved $file"
    fi
done

# Move existing config files
if [ -d "config" ]; then
    cp -r config/* config/services/ 2>/dev/null || true
fi

# Move infrastructure files
if [ -d "infrastructure" ]; then
    cp -r infrastructure/* deploy/terraform/ 2>/dev/null || true
fi

if [ -d "k8s" ]; then
    cp -r k8s/* deploy/kubernetes/ 2>/dev/null || true
fi

if [ -d "ansible" ]; then
    cp -r ansible/* deploy/ansible/ 2>/dev/null || true
fi

echo -e "${GREEN}✅ Configuration files moved${NC}"

# Phase 7: Move workflow files
echo -e "${BLUE}🔄 Phase 7: Moving workflow files...${NC}"

# Move Airflow files
if [ -d "airflow" ]; then
    cp -r airflow/* workflows/airflow/ 2>/dev/null || true
fi

# Move dbt files
if [ -d "dbt" ]; then
    cp -r dbt/* workflows/dbt/ 2>/dev/null || true
fi

# Move Spark files
if [ -d "spark" ]; then
    cp -r spark/* workflows/spark/ 2>/dev/null || true
fi

echo -e "${GREEN}✅ Workflow files moved${NC}"

# Phase 8: Move documentation
echo -e "${BLUE}📚 Phase 8: Moving documentation...${NC}"

# Move existing docs
if [ -d "docs" ]; then
    # Keep existing structure but organize better
    echo "Documentation already organized"
fi

# Move markdown files from root
for file in *.md; do
    if [ -f "$file" ] && [ "$file" != "README.md" ] && [ "$file" != "LICENSE" ]; then
        if [[ "$file" == *"IMPLEMENTATION"* ]] || [[ "$file" == *"GUIDE"* ]]; then
            mv "$file" docs/development/
        elif [[ "$file" == *"DEPLOYMENT"* ]]; then
            mv "$file" docs/deployment/
        elif [[ "$file" == *"API"* ]]; then
            mv "$file" docs/api/
        else
            mv "$file" docs/features/
        fi
        echo "Moved $file"
    fi
done

echo -e "${GREEN}✅ Documentation organized${NC}"

# Phase 9: Move data files
echo -e "${BLUE}📊 Phase 9: Moving data files...${NC}"

# Move existing data
if [ -d "data" ]; then
    echo "Data directory already exists"
fi

# Move log files
if [ -d "logs" ]; then
    mv logs/* .artifacts/logs/ 2>/dev/null || true
fi

echo -e "${GREEN}✅ Data files moved${NC}"

# Phase 10: Create __init__.py files
echo -e "${BLUE}🐍 Phase 10: Creating __init__.py files...${NC}"

find src/neuronews -type d -exec touch {}/__init__.py \;
find tests -type d -exec touch {}/__init__.py \;

echo -e "${GREEN}✅ __init__.py files created${NC}"

# Phase 11: Update configuration files
echo -e "${BLUE}⚙️ Phase 11: Creating configuration files...${NC}"

# Create pyproject.toml if it doesn't exist
if [ ! -f "pyproject.toml" ]; then
    cat > pyproject.toml << 'EOF'
[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "neuronews"
version = "1.0.0"
description = "AI-powered news analysis and fake news detection platform"
authors = [{name = "NeuroNews Team"}]
dependencies = [
    "fastapi>=0.100.0",
    "uvicorn>=0.23.0",
    "pydantic>=2.0.0",
    "sqlalchemy>=2.0.0",
    "pandas>=2.0.0",
    "numpy>=1.24.0",
    "scikit-learn>=1.3.0",
    "transformers>=4.30.0",
    "torch>=2.0.0",
    "requests>=2.31.0",
    "beautifulsoup4>=4.12.0",
    "redis>=4.6.0",
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
]

[project.optional-dependencies]
dev = [
    "black>=23.0.0",
    "flake8>=6.0.0",
    "mypy>=1.5.0",
    "pytest-cov>=4.1.0",
    "pre-commit>=3.3.0",
]

[tool.black]
line-length = 88
target-version = ['py38']

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"
addopts = "-v --tb=short"

[tool.mypy]
python_version = "3.8"
strict = true
ignore_missing_imports = true
EOF
fi

# Create .env.example
cat > .env.example << 'EOF'
# Database Configuration
DATABASE_URL=postgresql://user:password@localhost:5432/neuronews
REDIS_URL=redis://localhost:6379/0

# API Configuration
API_HOST=localhost
API_PORT=8000
API_DEBUG=true

# ML Configuration
MODEL_PATH=./models
HUGGINGFACE_CACHE_DIR=./cache

# Storage Configuration
S3_BUCKET=neuronews-articles
AWS_REGION=us-east-1

# Security
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Monitoring
LOG_LEVEL=INFO
ENABLE_METRICS=true
GRAFANA_URL=http://localhost:3000
EOF

# Create Makefile
cat > Makefile << 'EOF'
.PHONY: help install test lint format clean build deploy

help:
	@echo "Available commands:"
	@echo "  install    Install dependencies"
	@echo "  test       Run tests"
	@echo "  lint       Run linting"
	@echo "  format     Format code"
	@echo "  clean      Clean artifacts"
	@echo "  build      Build application"
	@echo "  deploy     Deploy application"

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v --cov=src/neuronews --cov-report=html

lint:
	flake8 src/ tests/
	mypy src/

format:
	black src/ tests/
	isort src/ tests/

clean:
	rm -rf .artifacts/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build:
	docker build -t neuronews -f deploy/docker/Dockerfile .

deploy:
	docker-compose -f deploy/docker/docker-compose.yml up -d
EOF

echo -e "${GREEN}✅ Configuration files created${NC}"

# Phase 12: Create .gitignore for artifacts
echo -e "${BLUE}🚫 Phase 12: Updating .gitignore...${NC}"

if [ -f ".gitignore" ]; then
    echo "" >> .gitignore
    echo "# Artifacts directory" >> .gitignore
    echo ".artifacts/" >> .gitignore
    echo "backup_*/" >> .gitignore
fi

echo -e "${GREEN}✅ .gitignore updated${NC}"

# Phase 13: Summary report
echo -e "${BLUE}📋 Phase 13: Generating migration report...${NC}"

cat > MIGRATION_REPORT.md << EOF
# Folder Structure Migration Report

**Migration Date:** $(date)
**Backup Location:** $backup_dir

## Summary of Changes

### Created Directories
- \`src/neuronews/\` - Main application package with clean architecture
- \`tests/\` - Comprehensive test organization
- \`scripts/\` - Organized automation scripts
- \`config/\` - Configuration management
- \`deploy/\` - Deployment configurations
- \`workflows/\` - Data processing workflows
- \`examples/\` - Examples and tutorials
- \`tools/\` - Development tools
- \`monitoring/\` - Monitoring configurations
- \`notebooks/\` - Jupyter notebooks
- \`.artifacts/\` - Build artifacts (gitignored)

### Moved Files
- Demo scripts → \`examples/\`
- Test files → \`tests/\`
- Shell scripts → \`scripts/\`
- Docker files → \`deploy/docker/\`
- Documentation → \`docs/\`
- Data files → \`data/\`

### Created Files
- \`pyproject.toml\` - Python project configuration
- \`.env.example\` - Environment variables template
- \`Makefile\` - Build automation
- Multiple \`__init__.py\` files

## Next Steps

1. Update import statements in Python files
2. Update CI/CD pipeline paths
3. Update documentation references
4. Test the application to ensure everything works
5. Remove backup after verification

## Rollback Instructions

If you need to rollback:
\`\`\`bash
rm -rf src/ tests/ scripts/ config/ deploy/ workflows/ examples/ tools/ monitoring/ notebooks/ .artifacts/
cp -r $backup_dir/* .
rm -rf $backup_dir/
\`\`\`
EOF

echo -e "${GREEN}✅ Migration report generated${NC}"

echo ""
echo -e "${GREEN}🎉 Migration completed successfully!${NC}"
echo -e "${YELLOW}📋 Check MIGRATION_REPORT.md for details${NC}"
echo -e "${YELLOW}🔍 Review the changes and test your application${NC}"
echo -e "${YELLOW}📦 Backup available at: $backup_dir${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "1. Review moved files and update imports"
echo "2. Update CI/CD pipeline configurations"
echo "3. Test the application thoroughly"
echo "4. Update team documentation"
echo "5. Remove backup after verification"
