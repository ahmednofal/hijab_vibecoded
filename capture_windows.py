"""Windows-specific screen capture worker using MSS and Win32 API."""

import os
import time
from multiprocessing import Queue, Event
import numpy as np
import mss
import mss.tools

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


def capture_windows(monitor_index: int = 0):
    """Capture screen using MSS (cross-platform but optimized for Windows).
    
    Args:
        monitor_index: Which monitor to capture (0 = all monitors, 1+ = specific monitor)
    
    Returns:
        numpy.ndarray: RGB frame of the captured screen
    """
    try:
        with mss.mss() as sct:
            # Monitor 0 is all monitors combined, 1+ are individual monitors
            # Adjust index since MSS uses 1-based indexing for specific monitors
            mon_idx = monitor_index + 1 if monitor_index >= 0 else 1
            
            # Ensure monitor index is valid
            if mon_idx > len(sct.monitors) - 1:
                mon_idx = 1  # Default to primary monitor
            
            monitor = sct.monitors[mon_idx]
            
            # Capture the screen
            screenshot = sct.grab(monitor)
            
            # Convert to numpy array (BGRA format)
            frame = np.array(screenshot)
            
            # Convert BGRA to RGB
            frame = frame[:, :, [2, 1, 0]].copy()
            
            return frame
    except Exception as e:
        print(f"[Capture] MSS capture error: {e}")
        return None


def capture_worker_windows(output_queue: Queue, stop_event: Event, monitor_index: int = 0, record: bool = False):
    """
    Windows-specific capture worker that continuously captures the screen.
    
    Args:
        output_queue: Queue to put captured frames into
        stop_event: Event to signal when to stop capturing
        monitor_index: Which monitor to capture (0 = primary)
        record: Save debug video to disk
    """
    from logging_setup import setup_logging
    setup_logging("capture")

    print(f"[Capture] Starting Windows capture worker for monitor {monitor_index}")
    
    # Test capture method
    print("[Capture] Testing Windows capture method (MSS)...")
    test_frame = capture_windows(monitor_index)
    if test_frame is not None:
        print(f"[Capture] MSS capture working ({test_frame.shape[1]}x{test_frame.shape[0]})")
    else:
        print("[Capture] ERROR: MSS capture failed!")
        return
    
    frame_count = 0
    start_time = time.time()
    error_count = 0
    max_consecutive_errors = 10
    capture_delay = 0.01  # 10ms delay for ~60fps max

    video_writer = None
    if record:
        video_path = os.path.join(os.getcwd(), 'capture_debug.avi')
        if HAS_CV2:
            print(f"[Capture] Recording debug video to: {video_path}")

    while not stop_event.is_set():
        try:
            # Capture screen
            frame = capture_windows(monitor_index)

            if frame is None:
                raise RuntimeError("Capture returned None")

            frame_count += 1

            # Write every frame to video (only in record mode)
            if record and HAS_CV2:
                if video_writer is None:
                    h, w = frame.shape[:2]
                    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                    video_writer = cv2.VideoWriter(video_path, fourcc, 30.0, (w, h))
                    print(f"[Capture] Video writer initialized: {w}x{h} @ 30fps")
                video_writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))

            # Try to put frame in queue (non-blocking)
            try:
                output_queue.put(frame, block=False)
                error_count = 0
                
                if frame_count == 1:
                    print(f"[Capture] First frame captured: {frame.shape[1]}x{frame.shape[0]}")
            except:
                pass  # Queue full, drop frame
            
            # Print FPS every 50 frames
            if frame_count % 50 == 0 and frame_count > 0:
                elapsed = time.time() - start_time
                fps = frame_count / elapsed
                print(f"[Capture] FPS: {fps:.2f}")
                frame_count = 0
                start_time = time.time()
            
            time.sleep(capture_delay)
            
        except Exception as e:
            error_count += 1
            print(f"[Capture] Error ({error_count}/{max_consecutive_errors}): {e}")
            
            if error_count >= max_consecutive_errors:
                print("[Capture] Too many errors, stopping")
                break
            
            time.sleep(0.5)
    
    # Cleanup video writer
    if video_writer is not None:
        video_writer.release()
        print(f"[Capture] Debug video saved: {video_path}")

    print("[Capture] Capture worker stopped")


def list_windows_monitors():
    """List all available monitors on Windows.
    
    Returns:
        List of monitor dictionaries with geometry info
    """
    try:
        with mss.mss() as sct:
            monitors = []
            # Skip monitor 0 (all monitors combined)
            for i, mon in enumerate(sct.monitors[1:], start=0):
                monitors.append({
                    'index': i,
                    'left': mon['left'],
                    'top': mon['top'],
                    'width': mon['width'],
                    'height': mon['height'],
                })
                print(f"  [{i}] Monitor: {mon['width']}x{mon['height']} at ({mon['left']}, {mon['top']})")
            return monitors
    except Exception as e:
        print(f"[Capture] Error listing monitors: {e}")
        return []
