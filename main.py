#!/usr/bin/env python3
"""
Hijab by Copilot - Real-time person overlay using semantic segmentation.

This application captures the screen, detects people, and overlays them
with a red semi-transparent hue in real-time.
"""

import sys
import signal
import os
from multiprocessing import Process, Queue, Event
from PyQt6.QtWidgets import QApplication

from capture import capture_worker, is_wayland
# Import overlay types
from overlay import run_overlay as run_overlay_qt
from overlay_gtk3 import run_overlay as run_overlay_gtk3
# Temporarily commented out to bypass segmentation issues
# from segmentation import segmentation_worker


class HijabOverlay:
    """Main application orchestrator."""
    
    def __init__(self):
        # Queues for inter-process communication
        self.capture_queue = Queue(maxsize=2)
        self.mask_queue = Queue(maxsize=2)
        self.overlay_id_queue = Queue(maxsize=1)  # For sending overlay window ID
        self.hide_signal_queue = Queue(maxsize=2)  # For capture worker to signal hide/show
        
        # Event to signal stop
        self.stop_event = Event()
        
        # Processes
        self.capture_process = None
        self.segmentation_process = None
    
    def select_monitor(self):
        """Detect monitors and select the internal one (not HP external).
        
        Returns:
            Tuple of (monitor_index, geometry) where geometry is (x, y, width, height)
        """
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        
        screens = app.screens()
        print(f"[Main] Detected {len(screens)} monitor(s):")
        
        internal_monitor = None
        internal_geometry = None
        for i, screen in enumerate(screens):
            geom = screen.geometry()
            name = screen.name()
            manufacturer = screen.manufacturer()
            model = screen.model()
            
            info = f"  [{i}] {name}: {geom.width()}x{geom.height()}"
            if manufacturer:
                info += f" ({manufacturer}"
            if model:
                info += f" {model}" if manufacturer else f" ({model}"
            if manufacturer or model:
                info += ")"
            
            print(info)
            
            # Skip HP external monitors
            is_hp = 'HP' in str(manufacturer).upper() or 'HP' in str(model).upper() or 'HP' in str(name).upper()
            
            if not is_hp and internal_monitor is None:
                internal_monitor = i
                internal_geometry = (geom.x(), geom.y(), geom.width(), geom.height())
                print(f"       ^ Internal monitor (will use this)")
            elif is_hp:
                print(f"       ^ HP external (skipping)")
        
        if internal_monitor is None:
            print("[Main] WARNING: Could not identify internal monitor, using primary (0)")
            internal_monitor = 0
            if screens:
                geom = screens[0].geometry()
                internal_geometry = (geom.x(), geom.y(), geom.width(), geom.height())
        
        return internal_monitor, internal_geometry
    
    def start(self):
        """Start all worker processes and the overlay."""
        print("=" * 60)
        print("Hijab by Copilot - Real-time Person Overlay")
        print("=" * 60)
        print("Starting application...")
        print("Press Ctrl+C to exit")
        print()
        
        # Check system requirements
        self.check_requirements()
        
        # Select monitor (internal, not HP external)
        monitor_index, monitor_geometry = self.select_monitor()
        print(f"[Main] Using monitor {monitor_index}")
        if monitor_geometry:
            print(f"[Main] Monitor geometry: x={monitor_geometry[0]}, y={monitor_geometry[1]}, {monitor_geometry[2]}x{monitor_geometry[3]}")
        print()
        
        # Capture background BEFORE showing overlay (for Wayland)
        background_image = None
        if is_wayland() and monitor_geometry:
            print("[Main] Capturing background before showing overlay...")
            from capture import capture_wayland_gnome
            background_image = capture_wayland_gnome(monitor_geometry)
            if background_image is not None:
                print(f"[Main] Background captured: {background_image.shape}")
            else:
                print("[Main] WARNING: Failed to capture background")
        
        # TESTING MODE: Moving rectangle to test feedback loop
        print("[Main] OVERLAY TEST:")
        print("[Main] - Rectangle moves left to right")
        print("[Main] - Background is pre-captured (static)")
        print("[Main] - Red bar should move over the frozen background")
        
        # Start capture worker (for future live capture / verification)
        print("[Main] Starting capture worker...")
        self.capture_process = Process(
            target=capture_worker,
            args=(self.capture_queue, self.stop_event, monitor_index, self.overlay_id_queue, monitor_geometry, self.hide_signal_queue),
            daemon=True
        )
        self.capture_process.start()
        
        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        print("[Main] Starting overlay window...")
        print()
        
        # Use GTK3 on Wayland with pre-captured background
        try:
            if is_wayland():
                print("[Main] Using GTK3 overlay with pre-captured background")
                run_overlay_gtk3(self.mask_queue, self.capture_queue, self.overlay_id_queue, monitor_index, self.hide_signal_queue, background_image)
            else:
                print("[Main] Using PyQt6 overlay")
                run_overlay_qt(self.mask_queue, self.capture_queue, self.overlay_id_queue, monitor_index, self.hide_signal_queue)
        except KeyboardInterrupt:
            print("\n[Main] Keyboard interrupt received")
        except Exception as e:
            print(f"[Main] Error in overlay: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop all worker processes."""
        print("\n[Main] Stopping application...")
        
        # Signal workers to stop
        self.stop_event.set()
        
        # Wait for processes to terminate
        if self.capture_process and self.capture_process.is_alive():
            print("[Main] Waiting for capture process...")
            self.capture_process.join(timeout=2)
            if self.capture_process.is_alive():
                print("[Main] Terminating capture process...")
                self.capture_process.terminate()
        
        if self.segmentation_process and self.segmentation_process.is_alive():
            print("[Main] Waiting for segmentation process...")
            self.segmentation_process.join(timeout=2)
            if self.segmentation_process.is_alive():
                print("[Main] Terminating segmentation process...")
                self.segmentation_process.terminate()
        
        print("[Main] Application stopped")
    
    def _signal_handler(self, signum, frame):
        """Handle termination signals."""
        print(f"\n[Main] Received signal {signum}")
        self.stop()
        sys.exit(0)
    
    def check_requirements(self):
        """Check if system meets requirements."""
        import os
        
        # Check if running on X11
        session_type = os.environ.get('XDG_SESSION_TYPE', 'unknown')
        print(f"[Main] Session type: {session_type}")
        
        if session_type == 'wayland':
            print("[Main] WARNING: Running on Wayland. This application requires X11.")
            print("[Main] Please switch to X11 session or this may not work correctly.")
        elif session_type == 'x11':
            print("[Main] X11 detected - good!")
        else:
            print(f"[Main] WARNING: Unknown session type: {session_type}")
        
        # Check for compositor (optional but recommended)
        try:
            from Xlib import X, display
            d = display.Display()
            screen = d.screen()
            
            # Check for compositor atom
            atom = d.intern_atom(f'_NET_WM_CM_S{screen.root.get_full_property(d.intern_atom("_NET_WM_CM_S0"), X.AnyPropertyType).value[0] if screen.root.get_full_property(d.intern_atom("_NET_WM_CM_S0"), X.AnyPropertyType) else 0}')
            print("[Main] Compositor check: OK (transparency should work)")
        except:
            print("[Main] WARNING: Could not detect compositor. Transparency may not work.")
        
        print()


def main():
    """Application entry point."""
    app = HijabOverlay()
    app.start()


if __name__ == '__main__':
    main()
