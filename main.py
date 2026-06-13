#!/usr/bin/env python3
"""
Hijab by Copilot - Real-time person overlay using semantic segmentation.

Captures the screen, detects people, and overlays them
with a red semi-transparent hue in real-time.

Windows-only version.
"""

import sys
import signal
from multiprocessing import Process, Queue, Event

from capture_windows import capture_worker_windows, list_windows_monitors
from overlay_windows import run_overlay_windows
from segmentation import segmentation_worker


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
    
    def select_monitor(self):
        """Detect monitors using MSS and select the primary one."""
        print("[Main] Detecting monitors (Windows)...")
        monitors = list_windows_monitors()
        
        if not monitors:
            print("[Main] WARNING: No monitors detected, using primary (0)")
            return 0, None
        
        internal_monitor = 0
        mon = monitors[0]
        internal_geometry = (mon['left'], mon['top'], mon['width'], mon['height'])
        
        print(f"[Main] Using monitor {internal_monitor}: {mon['width']}x{mon['height']}")
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
        
        # TESTING MODE: Moving rectangle to test feedback loop
        print("[Main] SEGMENTATION MODE:")
        print("[Main] - Capturing screen → segmenting → overlaying")

        # Start capture worker
        print("[Main] Starting capture worker...")
        self.capture_process = Process(
            target=capture_worker_windows,
            args=(self.capture_queue, self.stop_event, monitor_index),
            daemon=True
        )
        self.capture_process.start()

        # Start segmentation worker
        print("[Main] Starting segmentation worker...")
        self.segmentation_process = Process(
            target=segmentation_worker,
            args=(self.capture_queue, self.mask_queue, self.stop_event),
            kwargs={'scale_factor': 0.5},
            daemon=True
        )
        self.segmentation_process.start()
        
        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        print("[Main] Starting overlay window...")
        print()
        
        # Start overlay window
        try:
            print("[Main] Using Windows PyQt6 overlay")
            run_overlay_windows(self.mask_queue, monitor_index=monitor_index)
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
        print(f"[Main] Platform: Windows")
        print("[Main] Using MSS for screen capture")
        print()


def main():
    """Application entry point."""
    app = HijabOverlay()
    app.start()


if __name__ == '__main__':
    main()
