# Visual Testing Quick Start

## TL;DR

```bash
# Run complete test suite (15 seconds)
./run_tests.sh

# Or manually:
python3 test_orchestrator.py
python3 test_analyzer.py
```

## What This Does

1. **Detects** your display server (X11 or Wayland)
2. **Launches** the main overlay program
3. **Spawns** test agents that capture your screen every 0.5 seconds
4. **Analyzes** the visual output for red overlay presence and movement
5. **Converts** visual data to numerical metrics (RGB stats, coverage %, movement)
6. **Kills** the program after exactly 15 seconds
7. **Generates** JSON results and actionable feedback

## Two Parallel Agents

### X11 Agent (`test_agent_x11.py`)
- Uses `scrot` or ImageMagick's `import`
- Captures full screen via X11 protocol
- Detects red overlay pixels (R>200, R>G+50, R>B+50)
- Tracks movement of red overlay center of mass

### Wayland Agent (`test_agent_wayland.py`)
- Uses `grim`, `gnome-screenshot`, or `spectacle`
- Captures via Wayland screen capture APIs
- Same detection algorithm as X11
- Runs in parallel with X11 agent if both displays available

## Output

### Terminal Output
Real-time progress during test:
```
[X11 Test Agent] Sample 1 @ 0.5s: Red=YES Coverage=10.42%
[X11 Test Agent] Sample 2 @ 1.0s: Red=YES Coverage=11.23%
[Wayland Test Agent] Sample 1 @ 0.5s: Red=YES Coverage=10.38%
```

### JSON Files
- `test_results_x11.json`: Complete X11 test data
- `test_results_wayland.json`: Complete Wayland test data

### Analysis Report
```
X11 TEST RESULTS SUMMARY
========================================
Total samples: 30
Red overlay detected: 28 / 30 samples (93.3%)
Average red coverage: 10.52%
Average movement: 25.1 pixels
Animation detected: YES
```

### Feedback for Coding Agents
```
FEEDBACK FOR CODING AGENTS
========================================
  ✓ X11: Good overlay detection rate
  ✓ X11: Animation working correctly
  ✓ Wayland: Good overlay detection rate
  ✓ Wayland: Animation working correctly
```

## Metrics Explained

### Detection Rate
Percentage of frames where red overlay was found
- **>80%**: Good - overlay rendering consistently
- **50-80%**: Moderate - some frames missing overlay
- **<50%**: Poor - overlay not rendering correctly

### Coverage Percentage
Percentage of screen covered by red overlay
- **5-20%**: Expected for moving rectangle
- **<5%**: Overlay too small or barely visible
- **>50%**: Overlay too large or covering whole screen

### Movement
Pixels moved per frame
- **>5px average**: Animation working
- **<5px average**: Static or not moving enough
- **0px**: No animation detected

### Animation Detection
Boolean flag indicating if overlay is moving
- Based on average movement >5 pixels
- Verifies the moving rectangle test is working

## Install Missing Tools

```bash
# For X11 testing (choose one)
sudo apt install scrot              # Recommended
sudo apt install imagemagick        # Alternative

# For Wayland testing (choose one based on desktop environment)
sudo apt install grim               # For wlroots (Sway, etc.)
sudo apt install gnome-screenshot   # For GNOME
sudo apt install spectacle          # For KDE Plasma
```

## How It Works

### Process Lifecycle
```
1. test_orchestrator.py starts
2. Detects X11/Wayland
3. Launches main.py (overlay program)
4. Gets PID of main.py
5. Spawns test agents with PID
6. Agents capture screen every 0.5s for 15s
7. Agents analyze each capture
8. After 15s, agents kill main.py
9. Agents save JSON results
10. test_analyzer.py reads results
11. Analyzer prints summary and feedback
```

### Visual → Numerical Conversion

**Visual**: Red rectangle moving across screen
↓
**Capture**: Screenshot as RGB array [1080, 1920, 3]
↓
**Detect**: Find pixels where R>200 && R>G+50 && R>B+50
↓
**Calculate**: 
- Count red pixels → coverage %
- Find center of mass → position
- Compare to previous frame → movement
↓
**Output**: JSON with numerical metrics

## Closed Feedback Loop

The system closes the feedback loop for coding agents:

1. **Visual Output**: Program renders overlay on screen
2. **Automated Capture**: Test agent screenshots every 0.5s
3. **Numerical Data**: Convert pixels to metrics
4. **Analysis**: Compare against expected behavior
5. **Feedback**: Generate pass/fail with specific issues
6. **Automated Cleanup**: Kill program after 15s

This enables **fully automated testing** without human observation.

## Expected Timeline

```
T+0s:   Orchestrator starts
T+0.5s: Main program starts
T+2.5s: Test agents start (after 2s initialization delay)
T+3s:   First screen capture
T+3.5s: Second capture
...
T+17.5s: Last capture (15 seconds elapsed)
T+17.5s: Agents kill main program
T+18s:  JSON results saved
T+18s:  Analyzer runs and prints report
```

## Troubleshooting

**No capture tool found**
```bash
./run_tests.sh  # Shows which tools are missing
# Then install appropriate tool (see above)
```

**Agent can't capture screen**
- Check permissions for screen recording
- Wayland: May need to grant permission in Settings
- Try running with different capture tool

**Main program crashes before 15s**
- Run `python3 main.py` separately to see error
- Check dependencies are installed
- Verify X11/Wayland compatibility

**No results generated**
- Check if test agents actually ran
- Look for error messages in terminal output
- Verify JSON files were created: `ls -lh test_results_*.json`

## Next Steps After Testing

1. **View detailed results**: `cat test_results_x11.json | jq`
2. **Check specific frames**: Look at `samples` array in JSON
3. **Compare platforms**: Look at comparative analysis section
4. **Fix issues**: Use feedback to identify problems
5. **Re-test**: Run `./run_tests.sh` again after fixes

## Integration with Development

```bash
# Quick test during development
./run_tests.sh

# If tests pass, commit changes
git add .
git commit -m "Fix overlay rendering"

# If tests fail, fix and re-test
# Feedback tells you exactly what's wrong
```

## Success Criteria

✓ Red overlay detected in >80% of frames
✓ Animation working (average movement >5px)  
✓ Coverage between 5-50%
✓ Similar behavior on X11 and Wayland
✓ No crashes during 15 second test

If all criteria met → Overlay is working correctly!
