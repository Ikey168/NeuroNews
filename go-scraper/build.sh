#!/bin/bash

# NeuroNews Go Scraper Build Script

echo "🏗️ Building NeuroNews Go Async Scraper..."

# Navigate to scraper directory
cd "$(dirname "$0")"

# Initialize and tidy modules
echo "📦 Setting up Go modules..."
go mod tidy

# Run syntax check
echo "🔍 Checking syntax..."
go fmt ./...

# Run basic tests
echo "🧪 Running tests..."
go test -v

# Build the binary
echo "🔨 Building binary..."
go build -o neuronews-scraper

# Check if build was successful
if [ -f "neuronews-scraper" ]; then
    echo "✅ Build successful! Binary created: neuronews-scraper"
    echo "📏 Binary size: $(du -h neuronews-scraper | cut -f1)"
    echo ""
    echo "🚀 Usage examples:"
    echo "  ./neuronews-scraper -help"
    echo "  ./neuronews-scraper -test"
    echo "  ./neuronews-scraper -sources \"BBC,CNN\""
    echo "  ./neuronews-scraper -js -verbose"
else
    echo "❌ Build failed!"
    exit 1
fi

echo "🎉 Build complete!"
