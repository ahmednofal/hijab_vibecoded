"""Screen capture worker - supports both X11 and Wayland."""

import os
import sys
import time
import subprocess
import tempfile
from multiprocessing import Queue, Event
from pathlib import Path
import numpy as np
from PIL import Image

# When started via spawn (not fork) the working directory may not be on sys.path.
# Add it so local imports (capture_pipewire, etc.) resolve correctly.
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)


def is_wayland():
    """Check if running on Wayland."""
    return os.environ.get('XDG_SESSION_TYPE') == 'wayland'


_full_png_size_logged = False  # log the raw screenshot size once for debugging


def _drain_mask(capture_mask_queue):
    """Drain the mask queue and return the latest mask, or None."""
    if capture_mask_queue is None:
        return None
    latest = None
    try:
        while not capture_mask_queue.empty():
            latest = capture_mask_queue.get_nowait()
    except Exception:
        pass
    return latest


def _load_capture_png(tmp_path, monitor_region, total_display_size=None):
    """Load a captured PNG file into a numpy RGB array, cropped to monitor_region.

    The GNOME screenshot is taken at the compositor's physical resolution
    (often 1.25× or 1.5× the logical resolution on HiDPI setups). We must
    scale the logical crop coordinates before slicing, then resize the crop
    back down to the logical monitor dimensions so the rest of the pipeline
    always operates in a consistent coordinate space.

    Args:
        tmp_path:           Path to the PNG file.
        monitor_region:     (x, y, w, h) in *logical* compositor coordinates.
        total_display_size: (total_w, total_h) of the full virtual display in
                            logical coordinates — used to compute the scale
                            factor between screenshot pixels and logical pixels.
    """
    global _full_png_size_logged
    img = Image.open(tmp_path)
    frame = np.array(img)
    if len(frame.shape) > 2 and frame.shape[2] == 4:
        frame = frame[:, :, :3]
    ss_h, ss_w = frame.shape[:2]
    if not _full_png_size_logged:
        _full_png_size_logged = True
        print(f"[Capture] Full screenshot size: {ss_w}x{ss_h}")
        if monitor_region and total_display_size is not None:
            td_w, td_h = total_display_size
            print(f"[Capture] HiDPI scale: {ss_w/td_w:.3f}x {ss_h/td_h:.3f}y "
                  f"(logical {td_w}x{td_h} → screenshot {ss_w}x{ss_h})")
    if monitor_region:
        mx, my, mw, mh = monitor_region
        if total_display_size is not None:
            td_w, td_h = total_display_size
            scale_x = ss_w / td_w
            scale_y = ss_h / td_h
            cx = int(mx * scale_x)
            cy = int(my * scale_y)
            cw = int(mw * scale_x)
            ch = int(mh * scale_y)
            cx = min(cx, ss_w);  cw = min(cw, ss_w - cx)
            cy = min(cy, ss_h);  ch = min(ch, ss_h - cy)
            cropped = frame[cy:cy+ch, cx:cx+cw].copy()
            # Resize back to logical dimensions so the pipeline is coordinate-stable
            if cw != mw or ch != mh:
                pil = Image.fromarray(cropped).resize((mw, mh), Image.LANCZOS)
                cropped = np.array(pil)
            frame = cropped
        else:
            # No scale info — assume screenshot is at logical resolution (1:1)
            frame = frame[my:my+mh, mx:mx+mw].copy()
    return frame


def _capture_clean_frame(pw_capture, request_clean_event, overlay_clear_event):
    """Capture a PipeWire frame while the overlay is fully transparent.

    Coordinates with the overlay process via shared Events:
    1. Asks the overlay to stop painting (go transparent).
    2. Waits for the overlay to confirm.
    3. Waits for 2 new PipeWire frames (ensures compositor rendered
       the transparent state).
    4. Grabs the clean frame and signals the overlay to resume.

    Returns the clean frame (numpy RGB array) or None on timeout.
    """
    # Disable mask erasure in PipeWire callback — overlay is transparent,
    # so erasing would zero out actual screen content.
    pw_capture._skip_erasure.set()

    # Record current frame sequence before requesting transparent paint
    _, seq_before = pw_capture.get_frame_seq()

    # Ask the overlay to paint transparent
    overlay_clear_event.clear()
    request_clean_event.set()

    # Wait for overlay to confirm it painted transparent (up to 100ms)
    if not overlay_clear_event.wait(timeout=0.1):
        request_clean_event.clear()
        pw_capture._skip_erasure.clear()
        return None

    # Wait for at least 2 new PipeWire frames after the overlay went transparent.
    # Frame 1 may have been composited before the transparent paint took effect.
    # Frame 2 is guaranteed to be clean.
    target_seq = seq_before + 2
    deadline = time.time() + 0.12  # 120ms timeout
    frame = None
    while time.time() < deadline:
        f, seq = pw_capture.get_frame_seq()
        if seq >= target_seq and f is not None:
            frame = f.copy()
            break
        time.sleep(0.005)

    # Resume overlay
    request_clean_event.clear()
    pw_capture._skip_erasure.clear()

    return frame


def capture_wayland_area(x: int, y: int, width: int, height: int) -> np.ndarray | None:
    """Capture a specific screen region via gdbus ScreenshotArea.

    Directly captures the requested rectangle from the compositor — no full-screen
    PNG + crop needed.  Returns a frame resized to (width, height) logical pixels
    so the pipeline is always coordinate-stable regardless of HiDPI scaling.

    Args:
        x, y:          Top-left corner in Wayland compositor logical coordinates.
        width, height: Logical size of the region to capture.
    """
    tmp_path = '/tmp/hijab_capture_area.png'
    try:
        result = subprocess.run(
            [
                'gdbus', 'call', '--session',
                '--dest', 'org.gnome.Shell',
                '--object-path', '/org/gnome/Shell/Screenshot',
                '--method', 'org.gnome.Shell.Screenshot.ScreenshotArea',
                str(x), str(y), str(width), str(height),
                'false',    # flash=false
                tmp_path,
            ],
            capture_output=True,
            timeout=5,
        )
        if result.returncode != 0:
            err = result.stderr.decode(errors='replace').strip()
            print(f"[Capture] ScreenshotArea failed (rc={result.returncode}): {err}")
            return None
        if not Path(tmp_path).exists():
            print("[Capture] ScreenshotArea: no output file")
            return None
        img = Image.open(tmp_path)
        frame = np.array(img)
        if len(frame.shape) > 2 and frame.shape[2] == 4:
            frame = frame[:, :, :3]
        fh, fw = frame.shape[:2]
        print(f"[Capture] ScreenshotArea raw size: {fw}x{fh}")
        # Resize to logical target size if compositor returned at physical scale
        if fw != width or fh != height:
            pil = Image.fromarray(frame).resize((width, height), Image.LANCZOS)
            frame = np.array(pil)
        return frame
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"[Capture] ScreenshotArea exception: {e}")
    return None


def capture_wayland_gnome(monitor_region=None, total_display_size=None):
    """Capture screen on GNOME Wayland — silent via gdbus, fallback to gnome-screenshot."""
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
            return _load_capture_png(tmp_path, monitor_region, total_display_size)
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
            return _load_capture_png(tmp_path, monitor_region, total_display_size)
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


def capture_worker(output_queue: Queue, stop_event: Event, monitor_index: int = 0,
                   overlay_id_queue: Queue = None, monitor_geometry: tuple = None,
                   hide_signal_queue: Queue = None, capture_mask_queue: Queue = None,
                   viewer_queue: Queue = None, total_display_size: tuple = None,
                   request_clean_event=None, overlay_clear_event=None):
    """
    Continuously captures the screen and puts frames into the output queue.

    Before enqueuing each frame, erases any pixels that the overlay drew so the
    CV model never sees the overlay's own output (no feedback loop).

    On X11: overlay region blacked out using the overlay window's XID geometry.
    On Wayland: overlay region blacked out using the latest mask from
                capture_mask_queue (written by the segmentation worker).
                Timing note: gnome-screenshot takes ~2s so the mask will have
                advanced by capture completion. We erase the *current* mask
                position — a slight overestimate that's safer than underestimating.

    Args:
        output_queue:       Queue to put cleaned frames into (read by CV model).
        stop_event:         Multiprocessing Event; worker exits when set.
        monitor_index:      Which monitor to capture.
        overlay_id_queue:   Queue to receive overlay window XID (X11 exclusion).
        monitor_geometry:   (x, y, width, height) of target monitor for cropping.
        hide_signal_queue:  Queue for hide/show signals (unused in current flow).
        capture_mask_queue: Queue(maxsize=1) holding the latest segmentation mask
                            (H×W uint8, values 0/1).  Written by the segmentation
                            worker.  Pixels where mask==1 are zeroed in captured
                            frames before they reach the CV model.
    """
    # The capture subprocess is forked from main.py which already imported GTK
    # (via overlay_gtk3).  After fork, the inherited Wayland socket fd is shared
    # with the parent and becomes invalid for GDK use.  Unsetting WAYLAND_DISPLAY
    # prevents GDK from trying to dispatch Wayland events in this subprocess.
    # D-Bus (DBUS_SESSION_BUS_ADDRESS) and PipeWire use separate sockets and are
    # NOT affected by this — portal and PipeWire will still work correctly.
    os.environ.pop('WAYLAND_DISPLAY', None)
    os.environ['GDK_BACKEND'] = 'x11'   # belt-and-suspenders: force X11 if GDK does init

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
        monitor_region = monitor_geometry
        if monitor_region:
            mx, my, mw, mh = monitor_region
            print(f"[Capture] Monitor {monitor_index} region: x={mx}, y={my}, {mw}x{mh}")
        else:
            mx = my = mw = mh = None
            print("[Capture] No monitor geometry provided, capturing full screen")

        # ── Try PipeWire first (high-fps, no screenshot sound) ─────────────
        pw_capture = None
        capture_method = None
        _gnome_sounds_disabled = False

        from capture_pipewire import is_pipewire_available, PipeWireCapture
        if is_pipewire_available():
            print("[Capture] Trying PipeWire capture...")
            pw = PipeWireCapture(monitor_geometry, total_display_size=total_display_size,
                                 capture_mask_queue=capture_mask_queue)
            if pw.start():
                pw_capture = pw
                capture_method = 'pipewire'
                print("[Capture] PipeWire capture active")
            else:
                print("[Capture] PipeWire setup failed — falling back to gnome-screenshot")

        # ── Fall back to gnome-screenshot ───────────────────────────────────
        if capture_method is None:
            # Silence shutter sound while running
            try:
                r = subprocess.run(
                    ['gsettings', 'set', 'org.gnome.desktop.sound', 'event-sounds', 'false'],
                    capture_output=True, timeout=2,
                )
                if r.returncode == 0:
                    _gnome_sounds_disabled = True
                    print("[Capture] GNOME event sounds silenced (will restore on exit)")
            except Exception:
                print("[Capture] WARNING: Could not disable GNOME event sounds")

            print("[Capture] Testing gnome-screenshot capture methods...")
            test_frame = None

            if monitor_region is not None:
                test_frame = capture_wayland_area(mx, my, mw, mh)
                if test_frame is not None:
                    print(f"[Capture] Using ScreenshotArea ({test_frame.shape[1]}x{test_frame.shape[0]})")
                    capture_method = 'area'

            if test_frame is None:
                test_frame = capture_wayland_gnome(monitor_region, total_display_size)
                if test_frame is not None:
                    print(f"[Capture] Using GNOME dbus full capture ({test_frame.shape[1]}x{test_frame.shape[0]})")
                    capture_method = 'gnome'

            if test_frame is None:
                test_frame = capture_wayland_grim(monitor_region)
                if test_frame is not None:
                    print(f"[Capture] Using grim ({test_frame.shape[1]}x{test_frame.shape[0]})")
                    capture_method = 'grim'

            if test_frame is None:
                print("[Capture] ERROR: No working capture method found!")
                if _gnome_sounds_disabled:
                    subprocess.run(['gsettings', 'set', 'org.gnome.desktop.sound',
                                    'event-sounds', 'true'], capture_output=True, timeout=2)
                return
    else:
        _gnome_sounds_disabled = False
        pw_capture = None

    frame_count = 0
    start_time = time.time()
    error_count = 0
    max_consecutive_errors = 10

    # Clean capture: overlay briefly goes transparent so PipeWire grabs a frame
    # without the red overlay.  Only used for PipeWire (fast enough for the
    # hide-snap-show cycle).  Other capture methods fall back to mask erasure.
    _use_clean_capture = (capture_method == 'pipewire'
                          and request_clean_event is not None
                          and overlay_clear_event is not None)
    _last_clean = 0
    _CLEAN_INTERVAL = 0.5  # seconds between clean captures (2 fps — plenty for person detection)

    if _use_clean_capture:
        # Disable PipeWire-level mask erasure — clean capture provides genuinely
        # overlay-free frames so there's nothing to erase.  This also means
        # get_frame() returns the raw PipeWire frame (with overlay visible),
        # which is correct for the viewer display.
        if pw_capture is not None:
            pw_capture.capture_mask_queue = None
            pw_capture._erase_mask = None
        print("[Capture] Clean capture enabled — overlay will briefly go transparent for each model frame")

    # PipeWire runs its own frame thread — poll at high rate.
    # gnome-screenshot is slow; give it breathing room.
    capture_delay = 0.01 if (capture_method == 'pipewire' or not wayland_mode) else 0.05

    try:
        while not stop_event.is_set():
            try:
                frame = None

                if wayland_mode:
                    if capture_method == 'pipewire' and _use_clean_capture:
                        # ── Clean capture path ──────────────────────────────
                        # The overlay goes transparent briefly; PipeWire grabs
                        # a frame that shows the desktop without our overlay.
                        # The model gets genuinely clean content — no black
                        # rectangles, no residual overlay pixels.
                        frame = pw_capture.get_frame()
                        if frame is None:
                            time.sleep(0.01)
                            continue

                        # Always feed the viewer with the latest frame
                        if viewer_queue is not None:
                            try:
                                viewer_queue.put(frame, block=False)
                            except Exception:
                                pass

                        # Capture clean frame for the model at a controlled rate,
                        # and only when the model queue has room (avoids flickering
                        # when nobody is consuming frames, e.g. simulation mode).
                        now = time.time()
                        if (now - _last_clean >= _CLEAN_INTERVAL
                                and not output_queue.full()):
                            clean = _capture_clean_frame(
                                pw_capture, request_clean_event,
                                overlay_clear_event)
                            _last_clean = now  # always update to avoid rapid retries on failure
                            if clean is not None:
                                try:
                                    output_queue.put(clean, block=False)
                                    frame_count += 1
                                    error_count = 0
                                    if frame_count == 1:
                                        print(f"[Capture] First clean frame: "
                                              f"{clean.shape[1]}x{clean.shape[0]}")
                                except Exception:
                                    pass

                        if frame_count > 0 and frame_count % 50 == 0:
                            elapsed = time.time() - start_time
                            print(f"[Capture] Clean FPS: {frame_count / elapsed:.2f}")
                            frame_count = 0
                            start_time = time.time()

                        time.sleep(capture_delay)
                        continue  # viewer already fed, skip common path below

                    elif capture_method == 'pipewire':
                        # Fallback: PipeWire without clean capture events.
                        # Mask erasure in _on_sample handles overlay removal.
                        frame = pw_capture.get_frame()
                        if frame is None:
                            time.sleep(0.01)
                            continue
                        pre_capture_mask = None  # erasure done in _on_sample

                    elif capture_method == 'area':
                        pre_capture_mask = _drain_mask(capture_mask_queue)
                        frame = capture_wayland_area(mx, my, mw, mh)

                    elif capture_method == 'gnome':
                        tmp_gnome = '/tmp/hijab_capture.png'
                        try:
                            proc = subprocess.Popen(
                                ['gdbus', 'call', '--session',
                                 '--dest', 'org.gnome.Shell',
                                 '--object-path', '/org/gnome/Shell/Screenshot',
                                 '--method', 'org.gnome.Shell.Screenshot.Screenshot',
                                 'false', 'false', tmp_gnome],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            )
                            time.sleep(0.25)
                            pre_capture_mask = _drain_mask(capture_mask_queue)
                            proc.wait(timeout=8)
                            if Path(tmp_gnome).exists():
                                frame = _load_capture_png(
                                    tmp_gnome, monitor_region, total_display_size)
                            else:
                                frame = None
                        except Exception:
                            pre_capture_mask = _drain_mask(capture_mask_queue)
                            frame = capture_wayland_gnome(
                                monitor_region, total_display_size)

                    else:  # grim
                        pre_capture_mask = _drain_mask(capture_mask_queue)
                        frame = capture_wayland_grim(monitor_region)
                else:
                    pre_capture_mask = None  # X11 uses XID blackout below
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

                # ------------------------------------------------------------------
                # Erase overlay pixels so the CV model never sees what we drew.
                # On Wayland: use pre_capture_mask (snapshotted before the screenshot
                #             call) so the mask position matches the captured frame.
                # On X11:     already handled above via window XID blackout.
                # ------------------------------------------------------------------
                if wayland_mode and pre_capture_mask is not None:
                    try:
                        mask = pre_capture_mask
                        mh2, mw2 = mask.shape
                        fh, fw = frame.shape[:2]
                        h = min(mh2, fh)
                        w = min(mw2, fw)
                        frame[:h, :w][mask[:h, :w] == 1] = 0
                    except Exception:
                        pass

                try:
                    output_queue.put(frame, block=False)
                    frame_count += 1
                    error_count = 0
                    if frame_count == 1:
                        print(f"[Capture] First frame: {frame.shape[1]}x{frame.shape[0]}")
                except Exception:
                    pass  # Queue full — drop frame

                # Also send to viewer if one is attached (for live debug display)
                if viewer_queue is not None:
                    try:
                        viewer_queue.put(frame, block=False)
                    except Exception:
                        pass  # Viewer is slow or not consuming — drop

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
        if pw_capture is not None:
            pw_capture.stop()
        if _gnome_sounds_disabled:
            subprocess.run(
                ['gsettings', 'set', 'org.gnome.desktop.sound', 'event-sounds', 'true'],
                capture_output=True, timeout=2,
            )
            print("[Capture] GNOME event sounds restored")

    print("[Capture] Capture worker stopped")
