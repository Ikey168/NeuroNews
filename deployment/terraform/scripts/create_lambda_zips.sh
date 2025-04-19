#!/bin/bash
set -e

cd lambda_functions
for func in article_processor article_notifier knowledge_graph_generator; do
    zip "${func}.zip" "${func}.py"
done
