#!/bin/bash

# Build script for type generation and validation - Issue #369
# Regenerates types from contracts and validates compilation

set -e

echo "🔄 Auto-generating types from contracts..."
echo "========================================"

# Step 1: Clean and regenerate types
echo "✅ Step 1: Regenerating types from schemas"
python scripts/contracts/codegen.py --clean
echo "   ✓ Types regenerated successfully"

# Step 2: Validate Python syntax of generated files
echo ""
echo "✅ Step 2: Validating generated Python syntax"
generated_files=$(find services/generated -name "*.py" -type f)
file_count=$(echo "$generated_files" | wc -l)
echo "   Checking $file_count generated Python files..."

for file in $generated_files; do
    echo "   Validating $(basename "$file")..."
    if ! python -m py_compile "$file"; then
        echo "   ❌ Syntax error in generated file: $file"
        exit 1
    fi
done
echo "   ✓ All generated files have valid Python syntax"

# Step 3: Test imports work correctly
echo ""
echo "✅ Step 3: Testing generated module imports"
python -c "
import sys
sys.path.append('services')
try:
    # Test importing generated modules
    import generated
    import generated.avro
    import generated.jsonschema
    
    # Test specific model imports
    from generated.avro.article_ingest_v1_models import Articleingest
    from generated.jsonschema.ask_request_v1_models import AskRequest
    
    print('   ✓ All generated modules import successfully')
    
    # Test model instantiation
    article = Articleingest(
        article_id='test-123',
        source_id='test-source',
        url='https://example.com',
        language='en',
        published_at='2025-08-28T10:00:00Z',
        ingested_at='2025-08-28T10:01:00Z'
    )
    print('   ✓ Avro model instantiation works')
    
    ask_req = AskRequest(
        question='What is the latest news?'
    )
    print('   ✓ JSON Schema model instantiation works')
    
except ImportError as e:
    print(f'   ❌ Import error: {e}')
    sys.exit(1)
except Exception as e:
    print(f'   ❌ Model instantiation error: {e}')
    sys.exit(1)
"

# Step 4: Validate type safety with mypy (if available)
echo ""
echo "✅ Step 4: Type checking with mypy (optional)"
if command -v mypy &> /dev/null; then
    echo "   Running mypy type checking..."
    if mypy services/generated --ignore-missing-imports --no-error-summary; then
        echo "   ✓ Type checking passed"
    else
        echo "   ⚠️  Type checking found issues (non-blocking)"
    fi
else
    echo "   ⚠️  mypy not available, skipping type checking"
fi

# Step 5: Check for hand-rolled DTOs that should be replaced
echo ""
echo "✅ Step 5: Checking for hand-rolled DTOs"
python -c "
import ast
import os
from pathlib import Path

def find_hand_rolled_dtos():
    '''Find potential hand-rolled DTOs that duplicate generated types.'''
    services_dir = Path('services')
    dto_patterns = ['class.*Request', 'class.*Response', 'class.*Event', 'class.*Model']
    
    hand_rolled = []
    for py_file in services_dir.rglob('*.py'):
        if 'generated' in str(py_file):
            continue  # Skip generated files
            
        try:
            with open(py_file, 'r') as f:
                content = f.read()
                
            # Look for class definitions that might be DTOs
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_name = node.name
                    # Check if this looks like a DTO
                    if any(pattern.replace('.*', '') in class_name for pattern in ['Request', 'Response', 'Event', 'Model']):
                        # Check if it has dataclass decorator or inherits from BaseModel
                        is_dto = False
                        for decorator in node.decorator_list:
                            if isinstance(decorator, ast.Name) and decorator.id == 'dataclass':
                                is_dto = True
                            elif isinstance(decorator, ast.Attribute) and decorator.attr == 'dataclass':
                                is_dto = True
                        
                        for base in node.bases:
                            if isinstance(base, ast.Name) and base.id == 'BaseModel':
                                is_dto = True
                        
                        if is_dto:
                            hand_rolled.append(f'{py_file}:{node.lineno} - {class_name}')
        except:
            continue  # Skip files that can't be parsed
    
    return hand_rolled

dtos = find_hand_rolled_dtos()
if dtos:
    print(f'   ⚠️  Found {len(dtos)} potential hand-rolled DTOs:')
    for dto in dtos[:10]:  # Show first 10
        print(f'      {dto}')
    if len(dtos) > 10:
        print(f'      ... and {len(dtos) - 10} more')
    print('   💡 Consider replacing these with generated types from contracts')
else:
    print('   ✓ No obvious hand-rolled DTOs found')
"

# Step 6: Generate usage documentation
echo ""
echo "✅ Step 6: Generating usage documentation"
cat > services/generated/README.md << 'EOF'
# Generated Types Documentation

This directory contains auto-generated Python types from data contract schemas.

## 🚨 IMPORTANT: DO NOT EDIT MANUALLY

These files are automatically generated from contract schemas. Any manual changes will be lost when types are regenerated.

## Usage

### Importing Types

```python
# Import all generated types
import generated

# Import specific schema types
from generated.avro.article_ingest_v1_models import Articleingest
from generated.jsonschema.ask_request_v1_models import AskRequest

# Import by category
from generated.avro import *  # All Avro-generated types
from generated.jsonschema import *  # All JSON Schema-generated types
```

### Using Generated Models

#### Avro Models

```python
from generated.avro.article_ingest_v1_models import Articleingest

# Create from dictionary (e.g., from Kafka consumer)
article_data = {
    "article_id": "123",
    "source_id": "bbc",
    "url": "https://bbc.com/news/123",
    "language": "en",
    "published_at": "2025-08-28T10:00:00Z",
    "ingested_at": "2025-08-28T10:01:00Z"
}

article = Articleingest.from_avro_dict(article_data)

# Convert back to Avro format
avro_dict = article.to_avro_dict()
```

#### JSON Schema Models

```python
from generated.jsonschema.ask_request_v1_models import AskRequest

# Create request model
request = AskRequest(
    question="What is the latest news?",
    k=10,
    provider="openai"
)

# Convert to JSON
json_dict = request.to_json_dict()
```

## Regenerating Types

To regenerate types after schema changes:

```bash
# Regenerate all types
python scripts/contracts/codegen.py --clean

# Or use the build script
./build_types.sh
```

## Generated Structure

```
services/generated/
├── __init__.py                 # Root imports
├── avro/                      # Types from Avro schemas
│   ├── __init__.py
│   ├── article-ingest-v1_models.py
│   └── ...
└── jsonschema/                # Types from JSON schemas
    ├── __init__.py
    ├── ask-request-v1_models.py
    └── ...
```

## Integration with Services

Replace hand-rolled DTOs with generated types:

```python
# OLD: Hand-rolled DTO
class ArticleRequest:
    def __init__(self, article_id: str, source_id: str):
        self.article_id = article_id
        self.source_id = source_id

# NEW: Generated type
from generated.avro.article_ingest_v1_models import Articleingest
```

This ensures your code stays in sync with the contract schemas and prevents drift.
EOF

echo "   ✓ Generated README.md with usage instructions"

# Summary
echo ""
echo "🎉 SUCCESS: Type generation and validation completed!"
echo "================================================="
echo ""
echo "📋 Summary:"
echo "   ✓ Types regenerated from all contract schemas"
echo "   ✓ All generated files compile successfully"
echo "   ✓ Module imports work correctly"
echo "   ✓ Model instantiation validated"
echo "   ✓ Type checking completed (if mypy available)"
echo "   ✓ Hand-rolled DTO analysis performed"
echo "   ✓ Usage documentation generated"
echo ""
echo "📄 Generated Files:"
find services/generated -name "*.py" -type f | wc -l | xargs echo "   Python files:"
echo "   Documentation: services/generated/README.md"
echo ""
echo "💡 Next Steps:"
echo "   1. Import generated types in your services"
echo "   2. Replace hand-rolled DTOs with generated types"
echo "   3. Add this build script to your CI/CD pipeline"
echo ""
echo "✅ Issue 369 DoD requirements satisfied!"
