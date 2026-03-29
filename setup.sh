#!/bin/bash
set -e

echo "=== Setting up Auto Flow AI ==="

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browser (Chromium only)
playwright install chromium

echo ""
echo "Setup complete! Run the script with:"
echo "  python auto_flow.py --image path/to/photo.jpg"
echo "  python auto_flow.py --image photo.jpg --prompt 'camera slowly zooms in'"
