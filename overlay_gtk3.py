"""Transparent overlay window using GTK3 with Cairo for proper Wayland transparency."""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import cairo
import numpy as np
from multiprocessing import Queue
import sys


class TransparentOverlay(Gtk.Window):
    """Fullscreen transparent overlay that renders person masks in red."""
    
    def __init__(self, mask_queue: Queue, capture_queue: Queue = None, screen_index: int = 0, background_image=None):
        super().__init__(title='Hijab Overlay')
        
        self.mask_queue = mask_queue
        self.capture_queue = capture_queue
        self.screen_index = screen_index
        self.current_mask = None
        self.current_frame = None
        self.rect_x_offset = 0
        self.rect_width = 200
        self.screen_width = 1920
        self.screen_height = 1080
        
        self._init_transparency()
        self._init_window()
        
        # Animation timer
        GLib.timeout_add(33, self._on_tick)  # ~30 FPS
        
        print("[Overlay] GTK3 transparent overlay initialized")
    
    def _init_background_surface(self):
        """Convert background image to Cairo surface."""
        if self.background_image is not None:
            try:
                import numpy as np
                h, w = self.background_image.shape[:2]
                
                # Ensure RGBA format
                if self.background_image.shape[2] == 3:
                    # Convert RGB to RGBA
                    rgba = np.zeros((h, w, 4), dtype=np.uint8)
                    rgba[:, :, 0] = self.background_image[:, :, 2]  # B
                    rgba[:, :, 1] = self.background_image[:, :, 1]  # G
                    rgba[:, :, 2] = self.background_image[:, :, 0]  # R
                    rgba[:, :, 3] = 255  # A
                else:
                    rgba = self.background_image
                
                self.background_surface = cairo.ImageSurface.create_for_data(
                    rgba, cairo.FORMAT_ARGB32, w, h
                )
                print(f"[Overlay] Background surface created: {w}x{h}")
            except Exception as e:
                print(f"[Overlay] Failed to create background surface: {e}")
        
        # Animation timer
        GLib.timeout_add(33, self._on_tick)  # ~30 FPS
        
        print("[Overlay] GTK3 transparent overlay initialized")
    
    def _init_transparency(self):
        """Set up RGBA transparency."""
        self.set_app_paintable(True)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
            print("[Overlay] RGBA visual: enabled")
        else:
            print("[Overlay] WARNING: RGBA visual not available")
    
    def _init_window(self):
        """Configure window properties."""
        # Get display and monitor info
        display = Gdk.Display.get_default()
        n_monitors = display.get_n_monitors()
        print(f"[Overlay] Detected {n_monitors} monitors")
        
        self.target_monitor = None
        if self.screen_index < n_monitors:
            self.target_monitor = display.get_monitor(self.screen_index)
            geometry = self.target_monitor.get_geometry()
            self.screen_width = geometry.width
            self.screen_height = geometry.height
            self.monitor_x = geometry.x
            self.monitor_y = geometry.y
            print(f"[Overlay] Target monitor {self.screen_index}: {self.screen_width}x{self.screen_height} at ({self.monitor_x}, {self.monitor_y})")
        else:
            self.monitor_x = 0
            self.monitor_y = 0
        
        # Window properties - make it invisible to window manager
        self.set_decorated(False)
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)  # Act like a dock/panel, not a window
        self.set_keep_above(True)
        self.set_accept_focus(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        
        # Position and size manually (don't use fullscreen)
        self.move(self.monitor_x, self.monitor_y)
        self.resize(self.screen_width, self.screen_height)
        
        # Make click-through (input passthrough)
        self.set_can_focus(False)
        
        # Connect draw handler
        self.connect('draw', self._on_draw)
        self.connect('realize', self._on_realize)
    
    def _on_realize(self, widget):
        """Called when window is realized - set input passthrough and transparency."""
        window = self.get_window()
        if window:
            # Set window background to None for true transparency
            window.set_background_rgba(Gdk.RGBA(0, 0, 0, 0))
            
            # Create empty input region for click-through
            region = cairo.Region()
            window.input_shape_combine_region(region, 0, 0)
            print("[Overlay] Input passthrough enabled")
            
            # Get window ID
            # Note: On Wayland this may return 0 or a placeholder
            try:
                xid = window.get_xid()
                print(f"[Overlay] Window XID: {xid}")
            except:
                print("[Overlay] Window XID not available (Wayland)")
    
    def _on_tick(self):
        """Timer callback - update animation and check queues."""
        try:
            # Check mask queue
            while not self.mask_queue.empty():
                self.current_mask = self.mask_queue.get_nowait()
            
            # Check capture queue (for debugging)
            if self.capture_queue is not None:
                got_frame = False
                while not self.capture_queue.empty():
                    self.current_frame = self.capture_queue.get_nowait()
                    got_frame = True
                
                if got_frame and not hasattr(self, '_first_frame_logged'):
                    self._first_frame_logged = True
                    mean_val = np.mean(self.current_frame)
                    print(f"[Overlay] First frame: {self.current_frame.shape}, mean={mean_val:.1f}")
            
            # Animate rectangle
            self.rect_x_offset += 5
            if self.rect_x_offset > self.screen_width:
                self.rect_x_offset = 0
            
            # Trigger redraw
            self.queue_draw()
        except Exception as e:
            print(f"[Overlay] Tick error: {e}")
        
        return True  # Keep timer running
    
    def _on_draw(self, widget, cr):
        """Draw handler - fully transparent with only red rectangle visible."""
        # Clear to fully transparent
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        
        # Draw only the red rectangle
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_source_rgba(1.0, 0.0, 0.0, 0.7)  # Red with 70% opacity
        cr.rectangle(self.rect_x_offset, 0, self.rect_width, self.screen_height)
        cr.fill()
        
        return False


def run_overlay(mask_queue: Queue, capture_queue: Queue = None, overlay_id_queue: Queue = None, 
                screen_index: int = 0, hide_signal_queue: Queue = None, background_image=None):
    """
    Run the GTK3 overlay window.
    
    Args:
        mask_queue: Queue to receive segmentation masks from
        capture_queue: Queue to receive captured frames from
        overlay_id_queue: Queue to send overlay window ID to capture worker
        screen_index: Which monitor to display overlay on (0=primary)
        hide_signal_queue: Not used for GTK3 (placeholder for compatibility)
        background_image: Pre-captured background image to display
    """
    print("[Overlay] Starting GTK3 overlay application")
    
    overlay = TransparentOverlay(mask_queue, capture_queue, screen_index, background_image)
    overlay.connect('destroy', Gtk.main_quit)
    
    # Show the overlay (positioned and sized in init_window)
    overlay.show_all()
    print(f"[Overlay] Overlay shown on monitor {screen_index}")
    
    # Send window ID if requested (may not work on pure Wayland)
    if overlay_id_queue is not None:
        try:
            window = overlay.get_window()
            if window:
                xid = window.get_xid()
                overlay_id_queue.put(xid)
                print(f"[Overlay] Sent window ID {xid}")
        except Exception as e:
            overlay_id_queue.put(0)  # Send 0 if we can't get XID
            print(f"[Overlay] Could not get window ID: {e}")
    
    Gtk.main()


if __name__ == '__main__':
    # Test standalone
    from multiprocessing import Queue
    mask_q = Queue()
    run_overlay(mask_q)
