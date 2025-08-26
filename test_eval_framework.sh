#!/bin/bash
# Test script for Issue #235 Evaluation Framework

echo "Testing Issue #235: Evaluation Framework"
echo "======================================="

# Test 1: Basic help
echo "Test 1: CLI Help"
python evals/run_eval.py --help

echo -e "\nTest 2: Sample baseline evaluation"
python evals/run_eval.py --config baseline --sample 3

echo -e "\nTest 3: Configuration comparison (sample)"
python evals/run_eval.py --compare --sample 2

echo -e "\nTest 4: Custom configuration"
python evals/run_eval.py --custom --k 3 --fusion true --rerank false --sample 2

echo -e "\nAll tests completed!"
