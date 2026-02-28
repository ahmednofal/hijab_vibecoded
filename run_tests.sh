#!/bin/bash
# Quick test runner - runs the complete testing system

set -e

echo "=========================================="
echo "Hijab by Copilot - Visual Testing System"
echo "=========================================="
echo ""

# Check if we're in the right directory
if [ ! -f "main.py" ]; then
    echo "Error: main.py not found. Run this script from the project root."
    exit 1
fi

# Check Python version
echo "Checking Python version..."
python3 --version

# Check dependencies
echo ""
echo "Checking screen capture tools..."
if command -v scrot &> /dev/null; then
    echo "  ✓ scrot found (X11 capture)"
else
    echo "  ✗ scrot not found (install: sudo apt install scrot)"
fi

if command -v grim &> /dev/null; then
    echo "  ✓ grim found (Wayland capture)"
elif command -v gnome-screenshot &> /dev/null; then
    echo "  ✓ gnome-screenshot found (Wayland capture)"
elif command -v spectacle &> /dev/null; then
    echo "  ✓ spectacle found (Wayland capture)"
else
    echo "  ✗ No Wayland capture tool found"
fi

# Check display server
echo ""
echo "Display server info:"
echo "  XDG_SESSION_TYPE: ${XDG_SESSION_TYPE:-not set}"
echo "  DISPLAY: ${DISPLAY:-not set}"
echo "  WAYLAND_DISPLAY: ${WAYLAND_DISPLAY:-not set}"

# Clean up old results
echo ""
echo "Cleaning up old test results..."
rm -f test_results_*.json

# Run orchestrator
echo ""
echo "=========================================="
echo "Starting Test Orchestrator"
echo "=========================================="
echo ""
python3 test_orchestrator.py

# Check if results were generated
echo ""
echo "=========================================="
echo "Checking Test Results"
echo "=========================================="
echo ""

if [ -f "test_results_x11.json" ]; then
    echo "✓ X11 results generated"
fi

if [ -f "test_results_wayland.json" ]; then
    echo "✓ Wayland results generated"
fi

# Run analyzer
echo ""
echo "=========================================="
echo "Analyzing Test Results"
echo "=========================================="
echo ""
python3 test_analyzer.py

echo ""
echo "=========================================="
echo "Test Complete"
echo "=========================================="
