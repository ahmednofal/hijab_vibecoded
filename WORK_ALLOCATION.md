# Work Allocation - Agent Responsibilities

## Overview

The work has been split into **3 specialized agents** plus **1 orchestrator**:

```
┌─────────────────────────────────────────────────┐
│          Test Orchestrator                      │
│      (run_integrated_test.py)                   │
│                                                  │
│  Coordinates all agents                         │
│  Analyzes combined results                      │
│  Reports pass/fail                              │
└───────────┬─────────────┬──────────┬────────────┘
            │             │          │
   ┌────────▼─┐    ┌──────▼──┐  ┌───▼────────┐
   │ CV Agent │    │X11 Agent│  │Wayl. Agent │
   └──────────┘    └─────────┘  └────────────┘
```

## Agent 1: CV Monitor (Computer Vision Testing)

**File**: `test_cv_monitor.py`

**Responsibility**: Convert visual GUI output to numerical metrics for automated testing.

**Key Features**:
- ✓ Runs as **separate task** (not held by drawing loop)
- ✓ Invoked on execution start
- ✓ Runs for **15 seconds** (configurable)
- ✓ Uses computer vision techniques for monitoring
- ✓ Outputs numerical, machine-readable metrics

**What It Monitors**:
1. **Red pixel detection** - Color-based detection of overlay
2. **Rectangle detection** - Contour analysis to find shapes
3. **Movement tracking** - Displacement over time
4. **Feedback loop detection** - Multiple rectangles = capturing self
5. **Visual quality** - Edge detection, intensity (ensures real content, not black screen)

**Metrics Produced**:
```python
{
  'red_pixel_count': int,
  'red_percentage': float,
  'rectangle_count': int,
  'primary_rectangle': {x, y, width, height, area},
  'frame_mean_intensity': float,
  'edge_percentage': float,
  # ... and more
}
```

**How It Works**:
1. Captures screen every 100ms (~10 FPS)
2. Analyzes each frame with OpenCV
3. Extracts numerical features
4. Tracks metrics over time
5. Performs movement analysis
6. Detects patterns (e.g., feedback loops)
7. Outputs JSON results

**Independence**:
- Runs in **separate process** from overlay
- No interference with drawing loop
- Can be started/stopped independently
- Configurable duration (default: 15s)

## Agent 2: X11 Specialist

**File**: `overlay_x11.py`

**Responsibility**: Transparent overlay implementation optimized for X11 display server.

**Specializations**:
1. **X11 Window Manager Bypass**
   - Uses `Qt.WindowType.X11BypassWindowManagerHint`
   - Direct window control without WM interference

2. **X11 Window Properties** (via Xlib)
   - Sets `_NET_WM_WINDOW_TYPE_UTILITY`
   - Configures `_NET_WM_STATE_SKIP_TASKBAR`
   - Configures `_NET_WM_STATE_SKIP_PAGER`
   - Configures `_NET_WM_STATE_ABOVE`

3. **X11-Specific Optimizations**
   - Native X11 transparency
   - X11 compositing integration
   - Efficient window updates

**When Used**:
- Auto-selected on X11 systems
- Can be forced: `OVERLAY_BACKEND=x11 python main.py`
- Or via test: `python run_integrated_test.py --backend x11`

**Dependencies**:
- PyQt6
- python-xlib
- X11 display server

## Agent 3: Wayland Specialist

**File**: `overlay_wayland.py`

**Responsibility**: Transparent overlay implementation optimized for Wayland display server.

**Specializations**:
1. **GTK Layer Shell** (Wayland-native)
   - Uses `GtkLayerShell` protocol when available
   - Sets layer to `OVERLAY`
   - Configures screen anchors (top, bottom, left, right)
   - Keyboard mode: `NONE` (input passthrough)

2. **Wayland-Specific Features**
   - Native Wayland surface management
   - Proper z-ordering via layer protocol
   - Compositor-friendly approach

3. **Graceful Fallback**
   - If layer-shell unavailable, uses standard GTK
   - Still maintains transparency and input passthrough

**When Used**:
- Auto-selected on Wayland systems
- Can be forced: `OVERLAY_BACKEND=wayland python main.py`
- Or via test: `python run_integrated_test.py --backend wayland`

**Dependencies**:
- GTK 3 (required)
- GtkLayerShell (optional but recommended)
- Wayland display server

**Installation**:
```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1
```

## Orchestrator: Integrated Test Runner

**File**: `run_integrated_test.py`

**Responsibility**: Coordinate all agents and produce final test results.

**What It Does**:
1. **Detect Environment**
   - Identifies display server (X11/Wayland)
   - Selects appropriate overlay backend

2. **Launch Agents**
   - Starts overlay process (X11 or Wayland agent)
   - Starts CV monitor in separate process
   - Manages inter-process communication

3. **Collect Results**
   - Gathers metrics from CV monitor
   - Receives status from overlay

4. **Analyze Results**
   - Runs analysis on collected metrics
   - Determines pass/fail for each test
   - Calculates overall pass rate

5. **Report Results**
   - Terminal output (human-readable)
   - JSON output (machine-readable)
   - Exit code (0 = pass, 1 = fail)

## Communication Flow

```
Orchestrator
    │
    ├─► Start Overlay Process
    │   ├─► X11 Agent (if X11)
    │   └─► Wayland Agent (if Wayland)
    │
    ├─► Start CV Monitor Process
    │   ├─► Capture screen @ 10 FPS
    │   ├─► Analyze each frame
    │   └─► Send metrics back
    │
    ├─► Wait for duration (15s)
    │
    ├─► Collect all results
    │
    └─► Analyze & Report
        ├─► Movement test
        ├─► Feedback loop test
        ├─► Visual output test
        ├─► Red overlay test
        └─► Final verdict (PASS/FAIL)
```

## Task Separation

### Drawing Loop (Overlay Agents)
```python
# Runs at 30 FPS
def update():
    # Update animation
    rect_x += 5
    
    # Trigger repaint
    self.update()
    
    # Schedule next update
    timer.start(33ms)  # 30 FPS
```

### Monitoring Loop (CV Agent)
```python
# Runs at 10 FPS, SEPARATE process
def monitor():
    for duration:
        frame = capture_screen()  # 100ms interval
        metrics = analyze(frame)
        results.append(metrics)
        sleep(0.1)
    
    return analyze_all(results)
```

**Key Point**: Monitoring is **NOT** called from drawing loop!

## Usage Examples

### Run with Auto-Detection
```bash
python run_integrated_test.py
```
→ Detects X11/Wayland, picks appropriate agent

### Force X11 Agent
```bash
python run_integrated_test.py --backend x11
```
→ Uses X11 specialist, tests X11 optimizations

### Force Wayland Agent
```bash
python run_integrated_test.py --backend wayland
```
→ Uses Wayland specialist, tests layer-shell

### Extended Test (30s)
```bash
python run_integrated_test.py --duration 30
```
→ Runs all agents for 30 seconds

### Verbose + Save Results
```bash
python run_integrated_test.py -v --output results.json
```
→ Detailed logging + JSON output

## Why This Architecture?

### Separation of Concerns
- **CV Agent**: Testing/monitoring only
- **X11 Agent**: X11 display optimization only
- **Wayland Agent**: Wayland display optimization only
- **Orchestrator**: Coordination only

### Independence
- CV monitor doesn't affect overlay performance
- Overlay agents can be developed separately
- Easy to add new agents (e.g., macOS, Windows)

### Testability
- Each agent can be tested individually
- Clear pass/fail criteria (numerical metrics)
- Reproducible results
- CI/CD integration ready

### Maintainability
- Each agent has single responsibility
- Changes to X11 don't affect Wayland
- CV metrics can evolve independently
- Easy to debug specific issues

## Files Summary

| File | Lines | Purpose | Agent |
|------|-------|---------|-------|
| `test_cv_monitor.py` | ~380 | CV monitoring & metrics | CV Agent |
| `overlay_x11.py` | ~250 | X11 overlay implementation | X11 Agent |
| `overlay_wayland.py` | ~260 | Wayland overlay implementation | Wayland Agent |
| `run_integrated_test.py` | ~350 | Test orchestration & analysis | Orchestrator |
| `TESTING_ARCHITECTURE.md` | - | Detailed documentation | - |
| `QUICK_START_TESTING.md` | - | Quick reference guide | - |

**Total**: ~1,240 lines of new testing infrastructure

## Next Steps

1. **Run the test**:
   ```bash
   python run_integrated_test.py
   ```

2. **Check which agent is used**:
   ```bash
   echo $XDG_SESSION_TYPE  # Shows x11 or wayland
   ```

3. **Test both agents**:
   ```bash
   python run_integrated_test.py --backend x11
   python run_integrated_test.py --backend wayland
   ```

4. **Review results**:
   ```bash
   cat test_results.json | jq '.analysis'
   ```

5. **Extend as needed**:
   - Add new CV metrics in `test_cv_monitor.py`
   - Optimize X11 in `overlay_x11.py`
   - Optimize Wayland in `overlay_wayland.py`
   - Add new tests in `run_integrated_test.py`
