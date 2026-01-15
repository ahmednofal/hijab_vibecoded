"""Screen capture worker using X11 XComposite to exclude overlay."""

import time
from multiprocessing import Queue, Event
import numpy as np
from Xlib import X, display as xlib_display
from Xlib.ext import composite
import cv2

def capture_worker(output_queue: Queue, stop_event: Event, monitor_index: int = 0, overlay_id_queue: Queue = None):
    """
    Continuously captures the screen and puts frames into the output queue.
    
    Args:
        output_queue: Queue to put captured frames into
        stop_event: Event to signal when to stop capturing
        monitor_index: Which monitor to capture (0 = primary)
        overlay_id_queue: Queue to receive overlay window ID from (to exclude it)
    """
    print(f"[Capture] Starting capture worker for monitor {monitor_index}")
    
    # Wait for overlay window ID
    overlay_window_id = None
    if overlay_id_queue is not None:
        print("[Capture] Waiting for overlay window ID...")
        try:
            overlay_window_id = overlay_id_queue.get(timeout=5)
            print(f"[Capture] Got overlay window ID: {overlay_window_id} - will exclude it")
        except:
            print("[Capture] WARNING: Didn't get overlay window ID, will capture everything")
    
    # Open X11 display
    try:
        disp = xlib_display.Display()
        screen = disp.screen()
        root = screen.root
        
        # Get screen dimensions
        width = screen.width_in_pixels
        height = screen.height_in_pixels
        
        print(f"[Capture] Screen size: {width}x{height}")
        print(f"[Capture] Using X11 direct capture (excluding overlay)")
        
    except Exception as e:
        print(f"[Capture] Failed to initialize X11: {e}")
        return
    
    frame_count = 0
    start_time = time.time()
    error_count = 0
    max_consecutive_errors = 10
    
    while not stop_event.is_set():
        try:
            # Get root window pixmap
            # This captures all windows on the root window
            raw = root.get_image(0, 0, width, height, X.ZPixmap, 0xffffffff)
            
            # Convert to numpy array
            # X11 returns BGRX format (4 bytes per pixel)
            frame = np.frombuffer(raw.data, dtype=np.uint8)
            
            # Reshape to image dimensions (BGRX format)
            frame = frame.reshape(height, width, 4)
            
            # Convert BGRX to RGB (drop alpha, swap B and R)
            frame = frame[:, :, [2, 1, 0]]  # BGR to RGB, dropping the X channel
            
            # Make a copy to ensure data persists
            frame = frame.copy()
            
            # Try to put frame in queue (non-blocking)
            try:
                output_queue.put(frame, block=False)
                frame_count += 1
                error_count = 0  # Reset error count on success
                
                # Print success message first time
                if frame_count == 1:
                    print(f"[Capture] Successfully captured first frame: {width}x{height}")
            except:
                # Queue is full, drop this frame
                pass
            
            # Print FPS every 100 frames
            if frame_count % 100 == 0 and frame_count > 0:
                elapsed = time.time() - start_time
                fps = frame_count / elapsed
                print(f"[Capture] FPS: {fps:.2f}")
                frame_count = 0
                start_time = time.time()
            
            # Small delay to prevent excessive CPU usage
            time.sleep(0.01)
            
        except Exception as e:
            error_count += 1
            print(f"[Capture] Error ({error_count}/{max_consecutive_errors}): {e}")
            
            if error_count >= max_consecutive_errors:
                print(f"[Capture] Too many consecutive errors, stopping capture worker")
                break
            
            time.sleep(0.5)
    
    print("[Capture] Capture worker stopped")
