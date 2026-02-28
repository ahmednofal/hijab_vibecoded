#!/usr/bin/env python3
"""
Screenshot-based overlay - captures desktop, composites overlay, displays result.
This works around compositor transparency issues.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf
import cairo
import numpy as np
from PIL import Image
import subprocess
import sys

class ScreenshotOverlay(Gtk.Window):
    def __init__(self):
        super().__init__()
        
        # Get screen size
        display = Gdk.Display.get_default()
        monitor = display.get_monitor(0)
        geo = monitor.get_geometry()
        
        self.screen_width = geo.width
        self.screen_height = geo.height
        self.rect_x = 0
        
        print(f"Screen: {self.screen_width}x{self.screen_height}")
        
        # Capture initial desktop background
        self.background = self.capture_desktop()
        
        # Setup window
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        
        self.set_app_paintable(True)
        self.connect('draw', self.on_draw)
        self.set_default_size(self.screen_width, self.screen_height)
        
        # Show
        self.show_all()
        self.fullscreen()
        
        # Refresh background periodically and animate
        GLib.timeout_add(50, self.animate)  # 20 FPS animation
        GLib.timeout_add(1000, self.refresh_background)  # Refresh background every 1s
        
        print("Screenshot-based overlay created")
        print("Background refreshes every second")
        print("Red rectangle should overlay on top of desktop")
    
    def capture_desktop(self):
        """Capture current desktop screenshot."""
        try:
            # Hide self temporarily
            was_visible = self.get_visible()
            if was_visible:
                self.hide()
                GLib.usleep(100000)  # Wait 100ms for hide to take effect
            
            # Capture with grim or gnome-screenshot
            result = subprocess.run(
                ['gnome-screenshot', '-f', '/tmp/overlay_bg.png'],
                capture_output=True,
                timeout=1
            )
            
            if was_visible:
                self.show_all()
            
            if result.returncode == 0:
                img = Image.open('/tmp/overlay_bg.png')
                # Resize if needed
                if img.size != (self.screen_width, self.screen_height):
                    img = img.resize((self.screen_width, self.screen_height))
                return np.array(img)
            
        except Exception as e:
            print(f"Screenshot capture failed: {e}")
        
        # Fallback: black background
        return np.zeros((self.screen_height, self.screen_width, 3), dtype=np.uint8)
    
    def refresh_background(self):
        """Periodically refresh the background screenshot."""
        self.background = self.capture_desktop()
        return True  # Continue timer
    
    def animate(self):
        """Animate the red rectangle."""
        self.rect_x += 20
        if self.rect_x > self.screen_width:
            self.rect_x = 0
        self.queue_draw()
        return True
    
    def on_draw(self, widget, cr):
        """Draw background + red overlay."""
        try:
            # Draw background screenshot
            if self.background is not None:
                # Convert numpy array to cairo surface
                height, width = self.background.shape[:2]
                
                # Create ImageSurface from numpy array
                if self.background.shape[2] == 3:
                    # Add alpha channel
                    bgra = np.dstack([self.background, np.ones((height, width), dtype=np.uint8) * 255])
                else:
                    bgra = self.background
                
                # Convert RGB to BGR for cairo (actually BGRA)
                bgra_swapped = bgra[:, :, [2, 1, 0, 3]].copy()
                
                surface = cairo.ImageSurface.create_for_data(
                    bgra_swapped, cairo.FORMAT_RGB24, width, height
                )
                cr.set_source_surface(surface, 0, 0)
                cr.paint()
            
            # Draw semi-transparent red rectangle on top
            huge_width = int(self.screen_width * 0.5)
            cr.set_source_rgba(1.0, 0.0, 0.0, 0.5)  # Semi-transparent red
            cr.rectangle(self.rect_x, 0, huge_width, self.screen_height)
            cr.fill()
            
        except Exception as e:
            print(f"Draw error: {e}")
            import traceback
            traceback.print_exc()
        
        return False

if __name__ == '__main__':
    print("Screenshot-based overlay test")
    print("This composites red overlay onto desktop screenshot")
    print("Press Ctrl+C to exit")
    
    overlay = ScreenshotOverlay()
    try:
        Gtk.main()
    except KeyboardInterrupt:
        print("\nExiting")
        sys.exit(0)
