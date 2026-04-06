# Hijab by Copilot – Copilot Instructions

## Session Continuity — Read This First
**At the start of every session:** read [`SESSION.md`](../SESSION.md) — it has the current state, what was done last session, and the prioritised backlog.  
**Before ending every session:** update the "Current State" table and "Last Session" section in `SESSION.md`.

---

## Project Overview
Real-time person detection and screen overlay. Captures the screen, detects people via MediaPipe semantic segmentation, and renders a red semi-transparent overlay on them.

**Current focus: Windows port.** Linux support exists but is deprioritised.

## Architecture: Three-Stage Multiprocessing Pipeline
```
[capture_worker] → capture_queue(maxsize=2) → [segmentation_worker*] → mask_queue(maxsize=2) → [Overlay/main thread]
                                                                                                 ↑ overlay_id_queue / hide_signal_queue
```
- **Capture** and **Segmentation** run as `multiprocessing.Process` (daemon). **Overlay** runs on the main thread (Qt requirement).
- `maxsize=2` is intentional — frames drop under load to keep latency low, not a bug.
- ⚠️ **Segmentation is currently bypassed** (import commented out in `main.py`). App runs in test mode: animated red rectangle instead of real masks.

## Windows-Specific Files (Active)
| Concern | File |
|---|---|
| Screen capture | `capture_windows.py` — MSS, ~50-60 FPS |
| Overlay | `overlay_windows.py` — PyQt6, `TransparentOverlayWindows` |
| System check | `check_windows.py` |
| Launch | `run_windows.bat` |
| Setup | `setup_windows.bat` |

`main.py` selects at runtime via `IS_WINDOWS = platform.system() == 'Windows'`.

## Critical Design: Feedback Loop Prevention
The overlay window must **not** appear in captured frames.
- **Windows**: overlay `HWND` (from `winId()`) sent via `overlay_id_queue` → `capture_worker_windows` calls `capture_windows_exclude_window()` using `win32gui.GetWindowRect` to black out that region.
- **X11** (Linux): `XComposite` exclusion using `winId()`.
- **Wayland** (Linux): background pre-captured before overlay opens; static display.

## Key Gotchas
- **MSS indexing:** `sct.monitors[0]` = all monitors combined. Individual monitors start at `[1]`. `capture_windows.py` adjusts with `mon_idx = monitor_index + 1`.
- **HWND timing:** capture worker waits up to 5 s for HWND. If overlay is slow to start, it falls back to no-exclusion mode.
- **Test mode paint:** `overlay_windows.py paintEvent` has `if True: # Test mode` — the real mask rendering block (`if self.current_mask is not None`) is already written below it but never reached.
- **`overlay_gtk.py` vs `overlay_gtk3.py`:** `overlay_gtk3.py` is the active Wayland path; `overlay_gtk.py` is an older draft.

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

### Verify overlay correctness
```bash
python verify_v2.py   # taps capture_queue; validates movement & no feedback loop (preferred)
python verify.py      # external PyQt6 screen capture verifier
```

## Re-enabling Segmentation (`main.py`)
1. Uncomment `from segmentation import segmentation_worker`.
2. Instantiate `self.segmentation_process = Process(target=segmentation_worker, args=(capture_queue, mask_queue, stop_event))`.
3. Call `self.segmentation_process.start()` after the capture process.
4. In the overlay, read from `mask_queue` instead of `capture_queue`.
5. In `overlay_windows.py paintEvent`, change `if True: # Test mode` to `if self.current_mask is None:`.
