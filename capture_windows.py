"""Windows-specific screen capture worker using MSS and Win32 API."""

import os
import time
from multiprocessing import Queue, Event
import numpy as np
import mss
import mss.tools

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


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


def capture_windows_exclude_window(monitor_index: int = 0, exclude_hwnd: int = None):
    """Capture screen using MSS, optionally masking out a specific window.
    
    Args:
        monitor_index: Which monitor to capture (0 = all, 1+ = specific)
        exclude_hwnd: Windows handle (HWND) of window to exclude (black out)
    
    Returns:
        numpy.ndarray: RGB frame of the captured screen
    """
    frame = capture_windows(monitor_index)
    
    if frame is None:
        return None
    
    # If we need to exclude a window, black it out
    if exclude_hwnd is not None:
        try:
            import win32gui
            
            # Get window rectangle
            rect = win32gui.GetWindowRect(exclude_hwnd)
            x1, y1, x2, y2 = rect
            
            # Get monitor info to calculate relative coordinates
            with mss.mss() as sct:
                mon_idx = monitor_index + 1 if monitor_index >= 0 else 1
                if mon_idx > len(sct.monitors) - 1:
                    mon_idx = 1
                monitor = sct.monitors[mon_idx]
                
                # Calculate relative coordinates
                rel_x1 = max(0, x1 - monitor['left'])
                rel_y1 = max(0, y1 - monitor['top'])
                rel_x2 = min(monitor['width'], x2 - monitor['left'])
                rel_y2 = min(monitor['height'], y2 - monitor['top'])
                
                # Black out the window area
                if rel_x2 > rel_x1 and rel_y2 > rel_y1:
                    frame[rel_y1:rel_y2, rel_x1:rel_x2] = 0
        except Exception as e:
            print(f"[Capture] Error excluding window: {e}")
    
    return frame


def capture_worker_windows(output_queue: Queue, stop_event: Event, monitor_index: int = 0, 
                          overlay_hwnd_queue: Queue = None, monitor_geometry: tuple = None, 
                          hide_signal_queue: Queue = None):
    """
    Windows-specific capture worker that continuously captures the screen.
    
    Args:
        output_queue: Queue to put captured frames into
        stop_event: Event to signal when to stop capturing
        monitor_index: Which monitor to capture (0 = primary)
        overlay_hwnd_queue: Queue to receive overlay window HWND from (for exclusion)
        monitor_geometry: Tuple (x, y, width, height) for the target monitor (unused on Windows)
        hide_signal_queue: Queue to signal overlay to hide/show during capture (optional)
    """
    print(f"[Capture] Starting Windows capture worker for monitor {monitor_index}")
    
    # Wait for overlay window HWND
    overlay_hwnd = None
    if overlay_hwnd_queue is not None:
        print("[Capture] Waiting for overlay window HWND...")
        try:
            overlay_hwnd = overlay_hwnd_queue.get(timeout=5)
            print(f"[Capture] Got overlay window HWND: {overlay_hwnd}")
        except:
            print("[Capture] WARNING: Didn't get overlay window HWND")
    
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

    # Setup debug frame dump directory
    save_frames = False
    frames_dir = os.path.join(os.getcwd(), 'capture_frames')
    if HAS_PIL:
        try:
            os.makedirs(frames_dir, exist_ok=True)
            print(f"[Capture] Debug frames will be saved to: {frames_dir}")
            save_frames = True
        except Exception as e:
            print(f"[Capture] Could not create frames dir: {e}")
    
    while not stop_event.is_set():
        try:
            # Capture screen
            # Note: overlay uses WDA_EXCLUDEFROMCAPTURE, so it's already excluded
            # from BitBlt-based captures like MSS. No need for manual exclusion.
            frame = capture_windows(monitor_index)
            
            if frame is None:
                raise RuntimeError("Capture returned None")
            
            frame_count += 1

            # Save every frame as PNG for debug recording
            if save_frames:
                try:
                    img = Image.fromarray(frame)
                    img.save(os.path.join(frames_dir, f'frame_{frame_count:06d}.png'))
                except Exception as e:
                    print(f"[Capture] Frame save error: {e}")

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
