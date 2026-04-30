#!/bin/bash

# Exit on error
set -e

echo "🚀 Starting Moms Verdict..."

# Check if .env exists, if not copy from example
if [ ! -f .env ]; then
    echo "📄 Creating .env from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your OPENROUTER_API_KEY"
fi

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is not installed. Please install Python 3.10+."
    exit 1
fi

# Check for venv, create if doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install requirements
echo "⬇️  Installing dependencies..."
pip install -r requirements.txt -q

# Set PYTHONPATH
export PYTHONPATH=$PWD

echo "✅ Setup complete! Starting server..."
echo "🌐 Open your browser to: http://localhost:8000"

# Start the FastAPI server
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
