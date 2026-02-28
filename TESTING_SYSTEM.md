# Visual Testing System

## Overview

This testing system provides automated visual validation of the overlay application by capturing screen output, converting it to numerical metrics, and providing actionable feedback. The system runs separate test agents in parallel for X11 and Wayland display servers.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Test Orchestrator                         │
│  - Detects display server (X11/Wayland)                     │
│  - Launches main program                                     │
│  - Spawns appropriate test agents                           │
└─────────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Main Program │  │ X11 Agent    │  │ Wayland Agent│
│ (main.py)    │  │              │  │              │
│              │  │ Captures     │  │ Captures     │
│ Renders      │  │ screen using │  │ screen using │
│ red overlay  │  │ scrot/import │  │ grim/gnome-  │
│ rectangle    │  │              │  │ screenshot   │
└──────────────┘  └──────────────┘  └──────────────┘
        ▲                 │                 │
        │                 │                 │
        │    ┌────────────┴─────────────────┘
        │    ▼
        │  Kills after 15 seconds
        └────────────────────┐
                             │
                             ▼
                    ┌────────────────┐
                    │ Test Analyzer  │
                    │ - Reads results│
                    │ - Compares     │
                    │ - Generates    │
                    │   feedback     │
                    └────────────────┘
```

## Components

### 1. Test Orchestrator (`test_orchestrator.py`)
- **Purpose**: Main coordinator that launches the program and test agents
- **Responsibilities**:
  - Detect X11/Wayland display servers
  - Check for required capture tools
  - Start main program (`main.py`)
  - Launch appropriate test agents in parallel
  - Monitor execution and collect output
  - Ensure cleanup after tests complete

### 2. X11 Test Agent (`test_agent_x11.py`)
- **Purpose**: Visual testing for X11 display server
- **Capture Tools**: `scrot` or `import` (ImageMagick)
- **Metrics Collected**:
  - Frame RGB statistics (mean, std, min, max)
  - Red overlay detection (pixel count and coverage)
  - Red overlay position and movement
  - Animation detection
- **Duration**: 15 seconds
- **Action**: Sends SIGTERM/SIGKILL to main program after completion

### 3. Wayland Test Agent (`test_agent_wayland.py`)
- **Purpose**: Visual testing for Wayland display server
- **Capture Tools**: `grim`, `gnome-screenshot`, or `spectacle`
- **Metrics Collected**: Same as X11 agent
- **Duration**: 15 seconds
- **Action**: Sends SIGTERM/SIGKILL to main program after completion

### 4. Test Analyzer (`test_analyzer.py`)
- **Purpose**: Post-test analysis and feedback generation
- **Capabilities**:
  - Load and parse JSON test results
  - Display detailed metrics for each agent
  - Compare X11 vs Wayland performance
  - Generate actionable feedback for coding agents

## Numerical Metrics

Each test agent converts visual output to these numerical metrics:

### Frame-Level Metrics
- **timestamp**: Time since test start (seconds)
- **shape**: Frame dimensions [height, width, channels]
- **mean_rgb**: Average RGB values [0-255]
- **std_rgb**: Standard deviation of RGB values
- **min_rgb**: Minimum RGB values
- **max_rgb**: Maximum RGB values

### Overlay Detection Metrics
- **red_overlay_detected**: Boolean (true if >1000 red pixels found)
- **red_coverage_percent**: Percentage of screen covered by red overlay
- **red_pixel_count**: Total number of red pixels detected
- **red_center_x/y**: Center of mass of red overlay
- **red_movement_pixels**: Distance moved from previous frame
- **is_moving**: Boolean (true if moved >10 pixels)

### Summary Statistics
- **total_samples**: Number of frames captured
- **red_detected_count**: Frames with red overlay detected
- **red_detected_percent**: Detection rate percentage
- **avg_red_coverage**: Average coverage percentage
- **max_red_coverage**: Maximum coverage observed
- **avg_movement**: Average pixel movement per frame
- **max_movement**: Maximum movement observed
- **is_animated**: Boolean (true if avg movement >5px)

## Usage

### Quick Start

```bash
# Run complete test suite
python test_orchestrator.py

# After tests complete, analyze results
python test_analyzer.py
```

### Manual Testing

```bash
# Start main program in background
python main.py &
MAIN_PID=$!

# Run X11 test agent
python test_agent_x11.py $MAIN_PID test_results_x11.json

# Or run Wayland test agent
python test_agent_wayland.py $MAIN_PID test_results_wayland.json

# Analyze results
python test_analyzer.py
```

### Environment Variables

- **OVERLAY_BACKEND**: Force specific backend (`x11`, `wayland`, `gtk`, `qt`, or `auto`)
- **DISPLAY**: X11 display server address
- **WAYLAND_DISPLAY**: Wayland display server socket
- **XDG_SESSION_TYPE**: Session type (`x11` or `wayland`)

## Dependencies

### Required Python Packages
```bash
pip install numpy pillow
```

### System Tools

**For X11 Testing:**
- `scrot` (preferred): `sudo apt install scrot`
- OR `import` (ImageMagick): `sudo apt install imagemagick`

**For Wayland Testing:**
- `grim` (wlroots): `sudo apt install grim`
- OR `gnome-screenshot` (GNOME): `sudo apt install gnome-screenshot`
- OR `spectacle` (KDE): `sudo apt install spectacle`

## Output Files

### Test Results JSON
- `test_results_x11.json`: X11 agent results
- `test_results_wayland.json`: Wayland agent results

**Structure:**
```json
{
  "agent": "X11",
  "target_pid": 12345,
  "test_duration": 15,
  "samples_collected": 30,
  "timestamp": "2024-01-01T12:00:00",
  "samples": [
    {
      "timestamp": 0.5,
      "shape": [1080, 1920, 3],
      "mean_rgb": [127.5, 128.2, 126.8],
      "red_overlay_detected": true,
      "red_coverage_percent": 10.42,
      "red_movement_pixels": 25.3,
      "is_moving": true
    }
  ],
  "summary": {
    "total_samples": 30,
    "red_detected_count": 28,
    "red_detected_percent": 93.33,
    "avg_red_coverage": 10.5,
    "is_animated": true
  }
}
```

## Test Scenarios

### Expected Behavior
1. **Overlay Rendering**: Red semi-transparent rectangle should be visible
2. **Animation**: Rectangle should move from left to right across screen
3. **Transparency**: Desktop content should show through overlay
4. **Input Passthrough**: Clicks and keyboard input should pass through overlay

### Success Criteria
- ✓ Red overlay detected in >80% of frames
- ✓ Animation detected (average movement >5 pixels)
- ✓ Coverage between 5-50% (reasonable overlay size)
- ✓ Consistent behavior across X11 and Wayland

### Failure Indicators
- ❌ Detection rate <50%: Overlay not rendering correctly
- ❌ No animation: Movement logic not working
- ❌ Coverage <5%: Overlay too small or not visible
- ❌ Large X11/Wayland discrepancy: Platform-specific bugs

## Feedback Loop for Coding Agents

The test system closes the feedback loop by:

1. **Capturing Visual Output**: Screen captures at 2 Hz (every 0.5s)
2. **Converting to Numerical Data**: RGB statistics, overlay metrics, movement tracking
3. **Generating Actionable Feedback**: Clear pass/fail indicators with specific issues
4. **Automated Termination**: 15-second timeout ensures tests don't run indefinitely

This enables coding agents to:
- Verify overlay functionality without human observation
- Detect regressions in rendering or animation
- Compare cross-platform behavior
- Iterate rapidly with quantitative metrics

## Troubleshooting

### No Capture Tool Found
```bash
# Install for X11
sudo apt install scrot

# Install for Wayland (GNOME)
sudo apt install gnome-screenshot

# Install for Wayland (wlroots/sway)
sudo apt install grim
```

### Permission Denied on Screen Capture
Some Wayland compositors require additional permissions:
```bash
# Check compositor settings for screen sharing permissions
# May need to allow in GNOME Settings > Privacy > Screen Sharing
```

### Test Agent Times Out
If the main program crashes before 15 seconds:
```bash
# Check main program output
python main.py

# Verify dependencies are installed
python -c "from PyQt6.QtWidgets import QApplication"
```

### Inconsistent Results
- Ensure no other overlays are running
- Close unnecessary windows that might obstruct view
- Disable desktop effects temporarily
- Verify correct monitor is selected

## Integration with CI/CD

The testing system can be integrated into automated workflows:

```bash
#!/bin/bash
# CI test script

# Start Xvfb for headless testing (X11)
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99

# Run tests
python test_orchestrator.py

# Check results
python test_analyzer.py > test_summary.txt

# Verify success
if grep -q "❌" test_summary.txt; then
    echo "Tests failed"
    exit 1
fi

echo "Tests passed"
exit 0
```

## Future Enhancements

- [ ] Add video recording of test runs
- [ ] Support for multiple monitor testing
- [ ] Performance metrics (FPS, latency)
- [ ] Regression testing against baseline results
- [ ] HTML report generation with visualizations
- [ ] Real-time test monitoring dashboard

## License

Same as main project.
