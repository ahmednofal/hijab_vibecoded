"""Transparent overlay window using GTK3 with layer-shell for Wayland.

On Wayland, uses gtk-layer-shell to place overlay on OVERLAY layer,
which is automatically excluded from screenshots by gnome-screenshot.

On X11, falls back to standard GTK window with appropriate hints.
"""

import os
import sys
import numpy as np
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')

from gi.repository import Gtk, Gdk, GLib, GdkPixbuf
from multiprocessing import Queue

# Try to import layer-shell for Wayland
try:
    gi.require_version('GtkLayerShell', '0.1')
    from gi.repository import GtkLayerShell
    HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    HAS_LAYER_SHELL = False
    print("[Overlay] gtk-layer-shell not available, using standard window")


def is_wayland():
    """Check if running on Wayland."""
    return os.environ.get('XDG_SESSION_TYPE') == 'wayland'


class TransparentOverlay(Gtk.Window):
    """Fullscreen transparent overlay that renders person masks in red."""
    
    def __init__(self, mask_queue: Queue, capture_queue: Queue = None, 
                 screen_index: int = 0, overlay_id_queue: Queue = None):
        super().__init__(title="Hijab Overlay")
        
        self.mask_queue = mask_queue
        self.capture_queue = capture_queue
        self.overlay_id_queue = overlay_id_queue
        self.screen_index = screen_index
        
        self.current_mask = None
        self.current_frame = None
        self.rect_x_offset = 0
        self.rect_width = 200
        self.screen_width = 1920
        self.screen_height = 1080
        
        self._first_frame_received = False
        
        self.init_ui()
        
        # Update timer (~30 FPS)
        GLib.timeout_add(33, self.update_mask)
        
        print("[Overlay] GTK3 overlay initialized")
    
    def init_ui(self):
        """Initialize the overlay window."""
        # Get display and monitor info
        display = Gdk.Display.get_default()
        
        n_monitors = display.get_n_monitors()
        if self.screen_index < n_monitors:
            monitor = display.get_monitor(self.screen_index)
            geom = monitor.get_geometry()
            self.screen_width = geom.width
            self.screen_height = geom.height
            print(f"[Overlay] Using monitor {self.screen_index}: {self.screen_width}x{self.screen_height}")
        else:
            print(f"[Overlay] Monitor {self.screen_index} not found, using defaults")
        
        # Setup layer-shell on Wayland for auto-exclusion from screenshots
        if is_wayland() and HAS_LAYER_SHELL:
            print("[Overlay] Setting up layer-shell (Wayland)")
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)
            
            # Select specific monitor
            if self.screen_index < n_monitors:
                monitor = display.get_monitor(self.screen_index)
                GtkLayerShell.set_monitor(self, monitor)
            
            print("[Overlay] Layer-shell configured - overlay excluded from screenshots")
        else:
            # Standard window setup for X11
            print("[Overlay] Using standard GTK window (X11 mode)")
            self.set_decorated(False)
            self.set_skip_taskbar_hint(True)
            self.set_skip_pager_hint(True)
            self.set_keep_above(True)
            self.set_default_size(self.screen_width, self.screen_height)
            self.move(0, 0)
        
        # Enable transparency
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.set_app_paintable(True)
        
        # Connect draw signal
        self.connect('draw', self.on_draw)
        
        # Make click-through (input passthrough)
        self.set_accept_focus(False)
        self.connect('realize', self._on_realize)
        
        # Set size
        self.set_default_size(self.screen_width, self.screen_height)
    
    def _on_realize(self, widget):
        """Set input region to empty for click-through."""
        window = self.get_window()
        if window:
            # Create empty input region (all clicks pass through)
            region = Gdk.cairo_region_create_rectangle(Gdk.Rectangle())
            window.input_shape_combine_region(region, 0, 0)
            print("[Overlay] Click-through enabled")
        
        # Send window ID to capture worker (for X11 exclusion)
        if self.overlay_id_queue is not None:
            try:
                window_id = window.get_xid() if hasattr(window, 'get_xid') else 0
                self.overlay_id_queue.put(window_id)
                print(f"[Overlay] Sent window ID: {window_id}")
            except Exception as e:
                print(f"[Overlay] Could not get window ID: {e}")
                self.overlay_id_queue.put(0)
    
    def update_mask(self):
        """Update mask and frame from queues."""
        try:
            # Get latest mask
            while self.mask_queue and not self.mask_queue.empty():
                try:
                    self.current_mask = self.mask_queue.get_nowait()
                except:
                    break
            
            # Get captured frame
            if self.capture_queue is not None:
                got_frame = False
                while not self.capture_queue.empty():
                    try:
                        self.current_frame = self.capture_queue.get_nowait()
                        got_frame = True
                    except:
                        break
                
                if got_frame and not self._first_frame_received:
                    self._first_frame_received = True
                    print(f"[Overlay] First frame received! Shape: {self.current_frame.shape}")
                    mean_val = self.current_frame.mean()
                    print(f"[Overlay] Frame mean: {mean_val:.2f} (0=black, 255=white)")
            
            # Move rectangle
            self.rect_x_offset += 5
            if self.rect_x_offset > self.screen_width:
                self.rect_x_offset = 0
            
            # Trigger redraw
            self.queue_draw()
            
        except Exception as e:
            print(f"[Overlay] Update error: {e}")
        
        return True  # Continue timer
    
    def on_draw(self, widget, cr):
        """Draw the overlay content."""
        try:
            width = self.get_allocated_width()
            height = self.get_allocated_height()
            
            # Clear with transparency
            cr.set_operator(1)  # CAIRO_OPERATOR_SOURCE
            cr.set_source_rgba(0, 0, 0, 0)
            cr.paint()
            
            cr.set_operator(0)  # CAIRO_OPERATOR_CLEAR then OVER
            cr.set_operator(2)  # CAIRO_OPERATOR_OVER
            
            # Draw captured frame as background
            if self.current_frame is not None:
                self._draw_frame(cr, width, height)
            else:
                # Draw dark gray background
                cr.set_source_rgb(0.15, 0.15, 0.15)
                cr.paint()
            
            # Draw moving red rectangle
            cr.set_source_rgba(1.0, 0.0, 0.0, 0.7)  # Red with 70% opacity
            cr.rectangle(self.rect_x_offset, 0, self.rect_width, height)
            cr.fill()
            
        except Exception as e:
            print(f"[Overlay] Draw error: {e}")
        
        return False
    
    def _draw_frame(self, cr, width, height):
        """Draw the captured frame as background."""
        frame = self.current_frame
        
        # Get frame dimensions
        h, w = frame.shape[:2]
        channels = frame.shape[2] if len(frame.shape) > 2 else 1
        
        # Ensure RGB format
        if channels == 4:
            frame = frame[:, :, :3]
        
        # Create pixbuf from numpy array
        pixbuf = GdkPixbuf.Pixbuf.new_from_data(
            frame.tobytes(),
            GdkPixbuf.Colorspace.RGB,
            False,  # no alpha
            8,      # bits per sample
            w, h,
            w * 3   # rowstride
        )
        
        # Scale to window size
        scaled = pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.NEAREST)
        
        # Draw to cairo context
        Gdk.cairo_set_source_pixbuf(cr, scaled, 0, 0)
        cr.paint()


def run_overlay(mask_queue: Queue, capture_queue: Queue = None, 
                overlay_id_queue: Queue = None, screen_index: int = 0):
    """
    Run the overlay window.
    
    Args:
        mask_queue: Queue to receive segmentation masks from
        capture_queue: Queue to receive captured frames from  
        overlay_id_queue: Queue to send overlay window ID to capture worker
        screen_index: Which monitor to display on (0=primary)
    """
    print("[Overlay] Starting GTK3 overlay")
    print(f"[Overlay] Wayland: {is_wayland()}, Layer-shell: {HAS_LAYER_SHELL}")
    
    window = TransparentOverlay(mask_queue, capture_queue, screen_index, overlay_id_queue)
    window.connect('destroy', Gtk.main_quit)
    window.show_all()
    
    # Fullscreen on X11 (layer-shell handles this on Wayland)
    if not is_wayland() or not HAS_LAYER_SHELL:
        window.fullscreen()
    
    Gtk.main()
