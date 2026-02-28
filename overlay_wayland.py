#!/usr/bin/env python3
"""Wayland-specific transparent overlay implementation.

This module provides an overlay solution optimized for Wayland display servers.
Uses GTK/layer-shell or other Wayland-native approaches for transparency.

Agent: Wayland Specialist
"""

import numpy as np
from multiprocessing import Queue
import sys
import os
import cairo
import gi

gi.require_version('Gtk', '3.0')
try:
    gi.require_version('GtkLayerShell', '0.1')
    LAYER_SHELL_AVAILABLE = True
except ValueError:
    print("[WaylandOverlay] WARNING: GtkLayerShell not available, using fallback")
    LAYER_SHELL_AVAILABLE = False

from gi.repository import Gtk, Gdk, GLib, GdkPixbuf
if LAYER_SHELL_AVAILABLE:
    from gi.repository import GtkLayerShell


class WaylandTransparentOverlay(Gtk.Window):
    """Wayland-optimized transparent overlay using GTK3."""
    
    def __init__(self, mask_queue: Queue, capture_queue: Queue = None,
                 screen_index: int = 0, hide_signal_queue: Queue = None):
        super().__init__()
        
        self.mask_queue = mask_queue
        self.capture_queue = capture_queue
        self.screen_index = screen_index
        self.hide_signal_queue = hide_signal_queue
        self.current_mask = None
        self.current_frame = None
        self.rect_x_offset = 0
        self.rect_width = 400  # Larger rectangle for visibility
        self._hidden_for_capture = False
        self._draw_count = 0  # Debug counter
        
        self.init_ui()
        
        # Timer for updates
        GLib.timeout_add(33, self.update_mask)  # ~30 FPS
        
        print("[WaylandOverlay] Wayland transparent overlay initialized")
    
    def init_ui(self):
        """Initialize the Wayland overlay window."""
        # Verify we're on Wayland
        session_type = os.environ.get('XDG_SESSION_TYPE', 'unknown')
        if session_type != 'wayland':
            print(f"[WaylandOverlay] WARNING: Not running on Wayland (detected: {session_type})")
        
        # Get screen dimensions
        display = Gdk.Display.get_default()
        monitor = display.get_monitor(self.screen_index if self.screen_index < display.get_n_monitors() else 0)
        geometry = monitor.get_geometry()
        
        self.screen_width = geometry.width
        self.screen_height = geometry.height
        
        print(f"[WaylandOverlay] Screen geometry: {self.screen_width}x{self.screen_height}")
        
        # CRITICAL: Set window properties for transparency
        # Don't use fullscreen - it prevents transparency on some compositors
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        
        # Use NOTIFICATION type hint - this often supports transparency better
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        
        # Enable transparency BEFORE realizing/showing
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
            print("[WaylandOverlay] RGBA visual enabled")
        else:
            print("[WaylandOverlay] WARNING: No RGBA visual available")
            # Try composited visual as fallback
            visual = screen.get_system_visual()
            self.set_visual(visual)
        
        self.set_app_paintable(True)
        
        # Connect signals
        self.connect('draw', self.on_draw)
        self.connect('destroy', self.on_destroy)
        self.connect('realize', self.on_realize)
        
        # Set input passthrough
        self.set_accept_focus(False)
        self.set_can_focus(False)
        
        # Set exact window size to cover screen
        self.set_default_size(self.screen_width, self.screen_height)
        self.resize(self.screen_width, self.screen_height)
        
        # Move to screen position (important for multi-monitor)
        self.move(geometry.x, geometry.y)
        
        # Show window
        self.show_all()
        
        # Get window ID
        self.overlay_window_id = id(self)
        print(f"[WaylandOverlay] Window ID: {self.overlay_window_id}")
        print("[WaylandOverlay] Using NOTIFICATION window type for better transparency")
    
    def on_realize(self, widget):
        """Called when window is realized - set input passthrough."""
        try:
            window = self.get_window()
            if window:
                # Create empty input region for passthrough
                region = cairo.Region()
                window.input_shape_combine_region(region, 0, 0)
                print("[WaylandOverlay] Input passthrough enabled")
                
                # CRITICAL: Set window to be transparent/composited
                # This is compositor-specific but worth trying
                window.set_opacity(0.99)  # Slightly less than 1.0 forces compositing
                print("[WaylandOverlay] Window opacity set to enable compositing")
        except Exception as e:
            print(f"[WaylandOverlay] Could not set input passthrough: {e}")
    
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
                        print("[WaylandOverlay] Hiding for capture")
                    elif signal == 'show':
                        self._hidden_for_capture = False
                        self.show_all()
                        print("[WaylandOverlay] Showing after capture")
            
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
                    print(f"[WaylandOverlay] First frame received! Shape: {self.current_frame.shape}")
            
            # Animate rectangle
            if not self._hidden_for_capture:
                old_x = self.rect_x_offset
                self.rect_x_offset += 10  # Faster movement for visibility
                if self.rect_x_offset > self.screen_width:
                    self.rect_x_offset = 0
                    print(f"[WaylandOverlay] Rectangle reset to left (was at {old_x})")
                
                # Debug movement occasionally
                if not hasattr(self, '_update_count'):
                    self._update_count = 0
                self._update_count += 1
                if self._update_count % 30 == 1:
                    print(f"[WaylandOverlay] Update #{self._update_count}: Moving rect from {old_x} to {self.rect_x_offset}")
            
            # Trigger redraw
            self.queue_draw()
            
        except Exception as e:
            print(f"[WaylandOverlay] Update error: {e}")
            import traceback
            traceback.print_exc()
        
        return True  # Continue timer
    
    def on_draw(self, widget, cr):
        """Paint the overlay content using Cairo."""
        try:
            self._draw_count += 1
            if self._draw_count % 10 == 1:  # Debug more frequently
                print(f"[WaylandOverlay] Draw #{self._draw_count}: rect at x={self.rect_x_offset}, "
                      f"width={self.rect_width}, screen={self.screen_width}x{self.screen_height}")
            
            # CRITICAL: Clear entire surface with fully transparent color
            # This ensures desktop shows through
            cr.save()
            cr.set_source_rgba(0, 0, 0, 0)  # Fully transparent
            cr.set_operator(cairo.OPERATOR_SOURCE)  # Replace everything
            cr.paint()
            cr.restore()
            
            # Now draw red rectangle with normal composition
            huge_width = int(self.screen_width * 0.5)
            
            cr.set_source_rgba(1.0, 0.0, 0.0, 0.7)  # Semi-transparent red
            cr.set_operator(cairo.OPERATOR_OVER)  # Normal blending
            cr.rectangle(self.rect_x_offset, 0, huge_width, self.screen_height)
            cr.fill()
            
            if self._draw_count == 1:
                print(f"[WaylandOverlay] First draw: rect from {self.rect_x_offset} to {self.rect_x_offset + huge_width}, height {self.screen_height}")
                print(f"[WaylandOverlay] Drawing with transparent background - desktop should show through")
            
        except Exception as e:
            print(f"[WaylandOverlay] Draw error: {e}")
            import traceback
            traceback.print_exc()
        
        return False
    
    def on_destroy(self, widget):
        """Clean up when window is closed."""
        print("[WaylandOverlay] Wayland overlay window closed")
        Gtk.main_quit()


def run_overlay_wayland(mask_queue: Queue, capture_queue: Queue = None,
                       overlay_id_queue: Queue = None, screen_index: int = 0,
                       hide_signal_queue: Queue = None):
    """Run the Wayland-optimized overlay window.
    
    Args:
        mask_queue: Queue to receive segmentation masks
        capture_queue: Queue to receive captured frames
        overlay_id_queue: Queue to send overlay window ID
        screen_index: Which monitor to display on
        hide_signal_queue: Queue to receive hide/show signals
    """
    # Verify Wayland
    session_type = os.environ.get('XDG_SESSION_TYPE', 'unknown')
    if session_type != 'wayland':
        print(f"[WaylandOverlay] WARNING: Not running on Wayland (detected: {session_type})")
        print("[WaylandOverlay] This overlay is optimized for Wayland but will try to run anyway")
    
    print("[WaylandOverlay] Starting Wayland overlay application")
    
    overlay = WaylandTransparentOverlay(mask_queue, capture_queue, screen_index, hide_signal_queue)
    
    # Send overlay window ID
    if overlay_id_queue is not None:
        overlay_id_queue.put(overlay.overlay_window_id)
        print(f"[WaylandOverlay] Sent window ID {overlay.overlay_window_id} to capture worker")
    
    try:
        Gtk.main()
    except KeyboardInterrupt:
        print("[WaylandOverlay] Keyboard interrupt")


if __name__ == '__main__':
    print("Wayland Overlay - Wayland Display Server Specialist")
    print("This module provides Wayland-optimized transparent overlay")
    print("Requires: python3-gi, gir1.2-gtk-3.0, gir1.2-gtklayershell-0.1")
    print("Install layer-shell: sudo apt install gir1.2-gtklayershell-0.1")
    print("Run main.py to start the application")
