#!/bin/sh
set -e

REPO="https://github.com/0xkaushal/mcp-rc-audit.git"
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "  ⚡ Installing mcp-rc-audit..."
echo ""

# Try uvx/pipx/pip in order of preference
if command -v uvx >/dev/null 2>&1; then
    uv tool install "git+${REPO}"
    echo ""
    echo "${GREEN}✓ Installed via uv. Run: mcp-rc-audit scan ./your-server/${NC}"

elif command -v pipx >/dev/null 2>&1; then
    pipx install "git+${REPO}"
    echo ""
    echo "${GREEN}✓ Installed via pipx. Run: mcp-rc-audit scan ./your-server/${NC}"

elif command -v pip >/dev/null 2>&1; then
    pip install "git+${REPO}"
    echo ""
    echo "${GREEN}✓ Installed via pip. Run: mcp-rc-audit scan ./your-server/${NC}"

else
    echo "${RED}✗ No Python package manager found (uv, pipx, or pip).${NC}"
    echo "  Install uv first: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo ""
echo "  Usage:"
echo "    mcp-rc-audit scan ./path/to/your/mcp-server/"
echo "    mcp-rc-audit probe http://localhost:8000/mcp"
echo ""
