# Agent Session Log

> **Agents: Read this at the start of every session. Update the "Current State" and "Last Session" sections before ending.**

---

## Current State *(keep this block accurate at all times)*

| Item | Status |
|---|---|
| Windows port files | ✅ Complete (`capture_windows.py`, `overlay_windows.py`, `check_windows.py`, `setup_windows.bat`, `run_windows.bat`) |
| Test mode (moving red rectangle) | ✅ Working on Windows |
| MediaPipe segmentation | ❌ Bypassed — import commented out in `main.py` |
| Feedback-loop prevention (Windows) | ✅ Implemented via HWND exclusion in `capture_windows_exclude_window()` |
| Windows VM for testing | ✅ QEMU/KVM at `~/.local/share/qemu/windows11-hijab.qcow2` |
| Linux X11 overlay | ⚠️ Deprioritised — not the current focus |
| Wayland overlay | ⚠️ Experimental, deprioritised |

**Active focus:** Windows port — get segmentation fully working end-to-end on Windows.

---

## Last Session *(overwrite each session)*

**Date:** 2026-04-05  
**Work done:**
- Analysed full codebase to understand architecture, platform dual-track pattern, and feedback-loop prevention strategies.
- Created `.github/copilot-instructions.md` with architecture overview and developer workflows.
- Created this `SESSION.md` to enable session continuity.

**Left off at:** No code changes made yet. Project is in test mode with segmentation bypassed.

**Immediate next step:** Re-enable segmentation in `main.py` and wire the Windows pipeline end-to-end.

---

## Backlog / Next Steps *(prioritised)*

1. **Re-enable segmentation on Windows**
   - Uncomment `segmentation_worker` import in `main.py`
   - Instantiate `self.segmentation_process` in `HijabOverlay.start()`
   - Wire: `capture_queue → segmentation_worker → mask_queue`
   - Test MediaPipe loads correctly under Windows Python / QEMU VM

2. **Replace test-rectangle paint with real mask rendering**
   - `overlay_windows.py` `paintEvent` has `if True: # Test mode` block — replace condition with real mask check
   - The mask rendering code below it (`if self.current_mask is not None`) is already written but unreachable

3. **Verify full pipeline on Windows VM**
   - Boot VM: `./run_qemu_vm_installed.sh`
   - Access project: `\\10.0.2.4\qemu`
   - Run: `setup_windows.bat` then `run_windows.bat`
   - Validate with `python verify_v2.py`

4. **Monitor selection on Windows**
   - `select_monitor()` always picks index 0 on Windows — add HP-skip logic matching Linux version

5. **Performance tuning**
   - `segmentation_worker` has a `scale_factor=0.5` param — tune for Windows GPU/CPU

---

## Known Issues / Gotchas

- **MSS 1-based indexing:** `sct.monitors[0]` = all monitors combined; individual monitors start at `[1]`. `capture_windows.py` adjusts with `+1`.
- **Overlay HWND timing:** `capture_worker_windows` waits up to 5 s for HWND via `overlay_hwnd_queue`. If overlay starts slowly the capture worker falls back to no-exclusion mode.
- **Queue drop policy:** All queues are `maxsize=2`. Frames/masks are silently dropped when full — this is intentional for low latency, not a bug.
- **`overlay_gtk.py` vs `overlay_gtk3.py`:** Both exist; `overlay_gtk3.py` is the active Wayland path. `overlay_gtk.py` appears to be an older draft.
- **`verify_v2.py` vs `verify.py`:** `verify_v2.py` taps the internal `capture_queue` (works on Wayland); `verify.py` uses PyQt6 screen capture (X11/Wayland external view). Prefer `verify_v2.py`.
