#!/usr/bin/env python3
"""X11-specific transparent overlay implementation.

This module provides an overlay solution optimized for X11 display servers.
Uses native X11 features for true transparency and input passthrough.

Agent: X11 Specialist
"""

import numpy as np
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QPainter, QColor, QPixmap, QImage, QPainterPath, QRegion
from multiprocessing import Queue
import sys
import os


class X11TransparentOverlay(QWidget):
    """X11-optimized transparent overlay with input passthrough."""
    
    def __init__(self, mask_queue: Queue, capture_queue: Queue = None, 
                 screen_index: int = 0, hide_signal_queue: Queue = None):
        super().__init__()
        self.mask_queue = mask_queue
        self.capture_queue = capture_queue
        self.screen_index = screen_index
        self.hide_signal_queue = hide_signal_queue
        self.current_mask = None
        self.current_frame = None
        self.screen_geometry = None
        self.rect_x_offset = 0
        self.rect_width = 200
        self._hidden_for_capture = False
        
        self.init_ui()
        
        # Timer to update mask from queue
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_mask)
        self.update_timer.start(33)  # ~30 FPS
        
        print("[X11Overlay] X11 transparent overlay initialized")
    
    def init_ui(self):
        """Initialize the X11 overlay window."""
        # Verify we're on X11
        session_type = os.environ.get('XDG_SESSION_TYPE', 'unknown')
        if session_type != 'x11':
            print(f"[X11Overlay] WARNING: Not running on X11 (detected: {session_type})")
        
        # Get screen geometry
        screens = QApplication.screens()
        if self.screen_index < len(screens):
            screen = screens[self.screen_index]
            print(f"[X11Overlay] Using screen {self.screen_index}: {screen.name()}")
        else:
            screen = QApplication.primaryScreen()
            print(f"[X11Overlay] Screen {self.screen_index} not found, using primary")
        
        self.screen_geometry = screen.geometry()
        
        # X11-specific window flags
        # X11BypassWindowManagerHint gives us direct control over window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.X11BypassWindowManagerHint |  # X11 specific!
            Qt.WindowType.WindowTransparentForInput
        )
        
        # Enable transparency
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        
        # No focus
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        # Set geometry to cover entire screen
        self.setGeometry(self.screen_geometry)
        
        # Try to set X11 window properties for better compositing
        try:
            from Xlib import X, display, Xatom
            from Xlib.protocol import event
            
            d = display.Display()
            window = d.create_resource_object('window', int(self.winId()))
            
            # Set window type to UTILITY (less intrusive)
            window_type = d.intern_atom('_NET_WM_WINDOW_TYPE')
            window_type_utility = d.intern_atom('_NET_WM_WINDOW_TYPE_UTILITY')
            window.change_property(window_type, Xatom.ATOM, 32, [window_type_utility])
            
            # Request to skip taskbar and pager
            wm_state = d.intern_atom('_NET_WM_STATE')
            wm_state_skip_taskbar = d.intern_atom('_NET_WM_STATE_SKIP_TASKBAR')
            wm_state_skip_pager = d.intern_atom('_NET_WM_STATE_SKIP_PAGER')
            wm_state_above = d.intern_atom('_NET_WM_STATE_ABOVE')
            
            window.change_property(wm_state, Xatom.ATOM, 32, 
                                 [wm_state_skip_taskbar, wm_state_skip_pager, wm_state_above])
            
            d.sync()
            print("[X11Overlay] X11 properties set successfully")
        except Exception as e:
            print(f"[X11Overlay] Could not set X11 properties: {e}")
        
        self.overlay_window_id = int(self.winId())
        print(f"[X11Overlay] Screen geometry: {self.screen_geometry.width()}x{self.screen_geometry.height()}")
        print(f"[X11Overlay] Window ID: {self.overlay_window_id}")
    
    def update_mask(self):
        """Update overlay state from queues."""
        try:
            # Handle hide/show signals
            if self.hide_signal_queue is not None:
                while not self.hide_signal_queue.empty():
                    signal = self.hide_signal_queue.get_nowait()
                    if signal == 'hide':
                        self._hidden_for_capture = True
                        self.hide()
                    elif signal == 'show':
                        self._hidden_for_capture = False
                        self.showFullScreen()
            
            # Get latest mask
            while not self.mask_queue.empty():
                self.current_mask = self.mask_queue.get_nowait()
            
            # Get captured frame
            if self.capture_queue is not None:
                got_frame = False
                while not self.capture_queue.empty():
                    self.current_frame = self.capture_queue.get_nowait()
                    got_frame = True
                
                if got_frame and not hasattr(self, '_first_frame_received'):
                    self._first_frame_received = True
                    print(f"[X11Overlay] First frame received! Shape: {self.current_frame.shape}")
            
            # Animate rectangle
            if not self._hidden_for_capture:
                self.rect_x_offset += 5
                if self.rect_x_offset > self.screen_geometry.width():
                    self.rect_x_offset = 0
            
            self.update()
        except Exception as e:
            print(f"[X11Overlay] Update error: {e}")
    
    def paintEvent(self, event):
        """Paint the overlay content."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        
        try:
            screen_width = self.screen_geometry.width()
            screen_height = self.screen_geometry.height()
            
            # Clear with transparency
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(0, 0, screen_width, screen_height, Qt.GlobalColor.transparent)
            
            # Draw content
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            
            # Draw moving red rectangle
            painter.fillRect(
                self.rect_x_offset, 0,
                self.rect_width, screen_height,
                QColor(255, 0, 0, 180)
            )
            
        except Exception as e:
            print(f"[X11Overlay] Paint error: {e}")
        
        painter.end()
    
    def closeEvent(self, event):
        """Clean up when window is closed."""
        self.update_timer.stop()
        print("[X11Overlay] X11 overlay window closed")
        event.accept()


def run_overlay_x11(mask_queue: Queue, capture_queue: Queue = None, 
                    overlay_id_queue: Queue = None, screen_index: int = 0, 
                    hide_signal_queue: Queue = None):
    """Run the X11-optimized overlay window.
    
    Args:
        mask_queue: Queue to receive segmentation masks
        capture_queue: Queue to receive captured frames
        overlay_id_queue: Queue to send overlay window ID
        screen_index: Which monitor to display on
        hide_signal_queue: Queue to receive hide/show signals
    """
    # Verify X11
    session_type = os.environ.get('XDG_SESSION_TYPE', 'unknown')
    if session_type != 'x11':
        print(f"[X11Overlay] ERROR: This overlay requires X11 (detected: {session_type})")
        print("[X11Overlay] Please switch to X11 session or use a different overlay implementation")
        return
    
    app = QApplication(sys.argv)
    print("[X11Overlay] Starting X11 overlay application")
    
    overlay = X11TransparentOverlay(mask_queue, capture_queue, screen_index, hide_signal_queue)
    overlay.showFullScreen()
    
    # Send overlay window ID
    if overlay_id_queue is not None:
        overlay_id_queue.put(overlay.overlay_window_id)
        print(f"[X11Overlay] Sent window ID {overlay.overlay_window_id} to capture worker")
    
    sys.exit(app.exec())


if __name__ == '__main__':
    print("X11 Overlay - X11 Display Server Specialist")
    print("This module provides X11-optimized transparent overlay")
    print("Run main.py to start the application")
