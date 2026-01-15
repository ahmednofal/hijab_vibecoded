"""Transparent overlay window using PyQt6."""

import numpy as np
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QPainter, QColor, QPixmap, QImage, QPainterPath, QRegion
from multiprocessing import Queue
import sys


class TransparentOverlay(QWidget):
    """Fullscreen transparent overlay that renders person masks in red."""
    
    def __init__(self, mask_queue: Queue):
        super().__init__()
        self.mask_queue = mask_queue
        self.current_mask = None
        self.screen_geometry = None
        
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
        
        print(f"[Overlay] Screen geometry: {self.screen_geometry.width()}x{self.screen_geometry.height()}")
    
    def update_mask(self):
        """Try to get the latest mask from the queue."""
        try:
            # Get latest mask (non-blocking)
            while not self.mask_queue.empty():
                self.current_mask = self.mask_queue.get_nowait()
            
            # Trigger repaint
            self.update()
        except:
            pass
    
    def paintEvent(self, event):
        """Paint the red overlay where persons are detected."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        
        try:
            # Draw a big red rectangle covering half the screen for testing
            screen_width = self.screen_geometry.width()
            screen_height = self.screen_geometry.height()
            
            # Draw red semi-transparent rectangle on the left half
            painter.fillRect(
                0, 0,  # x, y
                screen_width // 2, screen_height,  # width, height
                QColor(255, 0, 0, 128)  # Red with 50% opacity
            )
            
        except Exception as e:
            print(f"[Overlay] Paint error: {e}")
        
        painter.end()
    
    def closeEvent(self, event):
        """Clean up when window is closed."""
        self.update_timer.stop()
        print("[Overlay] Overlay window closed")
        event.accept()


def run_overlay(mask_queue: Queue):
    """
    Run the overlay window in the main thread.
    
    Args:
        mask_queue: Queue to receive segmentation masks from
    """
    app = QApplication(sys.argv)
    
    # Check if compositor is running (optional warning)
    print("[Overlay] Starting overlay application")
    
    overlay = TransparentOverlay(mask_queue)
    overlay.showFullScreen()
    
    sys.exit(app.exec())