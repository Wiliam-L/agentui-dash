#!/usr/bin/env bash
# Build the AgentUI Dash wheel package.
# Usage: bash build_mcp/build.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Building AgentUI Dash ==="
cd "$ROOT"

# Clean previous build
rm -rf dist/ build/ *.egg-info

# Build
uv build

# Show results
echo ""
echo "=== Build complete ==="
ls -lh dist/
echo ""
WHEEL=$(ls dist/*.whl | head -1)
echo "To install:"
echo "  uv pip install --system \"$WHEEL\""
echo ""
echo "After installation, run:"
echo "  ui              # Start the Streamlit dashboard"
echo "  agentui-mcp     # Start the MCP server"
