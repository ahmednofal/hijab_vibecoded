"""Screen capture worker using PyQt6 for screen capture."""

import time
from multiprocessing import Queue, Event
import numpy as np
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QScreen
from PyQt6.QtCore import QRect
import sys


def capture_worker(output_queue: Queue, stop_event: Event, monitor_index: int = 0):
    """
    Continuously captures the screen and puts frames into the output queue.
    
    Args:
        output_queue: Queue to put captured frames into
        stop_event: Event to signal when to stop capturing
        monitor_index: Which monitor to capture (0 = primary)
    """
    print(f"[Capture] Starting capture worker for monitor {monitor_index}")
    
    # Create QApplication for screen capture
    app = QApplication(sys.argv)
    
    # Get the screen
    screens = QApplication.screens()
    if monitor_index >= len(screens):
        print(f"[Capture] Warning: Monitor {monitor_index} not found, using primary screen")
        monitor_index = 0
    
    screen = screens[monitor_index]
    print(f"[Capture] Screen size: {screen.size().width()}x{screen.size().height()}")
    
    frame_count = 0
    start_time = time.time()
    error_count = 0
    max_consecutive_errors = 10
    
    while not stop_event.is_set():
        try:
            # Capture the screen using QScreen.grabWindow
            pixmap = screen.grabWindow(0)
            
            if pixmap.isNull():
                # Fallback: try grabbing the entire screen geometry
                pixmap = screen.grabWindow(0, 0, 0, screen.size().width(), screen.size().height())
            
            if pixmap.isNull():
                raise Exception("Failed to capture screen - grabWindow returned null (Wayland restriction?)")
            
            # Convert to QImage
            image = pixmap.toImage()
            
            if image.isNull():
                raise Exception("Failed to convert pixmap to image")
            
            # Convert to numpy array
            width = image.width()
            height = image.height()
            
            # Convert QImage to RGB888 format
            image = image.convertToFormat(image.Format.Format_RGB888)
            
            # Get the bits and convert to numpy array
            ptr = image.bits()
            if ptr is None:
                raise Exception("Failed to get image bits - Wayland may not support screen capture")
            
            ptr.setsize(height * width * 3)
            frame = np.frombuffer(ptr, np.uint8).reshape((height, width, 3))
            
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
            
            # Small sleep to prevent CPU overuse
            time.sleep(0.01)  # 100 FPS max
            
        except Exception as e:
            error_count += 1
            print(f"[Capture] Error ({error_count}/{max_consecutive_errors}): {e}")
            
            if error_count >= max_consecutive_errors:
                print(f"[Capture] Too many consecutive errors, stopping capture worker")
                break
            
            time.sleep(0.5)
    
    print("[Capture] Capture worker stopped")
