# Testing Architecture

## Overview

This project now has a comprehensive testing framework that separates concerns into specialized agents:

1. **CV Monitor Agent** - Computer vision-based testing that converts visual output to numerical metrics
2. **X11 Agent** - X11-specific overlay implementation
3. **Wayland Agent** - Wayland-specific overlay implementation

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                   Test Orchestrator                      │
│              (run_integrated_test.py)                    │
│                                                           │
│  - Detects display server (X11/Wayland)                 │
│  - Starts appropriate overlay backend                    │
│  - Launches CV monitor process                           │
│  - Collects and analyzes results                         │
└────────────┬────────────────────────────┬────────────────┘
             │                            │
             │                            │
    ┌────────▼─────────┐         ┌────────▼──────────┐
    │  Overlay Process │         │  CV Monitor       │
    │                  │         │  (Separate Task)  │
    │  - X11 Backend   │         │                   │
    │  - Wayland Backend│        │  Runs for 15s     │
    │  - Qt Backend    │         │  (configurable)   │
    │  - GTK Backend   │         │                   │
    │                  │         │  Not in draw loop │
    │  Draws moving    │         │                   │
    │  red rectangle   │         │  Captures frames  │
    └──────────────────┘         │  Analyzes metrics │
                                 │  Detects movement │
                                 │  Checks feedback  │
                                 └───────────────────┘
```

## Key Components

### 1. CV Monitor (`test_cv_monitor.py`)

**Purpose**: Monitor visual output and convert it to numerical metrics for automated testing.

**Key Features**:
- Runs as **separate process/thread** - not held by drawing loop
- Invoked on execution start
- Runs for configurable duration (default: 15 seconds)
- Uses computer vision techniques to extract metrics:
  - Red pixel detection (color-based)
  - Rectangle detection (contour analysis)
  - Movement tracking (displacement over time)
  - Feedback loop detection (multiple rectangles)
  - Visual quality checks (edge detection, intensity)

**Metrics Extracted**:
```python
{
  'red_pixel_count': int,         # How many red pixels
  'red_percentage': float,        # % of screen that's red
  'rectangle_count': int,         # Number of rectangles detected
  'primary_rectangle': {          # Main rectangle properties
    'x': int, 'y': int,
    'width': int, 'height': int,
    'area': int,
    'aspect_ratio': float,
    'solidity': float
  },
  'frame_mean_intensity': float,  # Overall brightness
  'frame_std_intensity': float,   # Contrast
  'edge_percentage': float        # Amount of real content
}
```

**Usage**:
```bash
# Standalone mode
python test_cv_monitor.py --duration 15 --output results.json -v

# As part of integrated test (automatic)
python run_integrated_test.py
```

### 2. X11 Agent (`overlay_x11.py`)

**Purpose**: X11-specific transparent overlay implementation.

**Optimizations**:
- Uses `Qt.WindowType.X11BypassWindowManagerHint` for direct window control
- Sets X11 window properties via Xlib:
  - `_NET_WM_WINDOW_TYPE_UTILITY` - less intrusive window type
  - `_NET_WM_STATE_SKIP_TASKBAR` - don't show in taskbar
  - `_NET_WM_STATE_SKIP_PAGER` - don't show in workspace switcher
  - `_NET_WM_STATE_ABOVE` - always on top
- Full input passthrough using Qt flags

**Requirements**:
- X11 display server
- PyQt6
- python-xlib (for X11 properties)

**Usage**:
```bash
# Auto-selected on X11 systems
OVERLAY_BACKEND=x11 python main.py

# Force X11 backend
python run_integrated_test.py --backend x11
```

### 3. Wayland Agent (`overlay_wayland.py`)

**Purpose**: Wayland-specific transparent overlay implementation.

**Optimizations**:
- Uses GTK Layer Shell when available (Wayland-native approach)
- Sets layer to `OVERLAY` for proper z-ordering
- Configures anchors to cover entire screen
- Input passthrough via `KeyboardMode.NONE`
- Falls back to standard GTK window if layer-shell unavailable

**Requirements**:
- Wayland display server
- GTK 3
- GtkLayerShell (optional but recommended)

**Installation**:
```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1
```

**Usage**:
```bash
# Auto-selected on Wayland systems
OVERLAY_BACKEND=wayland python main.py

# Force Wayland backend
python run_integrated_test.py --backend wayland
```

## Testing Workflow

### Quick Test (15 seconds)

```bash
python run_integrated_test.py
```

This will:
1. Auto-detect your display server (X11 or Wayland)
2. Start the appropriate overlay backend
3. Run CV monitor for 15 seconds
4. Analyze results and report pass/fail

### Extended Test (30 seconds)

```bash
python run_integrated_test.py --duration 30
```

### Force Specific Backend

```bash
# Test X11 implementation
python run_integrated_test.py --backend x11

# Test Wayland implementation
python run_integrated_test.py --backend wayland

# Test Qt implementation (works on both)
python run_integrated_test.py --backend qt

# Test GTK implementation (works on both)
python run_integrated_test.py --backend gtk
```

### Verbose Mode with Detailed Output

```bash
python run_integrated_test.py --duration 20 --output detailed.json -v
```

## Test Criteria

The integrated test checks for:

### 1. Movement Detection ✓
- **Metric**: Average pixel displacement of red rectangle
- **Expected**: 10-50 pixels per frame (at ~100ms sampling)
- **Pass Criteria**: Movement detected with reasonable velocity
- **Failure Reasons**:
  - `insufficient_frames` - Not enough data
  - `insufficient_rectangles` - Rectangle not detected
  - `no_positive_displacement` - Rectangle not moving

### 2. No Feedback Loop ✓
- **Metric**: Maximum number of rectangles detected simultaneously
- **Expected**: Exactly 1 rectangle
- **Pass Criteria**: `max_rectangle_count == 1`
- **Indicates**: Overlay is not capturing itself (no recursive rendering)

### 3. Visual Output Present ✓
- **Metrics**: 
  - Edge detection percentage (real content vs black screen)
  - Mean intensity (brightness level)
- **Expected**: 
  - Edge percentage > 1.0%
  - Mean intensity > 10.0
- **Pass Criteria**: Real desktop content visible (not black/grey screen)

### 4. Red Overlay Detected ✓
- **Metric**: Percentage of frames with red pixels
- **Expected**: > 50% of frames
- **Pass Criteria**: Red overlay consistently visible
- **Indicates**: Overlay is actually rendering

## Output Format

### Terminal Output

```
======================================================================
INTEGRATED OVERLAY TEST WITH CV MONITORING
======================================================================
Display Server: x11
Overlay Backend: x11
Test Duration: 15.0s

[TestRunner] Starting overlay process...
[TestRunner] Waiting for overlay to initialize...
[TestRunner] Starting CV monitor (15s)...
[TestRunner] Collecting results...

======================================================================
ANALYZING RESULTS
======================================================================

Tests Run: 4
Tests Passed: 4
Tests Failed: 0
Pass Rate: 100.0%

✓ PASS - movement
       Avg displacement: 25.43 px
✓ PASS - no_feedback_loop
       Max rectangles: 1
✓ PASS - visual_output
       Edge detection: 12.34%
       Avg intensity: 128.5
✓ PASS - red_overlay
       Detection rate: 98.5%
       Frames with red: 147/149

======================================================================
Detailed results saved to: test_results.json

✓✓✓ ALL TESTS PASSED ✓✓✓
```

### JSON Output (test_results.json)

```json
{
  "test_config": {
    "duration": 15.0,
    "backend": "x11",
    "display_server": "x11",
    "verbose": false
  },
  "cv_monitoring": {
    "duration": 15.02,
    "total_frames": 149,
    "frame_metrics": [...],
    "movement_analysis": {
      "movement_detected": true,
      "avg_displacement": 25.43,
      "std_displacement": 2.15,
      "displacement_count": 148
    },
    "feedback_analysis": {
      "feedback_detected": false,
      "max_rectangle_count": 1,
      "avg_rectangle_count": 1.0
    }
  },
  "analysis": {
    "tests": {
      "movement": {"pass": true, ...},
      "no_feedback_loop": {"pass": true, ...},
      "visual_output": {"pass": true, ...},
      "red_overlay": {"pass": true, ...}
    },
    "overall_pass": true,
    "tests_passed": ["movement", "no_feedback_loop", "visual_output", "red_overlay"],
    "tests_failed": [],
    "pass_rate": 1.0
  }
}
```

## Agent Responsibilities

### CV Monitor Agent
- **NOT** part of the drawing loop
- Runs independently in separate process
- Samples screen at ~10 FPS (100ms intervals)
- Analyzes each frame with computer vision
- Tracks metrics over time
- Outputs numerical results

### X11 Agent
- Handles X11-specific window creation
- Sets X11 window manager hints
- Manages X11 transparency and compositing
- Optimizes for X11 performance

### Wayland Agent
- Handles Wayland-specific surface creation
- Uses layer-shell protocol when available
- Manages Wayland transparency
- Falls back gracefully if layer-shell unavailable
- Optimizes for Wayland compositors

## Troubleshooting

### CV Monitor shows "no_positive_displacement"
- Rectangle might not be moving
- Check overlay is actually running
- Verify rectangle animation logic

### Feedback loop detected (max_rectangles > 1)
- Overlay is capturing itself
- Check window exclusion in capture logic
- Verify overlay window ID is being sent correctly

### Visual output test fails
- Screen capture might be broken
- Check PyQt6 installation
- Verify permissions for screen capture

### Backend fails to start
- Check dependencies are installed
- Verify you're on the correct display server
- Try forcing a different backend

## Development Tips

### Adding New Metrics

Edit `test_cv_monitor.py`:

```python
def analyze_frame(self, frame: np.ndarray, frame_num: int) -> Dict:
    # Add your custom metric here
    metrics['my_custom_metric'] = calculate_something(frame)
    return metrics
```

### Adding New Test Criteria

Edit `run_integrated_test.py`:

```python
def analyze_results(cv_results: Dict) -> Dict:
    # Add your custom test
    analysis['tests']['my_custom_test'] = {
        'pass': check_condition(cv_results),
        'details': {...}
    }
    return analysis
```

### Creating New Overlay Backend

1. Create `overlay_newbackend.py`
2. Implement `run_overlay_newbackend()` function
3. Import in `main.py`
4. Add to backend selection logic
5. Test with `python run_integrated_test.py --backend newbackend`

## Performance Notes

- CV Monitor samples at 10 FPS to reduce CPU load
- Overlay runs at 30 FPS for smooth animation
- Total test overhead: ~15-20% CPU during monitoring
- Memory usage: ~100-200 MB additional for CV processing

## Future Enhancements

- [ ] GPU-accelerated CV processing
- [ ] Real-time streaming of metrics to web dashboard
- [ ] Support for multiple monitors simultaneously
- [ ] Automated performance regression testing
- [ ] Integration with CI/CD pipelines
- [ ] Comparison mode (before/after changes)
