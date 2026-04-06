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
        self._hidden_for_capture = False
        self._draw_count = 0
        
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
        
        # DOCK type hint: GNOME unconditionally excludes DOCK windows from
        # the Alt-Tab switcher, the overview (Super key), and the taskbar.
        # NOTIFICATION is unreliable — GNOME may still show it in Alt-Tab.
        # DOCK is what GNOME Shell's own top bar and panels (waybar, polybar) use.
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        
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
        print("[WaylandOverlay] Using DOCK window type (excluded from Alt-Tab/overview)")
    
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
        """Pull the latest mask from the queue and schedule a redraw."""
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

            # Drain mask queue — keep only the most recent mask
            while not self.mask_queue.empty():
                self.current_mask = self.mask_queue.get_nowait()

            self.queue_draw()

        except Exception as e:
            print(f"[WaylandOverlay] Update error: {e}")
            import traceback
            traceback.print_exc()

        return True  # Keep GLib timer alive
    
    def on_draw(self, widget, cr):
        """Paint the segmentation mask as a red semi-transparent overlay using Cairo."""
        try:
            self._draw_count += 1

            # Step 1: clear the entire surface to fully transparent
            cr.set_source_rgba(0, 0, 0, 0)
            cr.set_operator(cairo.OPERATOR_SOURCE)
            cr.paint()

            # Step 2: paint mask in red using OPERATOR_OVER
            if self.current_mask is not None:
                mask = self.current_mask
                h, w = mask.shape

                # Cairo FORMAT_ARGB32 is premultiplied ARGB stored in memory as
                # [B, G, R, A] on little-endian.  For red at ~70% opacity:
                #   alpha = 178, R_pre = 255*178//255 = 178, G=B=0
                alpha = 178
                img = np.zeros((h, w, 4), dtype=np.uint8)
                img[mask == 1, 2] = alpha   # R (premultiplied)
                img[mask == 1, 3] = alpha   # A

                stride = cairo.ImageSurface.format_stride_for_width(
                    cairo.FORMAT_ARGB32, w
                )
                surface = cairo.ImageSurface.create_for_data(
                    bytearray(img.tobytes()),
                    cairo.FORMAT_ARGB32, w, h, stride
                )
                cr.set_operator(cairo.OPERATOR_OVER)
                cr.set_source_surface(surface, 0, 0)
                cr.paint()

            if self._draw_count == 1:
                print("[WaylandOverlay] First draw complete — desktop shows through transparent regions")

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
