#!/bin/bash

# Test breaking change detection with a real example

echo "🧪 Testing Breaking Change Detection"
echo "====================================="

# Create a backup of the original schema
cp contracts/schemas/avro/article-ingest-v1.avsc /tmp/article-ingest-v1.avsc.backup

echo "📄 Original schema analysis (should be clean):"
python scripts/contracts/diff_schema.py --file contracts/schemas/avro/article-ingest-v1.avsc --base-ref origin/main

echo ""
echo "🔧 Simulating breaking change: removing required field 'article_id'..."

# Create a modified version with breaking change
python3 -c "
import json
with open('contracts/schemas/avro/article-ingest-v1.avsc', 'r') as f:
    schema = json.load(f)

# Remove the article_id field (this is a breaking change)
schema['fields'] = [f for f in schema['fields'] if f['name'] != 'article_id']

with open('contracts/schemas/avro/article-ingest-v1.avsc', 'w') as f:
    json.dump(schema, f, indent=2)
"

echo "📄 Modified schema analysis (should detect breaking change):"
if python scripts/contracts/diff_schema.py --file contracts/schemas/avro/article-ingest-v1.avsc --base-ref origin/main; then
    echo "❌ ERROR: Breaking change not detected!"
    exit_code=1
else
    echo "✅ SUCCESS: Breaking change correctly detected!"
    exit_code=0
fi

echo ""
echo "🔄 Restoring original schema..."
cp /tmp/article-ingest-v1.avsc.backup contracts/schemas/avro/article-ingest-v1.avsc

echo "📄 Restored schema analysis (should be clean again):"
python scripts/contracts/diff_schema.py --file contracts/schemas/avro/article-ingest-v1.avsc --base-ref origin/main

echo ""
if [ $exit_code -eq 0 ]; then
    echo "🎉 Breaking change detection test PASSED!"
else
    echo "❌ Breaking change detection test FAILED!"
fi

exit $exit_code
