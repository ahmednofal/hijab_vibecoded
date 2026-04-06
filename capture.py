"""Screen capture worker - supports both X11 and Wayland."""

import os
import time
import subprocess
import tempfile
from multiprocessing import Queue, Event
from pathlib import Path
import numpy as np
from PIL import Image


def is_wayland():
    """Check if running on Wayland."""
    return os.environ.get('XDG_SESSION_TYPE') == 'wayland'


def _load_capture_png(tmp_path, monitor_region):
    """Load a captured PNG file into a numpy RGB array, optionally cropped."""
    img = Image.open(tmp_path)
    frame = np.array(img)
    if len(frame.shape) > 2 and frame.shape[2] == 4:
        frame = frame[:, :, :3]
    if monitor_region:
        x, y, w, h = monitor_region
        frame = frame[y:y+h, x:x+w].copy()
    return frame


def capture_wayland_gnome(monitor_region=None):
    """Capture screen on GNOME Wayland — silent via gdbus, fallback to gnome-screenshot.

    Tries gdbus first (flash=false → no shutter sound/flash).  If the dbus policy
    blocks the call (AccessDenied on some GNOME versions), falls back to
    gnome-screenshot which makes sound but at least produces a valid frame.
    The capture worker disables GNOME event sounds via gsettings before looping,
    so the fallback path is also silent in practice.

    Args:
        monitor_region: Optional (x, y, width, height) to crop to a specific monitor.
    """
    tmp_path = '/tmp/hijab_capture.png'

    # Primary: gdbus direct call — no shutter sound, no flash
    try:
        result = subprocess.run(
            [
                'gdbus', 'call', '--session',
                '--dest', 'org.gnome.Shell',
                '--object-path', '/org/gnome/Shell/Screenshot',
                '--method', 'org.gnome.Shell.Screenshot.Screenshot',
                'false',    # include_cursor
                'false',    # flash=false — suppresses sound & flash
                tmp_path,
            ],
            capture_output=True,
            timeout=3,
        )
        if result.returncode == 0 and Path(tmp_path).exists():
            return _load_capture_png(tmp_path, monitor_region)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback: gnome-screenshot (sound is suppressed by gsettings in capture_worker)
    try:
        result = subprocess.run(
            ['gnome-screenshot', '-f', tmp_path],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0 and Path(tmp_path).exists():
            return _load_capture_png(tmp_path, monitor_region)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None


def capture_wayland_grim(monitor_region=None):
    """Capture screen using grim (works on wlroots/Sway).
    
    Args:
        monitor_region: Optional tuple (x, y, width, height) to crop to specific monitor
    """
    try:
        result = subprocess.run(
            ['grim', '-'],  # Output to stdout
            capture_output=True,
            timeout=2
        )
        
        if result.returncode == 0:
            from io import BytesIO
            img = Image.open(BytesIO(result.stdout))
            frame = np.array(img)
            if len(frame.shape) > 2 and frame.shape[2] == 4:
                frame = frame[:, :, :3]
            
            # Crop to specific monitor region if specified
            if monitor_region:
                x, y, w, h = monitor_region
                frame = frame[y:y+h, x:x+w].copy()
            
            return frame
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    return None


def capture_x11(disp, root, width, height):
    """Capture screen using X11 (traditional method)."""
    from Xlib import X
    
    raw = root.get_image(0, 0, width, height, X.ZPixmap, 0xffffffff)
    
    # Convert to numpy array - X11 returns BGRX format (4 bytes per pixel)
    frame = np.frombuffer(raw.data, dtype=np.uint8)
    frame = frame.reshape(height, width, 4)
    
    # Convert BGRX to RGB
    frame = frame[:, :, [2, 1, 0]].copy()
    
    return frame


def capture_worker(output_queue: Queue, stop_event: Event, monitor_index: int = 0, overlay_id_queue: Queue = None, monitor_geometry: tuple = None, hide_signal_queue: Queue = None):
    """
    Continuously captures the screen and puts frames into the output queue.
    
    Supports both X11 and Wayland (via gnome-screenshot or grim).
    
    Args:
        output_queue: Queue to put captured frames into
        stop_event: Event to signal when to stop capturing
        monitor_index: Which monitor to capture (0 = primary)
        overlay_id_queue: Queue to receive overlay window ID from (for X11 exclusion)
        monitor_geometry: Tuple (x, y, width, height) for the target monitor (for Wayland cropping)
        hide_signal_queue: Queue to signal overlay to hide/show during capture
    """
    print(f"[Capture] Starting capture worker for monitor {monitor_index}")
    
    wayland_mode = is_wayland()
    print(f"[Capture] Session type: {'Wayland' if wayland_mode else 'X11'}")
    
    # Wait for overlay window ID (only needed for X11)
    overlay_window_id = None
    if overlay_id_queue is not None:
        print("[Capture] Waiting for overlay window ID...")
        try:
            overlay_window_id = overlay_id_queue.get(timeout=5)
            print(f"[Capture] Got overlay window ID: {overlay_window_id}")
        except:
            print("[Capture] WARNING: Didn't get overlay window ID")
    
    # Initialize X11 if not on Wayland
    disp = None
    root = None
    width = height = 0
    
    if not wayland_mode:
        try:
            from Xlib import display as xlib_display
            
            disp = xlib_display.Display()
            screen = disp.screen()
            root = screen.root
            width = screen.width_in_pixels
            height = screen.height_in_pixels
            
            print(f"[Capture] X11 screen size: {width}x{height}")
        except Exception as e:
            print(f"[Capture] Failed to initialize X11: {e}")
            print("[Capture] Falling back to Wayland capture methods")
            wayland_mode = True
    
    if wayland_mode:
        # Silence GNOME's camera-shutter event sound.
        # gnome-screenshot triggers the sound via the GNOME Shell compositor event
        # system.  The gdbus direct-call approach is blocked by dbus policy in
        # recent GNOME versions, and no X11-based capture works through XWayland
        # on this compositor.  The only reliable silent fix is to disable GNOME
        # event sounds for the lifetime of this worker process and restore them
        # on exit.  This only affects event sounds (not music/video audio).
        _gnome_sounds_disabled = False
        try:
            r = subprocess.run(
                ['gsettings', 'set', 'org.gnome.desktop.sound', 'event-sounds', 'false'],
                capture_output=True, timeout=2,
            )
            if r.returncode == 0:
                _gnome_sounds_disabled = True
                print("[Capture] GNOME event sounds silenced (will restore on exit)")
        except Exception:
            print("[Capture] WARNING: Could not disable GNOME event sounds — expect shutter noise")

        # Get monitor geometry for cropping - passed in from main process
        monitor_region = monitor_geometry
        if monitor_region:
            print(f"[Capture] Monitor {monitor_index} region: x={monitor_region[0]}, y={monitor_region[1]}, {monitor_region[2]}x{monitor_region[3]}")
        else:
            print("[Capture] No monitor geometry provided, capturing full screen")

        # Detect which Wayland capture method works on this compositor
        print("[Capture] Testing Wayland capture methods...")
        test_frame = capture_wayland_gnome(monitor_region)
        if test_frame is not None:
            print(f"[Capture] Using GNOME dbus capture ({test_frame.shape[1]}x{test_frame.shape[0]})")
            capture_method = 'gnome'
        else:
            test_frame = capture_wayland_grim(monitor_region)
            if test_frame is not None:
                print(f"[Capture] Using grim ({test_frame.shape[1]}x{test_frame.shape[0]})")
                capture_method = 'grim'
            else:
                print("[Capture] ERROR: No working Wayland capture method found!")
                if _gnome_sounds_disabled:
                    subprocess.run(['gsettings', 'set', 'org.gnome.desktop.sound',
                                    'event-sounds', 'true'], capture_output=True, timeout=2)
                return
    else:
        _gnome_sounds_disabled = False

    frame_count = 0
    start_time = time.time()
    error_count = 0
    max_consecutive_errors = 10

    # Wayland captures are slow (~1-2 s each) so we don't try to hide/show the
    # overlay between captures.  In simulation mode there is no feedback loop
    # anyway (mask positions are clock-driven, not frame-driven).
    # For a real CV model: the overlay will appear in captured frames.  The fix
    # is to mask out self.current_mask pixels before inference — the model
    # already classified them in the previous frame.
    capture_delay = 0.05 if wayland_mode else 0.01

    try:
        while not stop_event.is_set():
            try:
                frame = None

                if wayland_mode:
                    if capture_method == 'gnome':
                        frame = capture_wayland_gnome(monitor_region)
                    else:
                        frame = capture_wayland_grim(monitor_region)
                else:
                    # X11: direct Xlib capture — silent, fast
                    frame = capture_x11(disp, root, width, height)

                    # Black out the overlay window's pixel region so the CV
                    # model never sees what we drew (no feedback loop on X11).
                    if overlay_window_id and frame is not None:
                        try:
                            overlay_win = disp.create_resource_object('window', overlay_window_id)
                            geom = overlay_win.get_geometry()
                            x, y, w, h = geom.x, geom.y, geom.width, geom.height
                            x = max(0, x)
                            y = max(0, y)
                            w = min(w, width - x)
                            h = min(h, height - y)
                            if w > 0 and h > 0:
                                frame[y:y+h, x:x+w] = 0
                        except Exception:
                            pass

                if frame is None:
                    raise RuntimeError("Capture returned None")

                try:
                    output_queue.put(frame, block=False)
                    frame_count += 1
                    error_count = 0
                    if frame_count == 1:
                        print(f"[Capture] First frame: {frame.shape[1]}x{frame.shape[0]}")
                except Exception:
                    pass  # Queue full — drop frame

                if frame_count > 0 and frame_count % 50 == 0:
                    elapsed = time.time() - start_time
                    print(f"[Capture] FPS: {frame_count / elapsed:.2f}")
                    frame_count = 0
                    start_time = time.time()

                time.sleep(capture_delay)

            except Exception as e:
                error_count += 1
                print(f"[Capture] Error ({error_count}/{max_consecutive_errors}): {e}")
                if error_count >= max_consecutive_errors:
                    print("[Capture] Too many errors, stopping")
                    break
                time.sleep(0.5)

    finally:
        if _gnome_sounds_disabled:
            subprocess.run(
                ['gsettings', 'set', 'org.gnome.desktop.sound', 'event-sounds', 'true'],
                capture_output=True, timeout=2,
            )
            print("[Capture] GNOME event sounds restored")

    print("[Capture] Capture worker stopped")
