# Quick Start - Testing Guide

## TL;DR

Run the automated test:
```bash
python run_integrated_test.py
```

This will automatically:
- Detect your display server (X11/Wayland)
- Start the appropriate overlay
- Monitor for 15 seconds using computer vision
- Output pass/fail with detailed metrics

## What Gets Tested

✓ **Movement** - Red rectangle moves across screen  
✓ **No Feedback Loop** - Overlay doesn't capture itself  
✓ **Visual Output** - Real desktop content visible (not black screen)  
✓ **Red Overlay** - Red overlay is actually rendered  

## Common Commands

### Basic Test (15 seconds)
```bash
python run_integrated_test.py
```

### Extended Test (30 seconds)
```bash
python run_integrated_test.py --duration 30
```

### Test Specific Backend

```bash
# Test X11 implementation
python run_integrated_test.py --backend x11

# Test Wayland implementation  
python run_integrated_test.py --backend wayland
```

### Verbose Mode + Save Results
```bash
python run_integrated_test.py -v --output results.json
```

### Just Run CV Monitor (no overlay)
```bash
python test_cv_monitor.py --duration 15 -v
```

## Understanding Results

### All Tests Pass ✓
```
✓✓✓ ALL TESTS PASSED ✓✓✓
```
Everything works! Overlay is rendering correctly.

### Movement Failed ✗
```
✗ FAIL - movement
     Reason: no_positive_displacement
```
**Problem**: Rectangle not moving  
**Fix**: Check animation logic in overlay

### Feedback Loop Detected ✗
```
✗ FAIL - no_feedback_loop
     Max rectangles: 3
```
**Problem**: Overlay capturing itself  
**Fix**: Check window exclusion in capture.py

### Visual Output Failed ✗
```
✗ FAIL - visual_output
     Edge detection: 0.05%
```
**Problem**: Screen capture returning black/blank  
**Fix**: Check screen capture permissions/setup

### Red Overlay Failed ✗
```
✗ FAIL - red_overlay
     Detection rate: 5.2%
```
**Problem**: Overlay not visible or transparent  
**Fix**: Check compositor support, window transparency

## File Organization

```
hijab_by_copilot/
├── run_integrated_test.py    # Main test orchestrator
├── test_cv_monitor.py         # CV monitoring (separate task)
├── overlay_x11.py             # X11 specialist agent
├── overlay_wayland.py         # Wayland specialist agent
├── overlay.py                 # Qt-based overlay (cross-platform)
├── overlay_gtk3.py            # GTK3-based overlay (cross-platform)
├── main.py                    # Main application
└── TESTING_ARCHITECTURE.md    # Detailed documentation
```

## System Requirements

### For X11:
```bash
pip install PyQt6 opencv-python scikit-image numpy
pip install python-xlib  # For X11 window properties
```

### For Wayland:
```bash
pip install PyQt6 opencv-python scikit-image numpy
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1
```

## Troubleshooting

### "No screen capture backend available"
Install PyQt6:
```bash
pip install PyQt6
```

### "ERROR: This overlay requires X11"
You're trying to run X11 overlay on Wayland. Use auto-detect:
```bash
python run_integrated_test.py  # Auto-detects
```

Or force Wayland backend:
```bash
python run_integrated_test.py --backend wayland
```

### "GtkLayerShell not available"
Optional but recommended for Wayland. Install:
```bash
sudo apt install gir1.2-gtklayershell-0.1
```

### Permission denied for screen capture
Some systems need explicit permission. Check:
```bash
echo $XDG_SESSION_TYPE  # Should show x11 or wayland
```

## Next Steps

- Read [TESTING_ARCHITECTURE.md](TESTING_ARCHITECTURE.md) for detailed info
- Modify CV metrics in `test_cv_monitor.py`
- Add new test criteria in `run_integrated_test.py`
- Optimize backend implementations in `overlay_x11.py` or `overlay_wayland.py`
