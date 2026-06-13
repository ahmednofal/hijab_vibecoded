# Hijab by Copilot – Copilot Instructions

## Project Overview
Real-time person detection and screen overlay. Captures the screen, detects people via MediaPipe semantic segmentation, and renders a red semi-transparent overlay on them.

**Windows-only version.**

## Architecture: Three-Stage Multiprocessing Pipeline
```
[capture_worker] → capture_queue(maxsize=2) → [segmentation_worker*] → mask_queue(maxsize=2) → [Overlay/main thread]
                                                                                             ↑ overlay_id_queue / hide_signal_queue
```
- **Capture** and **Segmentation** run as `multiprocessing.Process` (daemon). **Overlay** runs on the main thread (Qt requirement).
- `maxsize=2` is intentional — frames drop under load to keep latency low, not a bug.
- ⚠️ **Segmentation is currently bypassed** (import commented out in `main.py`). App runs in test mode: animated red rectangle instead of real masks.

## Windows-Specific Files
| Concern | File |
|---|---|
| Entry point | `main.py` |
| Screen capture | `capture_windows.py` — MSS + OpenCV debug video |
| Overlay | `overlay_windows.py` — PyQt6, `TransparentOverlayWindows` with `WDA_EXCLUDEFROMCAPTURE` |
| Segmentation | `segmentation.py` — MediaPipe (commented out in main.py) |
| System check | `check_windows.py` |
| Launch | `run_windows.bat` |
| Setup | `setup_windows.bat` |

## Critical Design: Feedback Loop Prevention
The overlay window must **not** appear in captured frames.
- **Windows**: `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` — OS-level exclusion from BitBlt-based captures (MSS). No manual black-out needed.

## Key Gotchas
- **MSS indexing:** `sct.monitors[0]` = all monitors combined. Individual monitors start at `[1]`. `capture_windows.py` adjusts with `mon_idx = monitor_index + 1`.
- **Test mode paint:** `overlay_windows.py paintEvent` has `if True: # Test mode` — the real mask rendering block (`if self.current_mask is not None`) is below it but never reached.
- **Queue drop policy:** Frames/masks silently dropped when queue full — intentional for low latency.

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

## Re-enabling Segmentation (`main.py`)
1. Uncomment `from segmentation import segmentation_worker`.
2. Instantiate `self.segmentation_process = Process(target=segmentation_worker, args=(capture_queue, mask_queue, stop_event))`.
3. Call `self.segmentation_process.start()` after the capture process.
4. In the overlay, read from `mask_queue` instead of `capture_queue`.
5. In `overlay_windows.py paintEvent`, change `if True: # Test mode` to `if self.current_mask is None:`.
