#!/bin/bash
set -e

# Update system packages
sudo apt-get update
sudo apt-get -y upgrade

# Install Python and pip if not present
if ! command -v python3 &> /dev/null; then
    sudo apt-get install -y python3
fi

if ! command -v pip3 &> /dev/null; then
    sudo apt-get install -y python3-pip
fi

# Clean up previous deployment if exists
if [ -d "/home/ubuntu/neuronews" ]; then
    rm -rf /home/ubuntu/neuronews/*
fi

# Create deployment directory if it doesn't exist
mkdir -p /home/ubuntu/neuronews