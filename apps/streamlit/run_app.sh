#!/bin/bash
# Launch script for NeuroNews Streamlit App
# Issue #234: Ask the News UI

echo "Starting NeuroNews Streamlit App..."
echo "Issue #234: Ask the News debug UI"
echo

# Check if we're in the right directory
if [ ! -f "Home.py" ]; then
    echo "Error: Please run this script from the apps/streamlit directory"
    exit 1
fi

# Install requirements if needed
if [ -f "requirements.txt" ]; then
    echo "Installing Streamlit requirements..."
    pip install -r requirements.txt
fi

echo "Launching Streamlit app..."
echo "Navigate to: http://localhost:8501"
echo "Then go to: 'Ask the News' page"
echo

streamlit run Home.py
