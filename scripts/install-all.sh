#!/bin/bash
# Install all KITPOS agents with optional dependencies

set -e

echo "================================================"
echo "KITPOS Agent Installation Script"
echo "================================================"

# Detect if running from monorepo root
if [ ! -f "README.md" ] || [ ! -d "agents" ]; then
    echo "❌ Error: Must run from KITPOS monorepo root directory"
    exit 1
fi

# Install Maverick Terminal Agent
echo ""
echo "📦 Installing Maverick Terminal Agent..."
cd agents/maverick-terminal-agent
pip install -e '.[ocr]'
cd ../../

# Install KIT Dashboard Agent
echo ""
echo "📦 Installing KIT Dashboard Agent..."
cd agents/kit-dashboard-agent
pip install -e '.[ocr,browser]'
cd ../../

echo ""
echo "================================================"
echo "✅ Installation complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "  1. Set environment variables (see docs/SETUP.md)"
echo "  2. Test agents:"
echo "     maverick --help"
echo "     kit --help"
echo ""
