#!/usr/bin/env python3

import re

# Read the file
with open('/workspaces/NeuroNews/dbt/neuro_news/models/marts/_marts__schema.yml', 'r') as f:
    content = f.read()

# Replace timestamp data types
content = re.sub(r'(\s+)data_type: timestamp(\s)', r'\1data_type: "timestamp with time zone"\2', content)

# Write back to file
with open('/workspaces/NeuroNews/dbt/neuro_news/models/marts/_marts__schema.yml', 'w') as f:
    f.write(content)

print("Updated timestamp data types to 'timestamp with time zone'")
