"""Windows-specific transparent overlay window using PyQt6."""

import numpy as np
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QImage
from multiprocessing import Queue
import sys
import ctypes


class TransparentOverlayWindows(QWidget):
    """Fullscreen transparent overlay that renders person masks in red (Windows version)."""
    
    def __init__(self, mask_queue: Queue, capture_queue: Queue = None, screen_index: int = 0, hide_signal_queue: Queue = None):
        super().__init__()
        self.mask_queue = mask_queue
        self.capture_queue = capture_queue
        self.screen_index = screen_index
        self.hide_signal_queue = hide_signal_queue
        self.current_mask = None
        self.current_frame = None
        self.screen_geometry = None
        self.rect_x_offset = 0  # For moving rectangle test
        self.rect_width = 200
        self._hidden_for_capture = False
        
        self.init_ui()
        
        # Timer to update mask from queue
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_mask)
        self.update_timer.start(33)  # ~30 FPS

        # Auto-close after 10 seconds (debug recording duration)
        self.close_timer = QTimer(self)
        self.close_timer.setSingleShot(True)
        self.close_timer.timeout.connect(self.close_and_quit)
        self.close_timer.start(10000)  # 10 seconds
        
        print("[Overlay] Windows transparent overlay initialized")
    
    def init_ui(self):
        """Initialize the overlay window for Windows."""
        # Get screen geometry for the specific monitor
        screens = QApplication.screens()
        if self.screen_index < len(screens):
            screen = screens[self.screen_index]
            print(f"[Overlay] Using screen {self.screen_index}: {screen.name()}")
        else:
            screen = QApplication.primaryScreen()
            print(f"[Overlay] Screen {self.screen_index} not found, using primary")
        
        self.screen_geometry = screen.geometry()
        
        # Windows-specific window flags for transparent overlay
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput  # Click-through
        )
        
        # Enable transparency
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        
        # Make window click-through
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        # Set geometry to cover entire screen
        self.setGeometry(self.screen_geometry)
        
        # Store window handle (HWND) for capture exclusion
        try:
            self.overlay_hwnd = int(self.winId())
            print(f"[Overlay] Window HWND: {self.overlay_hwnd}")
            # Exclude this window from BitBlt-based screen captures (Windows 10 2004+)
            WDA_EXCLUDEFROMCAPTURE = 0x00000011
            result = ctypes.windll.user32.SetWindowDisplayAffinity(
                self.overlay_hwnd, WDA_EXCLUDEFROMCAPTURE
            )
            if result:
                print("[Overlay] WDA_EXCLUDEFROMCAPTURE set successfully")
            else:
                print(f"[Overlay] WARNING: SetWindowDisplayAffinity failed (error {ctypes.get_last_error()})")
        except:
            print("[Overlay] WARNING: Could not get window HWND")
            self.overlay_hwnd = None
        
        print(f"[Overlay] Screen geometry: {self.screen_geometry.width()}x{self.screen_geometry.height()}")
    
    def get_hwnd(self):
        """Get the Windows window handle (HWND)."""
        return self.overlay_hwnd
    
    def update_mask(self):
        """Try to get the latest mask from the queue."""
        try:
            # Check if capture worker wants us to hide
            if self.hide_signal_queue is not None:
                while not self.hide_signal_queue.empty():
                    signal = self.hide_signal_queue.get_nowait()
                    if signal == 'hide':
                        self._hidden_for_capture = True
                        self.hide()
                    elif signal == 'show':
                        self._hidden_for_capture = False
                        self.showFullScreen()
            
            # Get latest mask (non-blocking)
            while not self.mask_queue.empty():
                self.current_mask = self.mask_queue.get_nowait()
            
            # Get captured frame if available
            if self.capture_queue is not None:
                got_frame = False
                while not self.capture_queue.empty():
                    self.current_frame = self.capture_queue.get_nowait()
                    got_frame = True
                
                # Optional: verify we're not in the capture
                if got_frame and self.current_frame is not None:
                    pass  # Frame received for verification
            
            # Update display
            self.update()
            
            # Animate test rectangle
            self.rect_x_offset = (self.rect_x_offset + 5) % (self.screen_geometry.width() + self.rect_width)
            
        except Exception as e:
            print(f"[Overlay] Error in update_mask: {e}")

    def close_and_quit(self):
        """Close overlay and quit the application."""
        print("[Overlay] 10 seconds elapsed, closing...")
        self.close()
        QApplication.quit()
    
    def paintEvent(self, event):
        """Paint the overlay - red tint over detected persons."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # For testing: draw a moving red rectangle
        # Later this will be replaced with the actual segmentation mask
        if True:  # Test mode
            # Draw a semi-transparent red moving rectangle
            rect_x = self.rect_x_offset - self.rect_width
            rect_y = self.screen_geometry.height() // 2 - 100
            rect_h = 200
            
            painter.fillRect(
                rect_x, rect_y, self.rect_width, rect_h,
                QColor(255, 0, 0, 128)  # Semi-transparent red
            )
        
        # If we have a mask, draw it
        if self.current_mask is not None:
            try:
                mask = self.current_mask
                
                # Ensure mask is 2D
                if len(mask.shape) == 3:
                    mask = mask[:, :, 0]
                
                # Resize mask to screen size if needed
                if mask.shape[1] != self.screen_geometry.width() or mask.shape[0] != self.screen_geometry.height():
                    from skimage.transform import resize
                    mask = resize(mask, (self.screen_geometry.height(), self.screen_geometry.width()), 
                                order=0, preserve_range=True, anti_aliasing=False)
                    mask = mask.astype(np.uint8)
                
                # Create a red overlay where mask > 0
                overlay = np.zeros((mask.shape[0], mask.shape[1], 4), dtype=np.uint8)
                overlay[mask > 0] = [0, 0, 255, 128]  # Red with 50% transparency (RGBA)
                
                # Convert to QImage and draw
                height, width = overlay.shape[:2]
                bytes_per_line = 4 * width
                q_image = QImage(overlay.data, width, height, bytes_per_line, QImage.Format.Format_RGBA8888)
                
                painter.drawImage(0, 0, q_image)
                
            except Exception as e:
                print(f"[Overlay] Error rendering mask: {e}")
        
        painter.end()


def run_overlay_windows(mask_queue: Queue, capture_queue: Queue = None, hwnd_queue: Queue = None, 
                       screen_index: int = 0, hide_signal_queue: Queue = None):
    """
    Run the Windows transparent overlay window.
    
    Args:
        mask_queue: Queue containing person segmentation masks
        capture_queue: Queue containing captured frames (for verification)
        hwnd_queue: Queue to send window HWND back to main process
        screen_index: Which monitor to use (0 = primary)
        hide_signal_queue: Queue to receive hide/show signals from capture worker
    """
    print("[Overlay] Starting Windows overlay...")
    
    # Create QApplication if it doesn't exist
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    # Create and show overlay window
    overlay = TransparentOverlayWindows(mask_queue, capture_queue, screen_index, hide_signal_queue)
    
    # Send window HWND back to main process (for capture exclusion)
    if hwnd_queue is not None:
        try:
            hwnd = overlay.get_hwnd()
            if hwnd:
                hwnd_queue.put(hwnd)
                print(f"[Overlay] Sent HWND {hwnd} to main process")
        except Exception as e:
            print(f"[Overlay] Error sending HWND: {e}")
    
    overlay.showFullScreen()
    
    print("[Overlay] Overlay window visible. Press Ctrl+C to exit.")
    
    # Start event loop
    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        print("\n[Overlay] Keyboard interrupt received")
    except Exception as e:
        print(f"[Overlay] Error in overlay: {e}")
    finally:
        overlay.close()
