#!/bin/bash

echo "======================================"
echo "Installing and Running Progress Tracker"
echo "======================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python not found!"
    echo "Please install Python 3.8 or higher"
    exit 1
fi

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Run application
echo ""
echo "======================================"
echo "Starting application..."
echo "Application will be available at:"
echo "http://localhost:5000"
echo "======================================"
echo ""
python app.py