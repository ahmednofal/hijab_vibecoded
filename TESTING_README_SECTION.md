## Automated Testing with Computer Vision

This project includes a comprehensive testing framework that uses computer vision to validate GUI correctness.

### Quick Start

Run the automated test:
```bash
python run_integrated_test.py
```

This will automatically detect your display server, start the appropriate overlay backend, and run computer vision monitoring for 15 seconds.

### Architecture

The testing system uses **3 specialized agents**:

1. **CV Monitor Agent** (`test_cv_monitor.py`) - Converts visual output to numerical metrics
   - Runs as separate process (not in drawing loop)
   - Uses OpenCV for color detection, contour analysis, movement tracking
   - Outputs JSON results with numerical metrics

2. **X11 Agent** (`overlay_x11.py`) - X11-optimized overlay implementation
   - Native X11 window properties via Xlib
   - Bypass window manager for direct control
   - Auto-selected on X11 systems

3. **Wayland Agent** (`overlay_wayland.py`) - Wayland-optimized overlay implementation
   - GTK Layer Shell integration
   - Native Wayland compositor support
   - Auto-selected on Wayland systems

### What Gets Tested

✓ **Movement** - Red rectangle moves across screen (displacement tracking)  
✓ **No Feedback Loop** - Overlay doesn't capture itself  
✓ **Visual Output** - Real desktop content visible (not black screen)  
✓ **Red Overlay** - Red overlay is rendered and visible  

### Example Output

```
✓✓✓ ALL TESTS PASSED ✓✓✓

✓ PASS - movement (avg: 25.43 px)
✓ PASS - no_feedback_loop (max: 1)
✓ PASS - visual_output (edges: 12.34%)
✓ PASS - red_overlay (rate: 98.5%)
```

### Documentation

- **Quick Start**: [QUICK_START_TESTING.md](QUICK_START_TESTING.md)
- **Architecture**: [TESTING_ARCHITECTURE.md](TESTING_ARCHITECTURE.md)
- **Implementation**: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
- **Diagrams**: [AGENT_DIAGRAM.txt](AGENT_DIAGRAM.txt)

### Common Commands

```bash
# Basic test (15 seconds)
python run_integrated_test.py

# Extended test (30 seconds)
python run_integrated_test.py --duration 30

# Test specific backend
python run_integrated_test.py --backend x11
python run_integrated_test.py --backend wayland

# Verbose mode with JSON output
python run_integrated_test.py -v --output results.json
```

### Dependencies

```bash
# Python packages
pip install PyQt6 opencv-python scikit-image numpy

# For Wayland support (optional)
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1
```
