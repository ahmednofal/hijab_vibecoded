# Hijab by Copilot – Copilot Instructions

## Project Overview
Real-time person detection and screen overlay. Captures the screen, detects people via MediaPipe semantic segmentation, and renders a red semi-transparent overlay on everything **except** the detected person (background is covered, person remains visible).

**Windows-only version.**

## Architecture: Three-Stage Multiprocessing Pipeline
```
[capture_worker] → capture_queue(maxsize=2) → [segmentation_worker] → mask_queue(maxsize=2) → [Overlay/main thread]
                                                                                          ↑ overlay_id_queue
```
- **Capture** and **Segmentation** run as `multiprocessing.Process` (daemon). **Overlay** runs on the main thread (Qt requirement).
- `maxsize=2` is intentional — frames drop under load to keep latency low, not a bug.
- Segmentation is fully wired: `main.py` starts all three stages.

## Windows-Specific Files
| Concern | File |
|---|---|
| Entry point | `main.py` |
| Screen capture | `capture_windows.py` — MSS + OpenCV debug video to `capture_debug.avi` |
| Overlay | `overlay_windows.py` — PyQt6, `TransparentOverlayWindows` with `WDA_EXCLUDEFROMCAPTURE` |
| Segmentation | `segmentation.py` — MediaPipe SelfieSegmentation, inverted mask (covers background) |
| System check | `check_windows.py` |
| Launch | `run_windows.bat` |
| Setup | `setup_windows.bat` |

## Critical Design: Feedback Loop Prevention
The overlay window must **not** appear in captured frames.
- **Windows**: `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` — OS-level exclusion from BitBlt-based captures (MSS). No manual black-out needed.

## Key Gotchas
- **MSS indexing:** `sct.monitors[0]` = all monitors combined. Individual monitors start at `[1]`. `capture_windows.py` adjusts with `mon_idx = monitor_index + 1`.
- **Mask inversion:** The overlay covers background (`mask <= 0`) not the person — the person is left visible.
- **Queue drop policy:** Frames/masks silently dropped when queue full — intentional for low latency.
- **Auto-close timer:** Overlay auto-closes after 30 seconds (debug recording duration).

## Developer Workflows

### Windows (in VM or native)
```cmd
setup_windows.bat       # create venv + install deps (first time)
run_windows.bat         # activate venv + run main.py
python check_windows.py # pre-flight check
```

### Boot Windows VM from Linux
```bash
./run_qemu_vm_installed.sh          # boots Windows 11 VM
# Access project in VM via \\10.0.2.4\qemu  (or map as Z:)
```
