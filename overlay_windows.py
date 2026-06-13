"""Windows-specific transparent overlay window using PyQt6."""

import numpy as np
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QImage
from multiprocessing import Queue
import sys
import ctypes


class TransparentOverlayWindows(QWidget):
    """Fullscreen transparent overlay that renders person masks in red (Windows version)."""
    
    def __init__(self, mask_queue: Queue, screen_index: int = 0):
        super().__init__()
        self.mask_queue = mask_queue
        self.screen_index = screen_index
        self.current_mask = None
        self.screen_geometry = None
        
        self.init_ui()
        
        # Timer to update mask from queue
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_mask)
        self.update_timer.start(33)  # ~30 FPS

        # Auto-close after 30 seconds (debug recording duration)
        self.close_timer = QTimer(self)
        self.close_timer.setSingleShot(True)
        self.close_timer.timeout.connect(self.close_and_quit)
        self.close_timer.start(30000)  # 30 seconds
        
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
    
    def update_mask(self):
        """Try to get the latest mask from the queue."""
        try:
            # Get latest mask (non-blocking)
            while not self.mask_queue.empty():
                self.current_mask = self.mask_queue.get_nowait()
            
            # Update display
            self.update()
            
        except Exception as e:
            print(f"[Overlay] Error in update_mask: {e}")

    def close_and_quit(self):
        """Close overlay and quit the application."""
        print("[Overlay] Recording complete, closing...")
        self.close()
        QApplication.quit()
    
    def paintEvent(self, event):
        """Paint the overlay - red tint over everything except detected persons."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
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
                
                # Create a red overlay where mask is background (inverted: cover everything except person)
                overlay = np.zeros((mask.shape[0], mask.shape[1], 4), dtype=np.uint8)
                overlay[mask <= 0] = [0, 0, 255, 128]  # Red with 50% transparency (RGBA) on background
                
                # Convert to QImage and draw
                height, width = overlay.shape[:2]
                bytes_per_line = 4 * width
                q_image = QImage(overlay.data, width, height, bytes_per_line, QImage.Format.Format_RGBA8888)
                
                painter.drawImage(0, 0, q_image)
                
            except Exception as e:
                print(f"[Overlay] Error rendering mask: {e}")
        
        painter.end()


def run_overlay_windows(mask_queue: Queue, screen_index: int = 0):
    """
    Run the Windows transparent overlay window.
    
    Args:
        mask_queue: Queue containing person segmentation masks
        screen_index: Which monitor to use (0 = primary)
    """
    print("[Overlay] Starting Windows overlay...")
    
    # Create QApplication if it doesn't exist
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    # Create and show overlay window
    overlay = TransparentOverlayWindows(mask_queue, screen_index)
    
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
