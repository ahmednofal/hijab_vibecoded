#!/usr/bin/env python3
"""
Hijab by Copilot - Real-time person overlay using semantic segmentation.

This application captures the screen, detects people, and overlays them
with a red semi-transparent hue in real-time.
"""

import sys
import signal
from multiprocessing import Process, Queue, Event

from capture import capture_worker
# Temporarily commented out to bypass segmentation issues
# from segmentation import segmentation_worker
from overlay import run_overlay


class HijabOverlay:
    """Main application orchestrator."""
    
    def __init__(self):
        # Queues for inter-process communication
        self.capture_queue = Queue(maxsize=2)
        self.mask_queue = Queue(maxsize=2)
        
        # Event to signal stop
        self.stop_event = Event()
        
        # Processes
        self.capture_process = None
        self.segmentation_process = None
    
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
        
        # TESTING MODE: Enable capture to test if we're capturing our own overlay
        print("[Main] TESTING MODE: Starting capture worker to test feedback loop")
        print("[Main] If the red gets darker over time, we're capturing our own overlay (BAD)")
        print("[Main] If the red stays the same, we're NOT capturing the overlay (GOOD)")
        
        # Start capture worker process
        print("[Main] Starting capture worker...")
        self.capture_process = Process(
            target=capture_worker,
            args=(self.capture_queue, self.stop_event, 0),  # Monitor 0 = primary
            daemon=True
        )
        self.capture_process.start()
        
        # Keep segmentation disabled for now
        # We'll pass captured frames directly to overlay for visualization
        
        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        print("[Main] Starting overlay window...")
        print()
        
        # Run overlay in main thread (Qt requires main thread)
        try:
            run_overlay(self.mask_queue)
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
