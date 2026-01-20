"""Screen capture worker - supports both X11 and Wayland."""

import os
import time
import subprocess
import tempfile
from multiprocessing import Queue, Event
from pathlib import Path
import numpy as np
from PIL import Image


def is_wayland():
    """Check if running on Wayland."""
    return os.environ.get('XDG_SESSION_TYPE') == 'wayland'


def capture_wayland_gnome(monitor_region=None):
    """Capture screen using gnome-screenshot (works on GNOME Wayland).
    
    Args:
        monitor_region: Optional tuple (x, y, width, height) to crop to specific monitor
    """
    # Use a fixed temp file to avoid file creation overhead
    tmp_path = '/tmp/hijab_capture.png'
    
    try:
        # gnome-screenshot captures without permission dialog
        result = subprocess.run(
            ['gnome-screenshot', '-f', tmp_path],
            capture_output=True,
            timeout=5  # Increased timeout for Wayland
        )
        
        if result.returncode == 0 and Path(tmp_path).exists():
            img = Image.open(tmp_path)
            frame = np.array(img)
            # Convert RGBA to RGB if needed
            if len(frame.shape) > 2 and frame.shape[2] == 4:
                frame = frame[:, :, :3]
            
            # Crop to specific monitor region if specified
            if monitor_region:
                x, y, w, h = monitor_region
                frame = frame[y:y+h, x:x+w].copy()
            
            return frame
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        pass
    
    return None


def capture_wayland_grim(monitor_region=None):
    """Capture screen using grim (works on wlroots/Sway).
    
    Args:
        monitor_region: Optional tuple (x, y, width, height) to crop to specific monitor
    """
    try:
        result = subprocess.run(
            ['grim', '-'],  # Output to stdout
            capture_output=True,
            timeout=2
        )
        
        if result.returncode == 0:
            from io import BytesIO
            img = Image.open(BytesIO(result.stdout))
            frame = np.array(img)
            if len(frame.shape) > 2 and frame.shape[2] == 4:
                frame = frame[:, :, :3]
            
            # Crop to specific monitor region if specified
            if monitor_region:
                x, y, w, h = monitor_region
                frame = frame[y:y+h, x:x+w].copy()
            
            return frame
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    return None


def capture_x11(disp, root, width, height):
    """Capture screen using X11 (traditional method)."""
    from Xlib import X
    
    raw = root.get_image(0, 0, width, height, X.ZPixmap, 0xffffffff)
    
    # Convert to numpy array - X11 returns BGRX format (4 bytes per pixel)
    frame = np.frombuffer(raw.data, dtype=np.uint8)
    frame = frame.reshape(height, width, 4)
    
    # Convert BGRX to RGB
    frame = frame[:, :, [2, 1, 0]].copy()
    
    return frame


def capture_worker(output_queue: Queue, stop_event: Event, monitor_index: int = 0, overlay_id_queue: Queue = None, monitor_geometry: tuple = None, hide_signal_queue: Queue = None):
    """
    Continuously captures the screen and puts frames into the output queue.
    
    Supports both X11 and Wayland (via gnome-screenshot or grim).
    
    Args:
        output_queue: Queue to put captured frames into
        stop_event: Event to signal when to stop capturing
        monitor_index: Which monitor to capture (0 = primary)
        overlay_id_queue: Queue to receive overlay window ID from (for X11 exclusion)
        monitor_geometry: Tuple (x, y, width, height) for the target monitor (for Wayland cropping)
        hide_signal_queue: Queue to signal overlay to hide/show during capture
    """
    print(f"[Capture] Starting capture worker for monitor {monitor_index}")
    
    wayland_mode = is_wayland()
    print(f"[Capture] Session type: {'Wayland' if wayland_mode else 'X11'}")
    
    # Wait for overlay window ID (only needed for X11)
    overlay_window_id = None
    if overlay_id_queue is not None:
        print("[Capture] Waiting for overlay window ID...")
        try:
            overlay_window_id = overlay_id_queue.get(timeout=5)
            print(f"[Capture] Got overlay window ID: {overlay_window_id}")
        except:
            print("[Capture] WARNING: Didn't get overlay window ID")
    
    # Initialize X11 if not on Wayland
    disp = None
    root = None
    width = height = 0
    
    if not wayland_mode:
        try:
            from Xlib import display as xlib_display
            
            disp = xlib_display.Display()
            screen = disp.screen()
            root = screen.root
            width = screen.width_in_pixels
            height = screen.height_in_pixels
            
            print(f"[Capture] X11 screen size: {width}x{height}")
        except Exception as e:
            print(f"[Capture] Failed to initialize X11: {e}")
            print("[Capture] Falling back to Wayland capture methods")
            wayland_mode = True
    
    if wayland_mode:
        # Get monitor geometry for cropping - passed in from main process
        monitor_region = monitor_geometry
        if monitor_region:
            print(f"[Capture] Monitor {monitor_index} region: x={monitor_region[0]}, y={monitor_region[1]}, {monitor_region[2]}x{monitor_region[3]}")
        else:
            print(f"[Capture] No monitor geometry provided, capturing full screen")
        
        # Test which Wayland capture method works
        print("[Capture] Testing Wayland capture methods...")
        
        test_frame = capture_wayland_gnome(monitor_region)
        if test_frame is not None:
            print(f"[Capture] Using gnome-screenshot ({test_frame.shape[1]}x{test_frame.shape[0]})")
            capture_method = 'gnome'
        else:
            test_frame = capture_wayland_grim(monitor_region)
            if test_frame is not None:
                print(f"[Capture] Using grim ({test_frame.shape[1]}x{test_frame.shape[0]})")
                capture_method = 'grim'
            else:
                print("[Capture] ERROR: No working Wayland capture method found!")
                print("[Capture] Please install gnome-screenshot or grim")
                return
    
    frame_count = 0
    start_time = time.time()
    error_count = 0
    max_consecutive_errors = 10
    
    # Capture delay (Wayland is slower due to file I/O)
    capture_delay = 0.05 if wayland_mode else 0.01
    
    # For Wayland with gnome-screenshot, hiding the overlay during capture
    # would cause severe flickering due to slow capture (~2s).
    # Instead, we capture everything and accept that the overlay may be visible.
    # The overlay is now transparent (not drawing frames), so there's no feedback loop.
    
    while not stop_event.is_set():
        try:
            frame = None
            
            if wayland_mode:
                # Wayland capture with monitor region cropping
                if capture_method == 'gnome':
                    frame = capture_wayland_gnome(monitor_region)
                else:
                    frame = capture_wayland_grim(monitor_region)
            else:
                # X11 capture
                frame = capture_x11(disp, root, width, height)
                
                # Black out overlay window area if we have the ID
                if overlay_window_id and frame is not None:
                    try:
                        overlay_win = disp.create_resource_object('window', overlay_window_id)
                        geom = overlay_win.get_geometry()
                        x, y, w, h = geom.x, geom.y, geom.width, geom.height
                        x = max(0, x)
                        y = max(0, y)
                        w = min(w, width - x)
                        h = min(h, height - y)
                        if w > 0 and h > 0:
                            frame[y:y+h, x:x+w] = 0
                    except:
                        pass
            
            if frame is None:
                raise RuntimeError("Capture returned None")
            
            # Try to put frame in queue (non-blocking)
            try:
                output_queue.put(frame, block=False)
                frame_count += 1
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
    
    print("[Capture] Capture worker stopped")
