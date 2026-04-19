#!/bin/bash
# Kitee Build Script for POSIX (Linux, macOS, etc.)
# Usage: ./build.sh [--onefile] [--clean]

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    exit 1
fi

PYTHON_CMD="python3"

# Check if Nuitka is installed
if ! $PYTHON_CMD -m pip show nuitka &> /dev/null; then
    echo -e "${YELLOW}Installing Nuitka...${NC}"
    $PYTHON_CMD -m pip install Nuitka
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Failed to install Nuitka${NC}"
        exit 1
    fi
fi

echo ""
echo "============================================================"
echo "Kitee Build Script (POSIX)"
echo "============================================================"
echo "Python:"
$PYTHON_CMD --version
echo ""
echo "Executing: $PYTHON_CMD build.py $@"
echo ""

$PYTHON_CMD build.py "$@"
BUILD_RESULT=$?

echo ""
if [ $BUILD_RESULT -eq 0 ]; then
    echo -e "${GREEN}Build completed successfully!${NC}"
    exit 0
else
    echo -e "${RED}Build failed!${NC}"
    exit 1
fi
