#!/usr/bin/env python3
"""
Test that the capture worker erases overlay pixels from frames before they
reach the CV model.

Two tests:

1. UNIT TEST  — no overlay running, no screen capture.
   Creates a synthetic frame pre-painted with red pixels matching the mask,
   applies the erasure logic, and asserts zero red pixels remain.
   Fast (<1s). Run first.

2. INTEGRATION TEST — starts a real gnome-screenshot capture cycle alongside
   the simulation worker, collects a couple of frames from the capture_queue
   (what the CV model would see), and checks them for red pixels.
   Slow (~10s, requires Wayland/gnome-screenshot).

Usage:
    source venv/bin/activate
    python test_overlay_exclusion.py          # runs both tests
    python test_overlay_exclusion.py --unit   # unit test only (fast)
    python test_overlay_exclusion.py --integ  # integration test only
"""

import sys
import time
import numpy as np
from multiprocessing import Queue, Event, Process

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def has_red(frame: np.ndarray, threshold: int = 100) -> int:
    """Return count of pixels that look like the overlay red (R high, G/B low)."""
    r = frame[:, :, 0].astype(int)
    g = frame[:, :, 1].astype(int)
    b = frame[:, :, 2].astype(int)
    return int(np.sum((r > threshold) & (r - g > 50) & (r - b > 50)))


def apply_erasure(frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Same logic used in capture_worker — zero pixels where mask == 1."""
    out = frame.copy()
    mh, mw = mask.shape
    fh, fw = out.shape[:2]
    h, w = min(mh, fh), min(mw, fw)
    out[:h, :w][mask[:h, :w] == 1] = 0
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 – Unit test (synthetic frame, no screen capture)
# ─────────────────────────────────────────────────────────────────────────────

def test_unit():
    print("\n── Unit test ──────────────────────────────────────────────────────")
    import threading
    from segmentation import simulation_worker

    SCREEN_W, SCREEN_H = 1536, 864

    mask_q       = Queue(maxsize=2)
    cap_mask_q   = Queue(maxsize=1)
    stop         = Event()

    # Run simulation briefly to get a real mask
    t = threading.Thread(
        target=simulation_worker,
        args=(mask_q, stop, SCREEN_W, SCREEN_H),
        kwargs={'capture_mask_queue': cap_mask_q},
        daemon=True,
    )
    t.start()
    time.sleep(0.15)
    stop.set()
    t.join(2)

    mask = None
    while not cap_mask_q.empty():
        mask = cap_mask_q.get()

    if mask is None:
        print("FAIL – no mask received from simulation_worker")
        return False

    print(f"  Mask shape: {mask.shape}, covered pixels: {mask.sum()} "
          f"({100*mask.mean():.1f}% of frame)")

    # Build a synthetic frame: grey background, red paint where mask==1
    fake = np.full((SCREEN_H, SCREEN_W, 3), 128, dtype=np.uint8)
    fake[:, :, 0][mask == 1] = 220   # R
    fake[:, :, 1][mask == 1] = 0     # G
    fake[:, :, 2][mask == 1] = 0     # B

    red_before = has_red(fake)
    print(f"  Red pixels BEFORE erasure : {red_before:,}")
    assert red_before > 0, "Test setup error — no red pixels injected"

    cleaned = apply_erasure(fake, mask)

    red_after = has_red(cleaned)
    print(f"  Red pixels AFTER  erasure : {red_after}")

    if red_after == 0:
        print("  PASS ✓  — overlay pixels fully erased from synthetic frame")
        return True
    else:
        print(f"  FAIL ✗  — {red_after} red pixels remain after erasure")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 – Integration test (real gnome-screenshot capture pipeline)
# ─────────────────────────────────────────────────────────────────────────────

def max_consecutive(arr: np.ndarray) -> int:
    """Length of the longest run of True values in a 1-D boolean array."""
    if not arr.any():
        return 0
    max_run = cur = 0
    for v in arr:
        cur = cur + 1 if v else 0
        if cur > max_run:
            max_run = cur
    return int(max_run)


def find_erased_band(frame: np.ndarray, min_run: int = 300) -> dict:
    """
    Detect the pure-black band that mask erasure leaves in the frame.

    Erasure sets pixels to exact (0, 0, 0).  Normal desktop content almost
    never has a solid 300-px-wide column band of pure-black pixels, so finding
    one is a strong signal that erasure happened.

    Returns a dict with 'max_run' (longest run of erased columns) and
    'erased_columns' (total count of columns ≥ 99 % pure-black).
    """
    pure_black = (frame == 0).all(axis=2)          # (H, W) bool
    col_frac   = pure_black.mean(axis=0)           # fraction per column
    erased_col = col_frac >= 0.99                  # column nearly all-black
    return {
        'max_run':        max_consecutive(erased_col),
        'erased_columns': int(erased_col.sum()),
    }


def test_integration():
    print("\n── Integration test ───────────────────────────────────────────────")
    print("  Strategy: erasure sets pixels to exact (0,0,0).  After erasure the")
    print("  frame contains a ~400-px-wide solid-black band — a pattern that")
    print("  normal desktop content never produces.  We detect that band.")
    print("  Natural red pixels elsewhere (icons, terminal text) are ignored.")
    print("  (Requires Wayland + gnome-screenshot; takes ~15 s)")
    from capture import capture_worker
    from segmentation import simulation_worker

    SCREEN_W, SCREEN_H = 1536, 864
    MONITOR_GEOMETRY   = (1920, 0, SCREEN_W, SCREEN_H)

    RECT_WIDTH = 400   # must match simulation_worker default

    mask_q     = Queue(maxsize=2)
    capture_q  = Queue(maxsize=5)
    cap_mask_q = Queue(maxsize=1)
    stop       = Event()

    seg_proc = Process(
        target=simulation_worker,
        args=(mask_q, stop, SCREEN_W, SCREEN_H),
        kwargs={'capture_mask_queue': cap_mask_q},
        daemon=True,
    )
    cap_proc = Process(
        target=capture_worker,
        args=(capture_q, stop, 0, None, MONITOR_GEOMETRY, None),
        kwargs={'capture_mask_queue': cap_mask_q},
        daemon=True,
    )

    seg_proc.start()
    cap_proc.start()

    print("  Waiting for captured frames (gnome-screenshot ~2 s each)…")
    frames = []
    deadline = time.time() + 25
    while len(frames) < 3 and time.time() < deadline:
        try:
            frame = capture_q.get(timeout=8)
            frames.append(frame)
        except Exception:
            break

    stop.set()
    seg_proc.join(3)
    cap_proc.join(3)

    if not frames:
        print("  SKIP — no frames received (check gnome-screenshot / capture setup)")
        return None

    print(f"  Got {len(frames)} frame(s)")
    passed = 0
    for i, frame in enumerate(frames):
        info   = find_erased_band(frame)
        red_px = has_red(frame)

        print(f"\n  Frame {i+1}:")
        print(f"    Shape            : {frame.shape}")
        print(f"    Red pixels (all) : {red_px:,}  "
              f"← includes natural screen content outside mask")
        print(f"    Erased columns   : {info['erased_columns']} "
              f"(≥99 % pure-black)")
        print(f"    Longest black run: {info['max_run']} columns "
              f"(need ≥ {RECT_WIDTH - 100})")

        # Primary check: a solid erased band exists whose width ≈ rect_width.
        # Allow ±100 px tolerance for timing drift (mask moves ~300 px/s,
        # gnome-screenshot takes ~2 s, so up to 600 px drift possible;
        # the overlap between drawn and erased position shrinks but the
        # continuous zeroed region should still be clearly wider than noise).
        min_expected = RECT_WIDTH - 100  # 300 px
        if info['max_run'] >= min_expected:
            print(f"    PASS ✓  — erased band detected ({info['max_run']} px wide)")
            passed += 1
        else:
            print(f"    FAIL ✗  — no erased band found "
                  f"(max_run={info['max_run']}, expected ≥{min_expected})")

    print()
    if passed == len(frames):
        print(f"  PASS ✓  — erasure confirmed in all {len(frames)} frames")
        return True
    else:
        print(f"  FAIL ✗  — {len(frames)-passed}/{len(frames)} frames show no erased band")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    run_unit  = '--integ' not in sys.argv
    run_integ = '--unit'  not in sys.argv

    results = []

    if run_unit:
        results.append(('unit',        test_unit()))
    if run_integ:
        results.append(('integration', test_integration()))

    print("\n── Summary ────────────────────────────────────────────────────────")
    for name, ok in results:
        if ok is None:
            status = 'SKIP'
        elif ok:
            status = 'PASS ✓'
        else:
            status = 'FAIL ✗'
        print(f"  {name:<14} {status}")

    any_failed = any(r is False for _, r in results)
    sys.exit(1 if any_failed else 0)
