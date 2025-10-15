#!/usr/bin/env bash
# Build script for Render deployment

echo "🚀 Starting OCRD Extractor build process..."

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p uploads
mkdir -p exports

echo "✅ Build completed successfully!"
