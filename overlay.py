"""Transparent overlay window using PyQt6."""

import numpy as np
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QPainter, QColor, QPixmap, QImage, QPainterPath, QRegion
from multiprocessing import Queue
import sys


class TransparentOverlay(QWidget):
    """Fullscreen transparent overlay that renders person masks in red."""
    
    def __init__(self, mask_queue: Queue, capture_queue: Queue = None):
        super().__init__()
        self.mask_queue = mask_queue
        self.capture_queue = capture_queue
        self.current_mask = None
        self.current_frame = None
        self.screen_geometry = None
        self.rect_x_offset = 0  # For moving rectangle test
        self.rect_width = 200
        
        self.init_ui()
        
        # Timer to update mask from queue
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_mask)
        self.update_timer.start(33)  # ~30 FPS
        
        print("[Overlay] Transparent overlay initialized")
    
    def init_ui(self):
        """Initialize the overlay window."""
        # Get screen geometry
        screen = QApplication.primaryScreen()
        self.screen_geometry = screen.geometry()
        
        # Set window flags for transparent, always-on-top, frameless window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.X11BypassWindowManagerHint |
            Qt.WindowType.WindowTransparentForInput  # This is key for input passthrough
        )
        
        # Enable transparency
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Make window click-through (input passthrough)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        # Additional attribute for complete input passthrough
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        # Set geometry to cover entire screen
        self.setGeometry(self.screen_geometry)
        
        # Store window ID for capture exclusion
        self.overlay_window_id = int(self.winId())
        
        print(f"[Overlay] Screen geometry: {self.screen_geometry.width()}x{self.screen_geometry.height()}")
        print(f"[Overlay] Window ID: {self.overlay_window_id}")
    
    def update_mask(self):
        """Try to get the latest mask from the queue."""
        try:
            # Get latest mask (non-blocking)
            while not self.mask_queue.empty():
                self.current_mask = self.mask_queue.get_nowait()
            
            # Get captured frame if available
            if self.capture_queue is not None:
                got_frame = False
                while not self.capture_queue.empty():
                    self.current_frame = self.capture_queue.get_nowait()
                    got_frame = True
                
                # Debug: print when we get first frame
                if got_frame and not hasattr(self, '_first_frame_received'):
                    self._first_frame_received = True
                    print(f"[Overlay] First frame received! Shape: {self.current_frame.shape}")
                    # Check if frame is all black
                    mean_val = self.current_frame.mean()
                    print(f"[Overlay] Frame mean value: {mean_val:.2f} (0=black, 255=white)")
                    print(f"[Overlay] Frame min: {self.current_frame.min()}, max: {self.current_frame.max()}")
            
            # Move rectangle to the right
            self.rect_x_offset += 5
            if self.rect_x_offset > self.screen_geometry.width():
                self.rect_x_offset = 0
            
            # Trigger repaint
            self.update()
        except Exception as e:
            print(f"[Overlay] Update error: {e}")
    
    def paintEvent(self, event):
        """Paint the red overlay where persons are detected."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        
        try:
            screen_width = self.screen_geometry.width()
            screen_height = self.screen_geometry.height()
            
            # Draw captured frame as background (if available)
            if self.current_frame is not None:
                try:
                    frame_height, frame_width = self.current_frame.shape[:2]
                    frame_copy = self.current_frame.copy()
                    
                    bytes_per_line = frame_width * 3
                    q_image = QImage(
                        frame_copy.data,
                        frame_width,
                        frame_height,
                        bytes_per_line,
                        QImage.Format.Format_RGB888
                    ).copy()
                    
                    pixmap = QPixmap.fromImage(q_image)
                    pixmap = pixmap.scaled(
                        screen_width,
                        screen_height,
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.FastTransformation
                    )
                    
                    painter.drawPixmap(0, 0, pixmap)
                except Exception as e:
                    print(f"[Overlay] Error drawing frame: {e}")
            else:
                # Draw dark gray background if no frame yet
                painter.fillRect(0, 0, screen_width, screen_height, QColor(40, 40, 40))
            
            # Draw moving red rectangle
            painter.fillRect(
                self.rect_x_offset, 0,  # x, y
                self.rect_width, screen_height,  # width, height
                QColor(255, 0, 0, 180)  # Red with opacity
            )
            
        except Exception as e:
            print(f"[Overlay] Paint error: {e}")
        
        painter.end()
    
    def closeEvent(self, event):
        """Clean up when window is closed."""
        self.update_timer.stop()
        print("[Overlay] Overlay window closed")
        event.accept()


def run_overlay(mask_queue: Queue, capture_queue: Queue = None, overlay_id_queue: Queue = None):
    """
    Run the overlay window in the main thread.
    
    Args:
        mask_queue: Queue to receive segmentation masks from
        capture_queue: Queue to receive captured frames from
        overlay_id_queue: Queue to send overlay window ID to capture worker
    """
    app = QApplication(sys.argv)
    
    print("[Overlay] Starting overlay application")
    
    overlay = TransparentOverlay(mask_queue, capture_queue)
    overlay.showFullScreen()
    
    # Send overlay window ID to capture worker so it can exclude it
    if overlay_id_queue is not None:
        overlay_id_queue.put(overlay.overlay_window_id)
        print(f"[Overlay] Sent window ID {overlay.overlay_window_id} to capture worker")
    
    sys.exit(app.exec())
