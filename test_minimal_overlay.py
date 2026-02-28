#!/usr/bin/env python3
"""
Minimal overlay test - just show a red rectangle to verify display works.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import cairo
import sys

class MinimalOverlay(Gtk.Window):
    def __init__(self):
        super().__init__()
        
        # Get screen size
        display = Gdk.Display.get_default()
        monitor = display.get_monitor(0)
        geo = monitor.get_geometry()
        
        print(f"Screen: {geo.width}x{geo.height} at ({geo.x}, {geo.y})")
        
        self.screen_width = geo.width
        self.screen_height = geo.height
        self.rect_x = 0
        
        # Setup window
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        
        # Enable transparency BEFORE showing
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
            print("RGBA enabled - transparency supported")
        else:
            print("WARNING: No RGBA visual - transparency may not work")
        
        self.set_app_paintable(True)
        self.connect('draw', self.on_draw)
        self.set_default_size(self.screen_width, self.screen_height)
        
        # Show
        self.show_all()
        self.fullscreen()
        
        # Animation timer
        GLib.timeout_add(50, self.animate)
        
        print("Overlay created - you should see a red rectangle moving over your desktop!")
        print("The desktop should be visible through the window (not black background)")
    
    def animate(self):
        self.rect_x += 20
        if self.rect_x > self.screen_width:
            self.rect_x = 0
            print("Rectangle reset - desktop should be visible through overlay")
        self.queue_draw()
        return True
    
    def on_draw(self, widget, cr):
        # CRITICAL: Clear with fully transparent background
        # This makes desktop show through
        cr.save()
        cr.set_source_rgba(0, 0, 0, 0)  # Fully transparent
        cr.set_operator(cairo.OPERATOR_SOURCE)  # Replace mode
        cr.paint()
        cr.restore()
        
        # Draw semi-transparent red rectangle
        huge_width = int(self.screen_width * 0.4)
        cr.set_source_rgba(1.0, 0.0, 0.0, 0.7)  # Semi-transparent red
        cr.set_operator(cairo.OPERATOR_OVER)  # Normal blending
        cr.rectangle(self.rect_x, 0, huge_width, self.screen_height)
        cr.fill()
        
        return False

if __name__ == '__main__':
    print("Minimal overlay test - press Ctrl+C to exit")
    print("Expected: Red rectangle moves across screen, desktop visible through window")
    overlay = MinimalOverlay()
    try:
        Gtk.main()
    except KeyboardInterrupt:
        print("\nExiting")
        sys.exit(0)
