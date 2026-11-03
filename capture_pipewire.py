"""PipeWire screen capture via XDG Desktop Portal.

On first run GNOME shows a "Select screen to share" dialog.
Select the internal laptop screen (eDP-1). The choice is persisted via a
restore token so subsequent runs start immediately with no dialog.

Provides:
    is_pipewire_available() -> bool
    PipeWireCapture(monitor_geometry)
        .start()      -> bool
        .get_frame()  -> np.ndarray (RGB, monitor-local coords) | None
        .stop()
"""

import os
import json
import random
import string
import threading
import time
import numpy as np
from pathlib import Path

TOKEN_FILE = Path.home() / '.config' / 'hijab_by_copilot' / 'pipewire_token.json'

PORTAL_DEST   = 'org.freedesktop.portal.Desktop'
PORTAL_PATH   = '/org/freedesktop/portal/desktop'
PORTAL_IFACE  = 'org.freedesktop.portal.ScreenCast'


# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------

def is_pipewire_available():
    """Return True if GStreamer + pipewiresrc are present."""
    try:
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        Gst.init(None)
        if Gst.ElementFactory.find('pipewiresrc') is None:
            print("[PipeWire] pipewiresrc plugin not found — "
                  "install: sudo apt install gstreamer1.0-pipewire")
            return False
        return True
    except Exception as e:
        print(f"[PipeWire] Not available: {e}")
        return False


# ---------------------------------------------------------------------------
# Portal helpers
# ---------------------------------------------------------------------------

def _rand(n=12):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _setup_portal_session():
    """
    Run the XDG Desktop Portal ScreenCast flow.

    Returns (node_id: int, pw_fd: int) on success, (None, None) on failure.
    pw_fd is the PipeWire remote socket fd from OpenPipeWireRemote.
    """
    from gi.repository import GLib, Gio

    # GLib main loop in a background thread so D-Bus signals are dispatched
    loop = GLib.MainLoop()
    loop_thread = threading.Thread(target=loop.run, daemon=True)
    loop_thread.start()

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    # Unique name like ':1.6735' → '1_6735' for request path
    sender = bus.get_unique_name().replace(':', '').replace('.', '_')

    def request_path(handle_token):
        return f'/org/freedesktop/portal/desktop/request/{sender}/{handle_token}'

    def portal_call(method, params_variant, handle_token, timeout=120):
        """Call a portal method and block until Request::Response arrives."""
        rpath = request_path(handle_token)
        done  = threading.Event()
        result = [None]

        def on_response(conn, s_name, obj_path, iface, sig, params, ud):
            code = int(params[0])
            # GLib.Variant a{sv} → unpack to plain Python types so that
            # string values don't get extra quotes from str(GLib.Variant)
            raw = params[1]
            data = {}
            for k in raw.keys():
                v = raw[k]
                try:
                    data[k] = v.unpack()
                except AttributeError:
                    data[k] = v
            result[0] = (code, data)
            done.set()

        sub = bus.signal_subscribe(
            None,
            'org.freedesktop.portal.Request',
            'Response',
            rpath,
            None,
            Gio.DBusSignalFlags.NONE,
            on_response,
            None,
        )
        try:
            bus.call_sync(
                PORTAL_DEST, PORTAL_PATH, PORTAL_IFACE,
                method, params_variant,
                None,
                Gio.DBusCallFlags.NONE,
                -1, None,
            )
        except Exception as e:
            print(f"[PipeWire] Portal call '{method}' error: {e}")
            bus.signal_unsubscribe(sub)
            return None

        if not done.wait(timeout=timeout):
            print(f"[PipeWire] Timeout waiting for '{method}' response")
            bus.signal_unsubscribe(sub)
            return None

        bus.signal_unsubscribe(sub)
        return result[0]

    # ── Load restore token ─────────────────────────────────────────────────
    restore_token = None
    if TOKEN_FILE.exists():
        try:
            restore_token = json.loads(TOKEN_FILE.read_text()).get('restore_token')
            if restore_token:
                print("[PipeWire] Restore token found — no selection dialog needed")
        except Exception:
            pass

    # ── 1. CreateSession ───────────────────────────────────────────────────
    ht = f'hijab_{_rand()}'
    st = f'hijab_s_{_rand()}'
    params = GLib.Variant('(a{sv})', ({
        'handle_token':         GLib.Variant('s', ht),
        'session_handle_token': GLib.Variant('s', st),
    },))
    print("[PipeWire] CreateSession...")
    resp = portal_call('CreateSession', params, ht, timeout=15)
    if resp is None or resp[0] != 0:
        print(f"[PipeWire] CreateSession failed: {resp}")
        loop.quit()
        return None, None

    session = str(resp[1]['session_handle'])
    print(f"[PipeWire] Session handle: {session}")

    # ── 2. SelectSources ──────────────────────────────────────────────────
    ht = f'hijab_{_rand()}'
    opts = {
        'handle_token': GLib.Variant('s', ht),
        'types':        GLib.Variant('u', 1),      # Monitor only
        'multiple':     GLib.Variant('b', False),
        'persist_mode': GLib.Variant('u', 2),       # Persist forever
    }
    if restore_token:
        opts['restore_token'] = GLib.Variant('s', restore_token)

    params = GLib.Variant('(oa{sv})', (session, opts))
    print("[PipeWire] SelectSources...")
    resp = portal_call('SelectSources', params, ht, timeout=15)
    if resp is None or resp[0] != 0:
        print(f"[PipeWire] SelectSources failed: {resp}")
        loop.quit()
        return None, None

    # ── 3. Start ──────────────────────────────────────────────────────────
    ht = f'hijab_{_rand()}'
    params = GLib.Variant('(osa{sv})', (
        session, '',
        {'handle_token': GLib.Variant('s', ht)},
    ))
    if restore_token:
        print("[PipeWire] Start (restore token — no dialog)...")
    else:
        print("[PipeWire] Start — select your internal screen in the GNOME dialog...")
    resp = portal_call('Start', params, ht, timeout=120)
    if resp is None or resp[0] != 0:
        print(f"[PipeWire] Start failed or cancelled: {resp}")
        # Bad token — remove it so next run shows dialog
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
        loop.quit()
        return None, None

    streams = resp[1].get('streams')
    print(f"[PipeWire] streams raw: {streams!r}")
    if not streams:
        print("[PipeWire] No streams in Start response")
        loop.quit()
        return None, None

    # streams is a list of (node_id, props_dict) tuples after .unpack()
    first_stream = streams[0]
    node_id = int(first_stream[0])
    print(f"[PipeWire] Node ID: {node_id}, stream props: {first_stream[1] if len(first_stream) > 1 else {}}")

    # Save new restore token (resp[1] values are now native Python types via .unpack())
    new_token = resp[1].get('restore_token')
    print(f"[PipeWire] Start response keys: {list(resp[1].keys())}")
    print(f"[PipeWire] restore_token raw: {new_token!r}")
    if new_token:
        # new_token is already a plain Python string after .unpack()
        token_str = new_token if isinstance(new_token, str) else str(new_token)
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(json.dumps({'restore_token': token_str}))
        print(f"[PipeWire] Restore token saved: {token_str!r}")

    # ── 4. OpenPipeWireRemote ─────────────────────────────────────────────
    pw_fd = None
    try:
        ret, out_fds = bus.call_with_unix_fd_list_sync(
            PORTAL_DEST, PORTAL_PATH, PORTAL_IFACE,
            'OpenPipeWireRemote',
            GLib.Variant('(oa{sv})', (session, {})),
            GLib.VariantType.new('(h)'),
            Gio.DBusCallFlags.NONE,
            -1, None, None,
        )
        pw_fd = out_fds.get(int(ret[0]))
        print(f"[PipeWire] PipeWire remote fd: {pw_fd}")
    except Exception as e:
        print(f"[PipeWire] OpenPipeWireRemote failed ({e}) — trying without fd")

    loop.quit()
    return node_id, pw_fd


# ---------------------------------------------------------------------------
# GStreamer pipeline wrapper
# ---------------------------------------------------------------------------

class PipeWireCapture:
    """Frame-by-frame screen capture via PipeWire + GStreamer appsink."""

    def __init__(self, monitor_geometry, total_display_size=None,
                 capture_mask_queue=None):
        """
        Args:
            monitor_geometry:    (x, y, width, height) in logical Wayland coords
                                 of the target monitor.
            total_display_size:  (total_w, total_h) of the full virtual display in
                                 logical coords.
            capture_mask_queue:  Queue(maxsize=1) written by the overlay with the mask
                                 it just rendered.  Erasure is applied here inside the
                                 GStreamer callback — the moment the frame arrives —
                                 before the overlay's next timer tick can overwrite it.
        """
        self.monitor_geometry    = monitor_geometry
        self.total_display_size  = total_display_size
        self.capture_mask_queue  = capture_mask_queue
        self._pipeline   = None
        self._appsink    = None
        self._latest     = None
        self._lock       = threading.Lock()
        self._frame_w    = None
        self._frame_h    = None
        self._frame_seq  = 0      # monotonic frame counter for clean capture sync
        self._erase_mask = None   # last mask written by overlay's paintEvent
        self._skip_erasure = threading.Event()  # set during clean capture to disable mask erasure

    def start(self):
        """Set up portal + GStreamer pipeline.  Returns True on success."""
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        Gst.init(None)

        node_id, pw_fd = _setup_portal_session()
        if node_id is None:
            return False

        # Build pipeline string
        if pw_fd is not None and pw_fd >= 0:
            src = f'pipewiresrc fd={pw_fd} path={node_id}'
        else:
            src = f'pipewiresrc path={node_id}'

        pipe_str = (
            f'{src} ! '
            f'videoconvert ! '
            f'video/x-raw,format=RGB ! '
            f'appsink name=sink max-buffers=2 drop=true emit-signals=true sync=false'
        )
        print(f"[PipeWire] Pipeline: {pipe_str}")

        try:
            self._pipeline = Gst.parse_launch(pipe_str)
        except Exception as e:
            print(f"[PipeWire] Pipeline parse error: {e}")
            return False

        self._appsink = self._pipeline.get_by_name('sink')
        self._appsink.connect('new-sample', self._on_sample)

        ret = self._pipeline.set_state(Gst.State.PLAYING)
        from gi.repository import Gst as _Gst
        if ret == _Gst.StateChangeReturn.FAILURE:
            print("[PipeWire] Pipeline failed to transition to PLAYING")
            return False

        # Wait for first frame (up to 10 s)
        print("[PipeWire] Waiting for first frame...")
        deadline = time.time() + 10
        while time.time() < deadline:
            if self._latest is not None:
                break
            time.sleep(0.05)

        if self._latest is None:
            print("[PipeWire] No frames received — check pipewiresrc / portal permissions")
            return False

        print(f"[PipeWire] Live capture started: "
              f"{self._latest.shape[1]}x{self._latest.shape[0]} @ ~30 fps")
        return True

    def _on_sample(self, sink):
        """Called by GStreamer in its own thread for every new frame."""
        from gi.repository import Gst
        sample = sink.emit('pull-sample')
        if sample is None:
            return Gst.FlowReturn.OK

        buf  = sample.get_buffer()
        caps = sample.get_caps()
        s    = caps.get_structure(0)
        w    = s.get_value('width')
        h    = s.get_value('height')

        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.FlowReturn.OK

        try:
            arr = np.frombuffer(mapinfo.data, dtype=np.uint8)
            frame = arr.reshape((h, w, 3)).copy()

            mx, my, mw, mh = self.monitor_geometry

            # Log dimensions once (fires when dims change, i.e. first frame only)
            if self._frame_w != w or self._frame_h != h:
                self._frame_w, self._frame_h = w, h
                print(f"[PipeWire] Frame dims from portal: {w}x{h} "
                      f"(monitor logical: {mw}x{mh})")

            if frame.shape[:2] != (mh, mw):
                # PipeWire delivers eDP-1 content at physical (HiDPI) resolution.
                # Just resize to logical monitor dims — no crop needed.
                from PIL import Image
                pil = Image.fromarray(frame).resize((mw, mh), Image.LANCZOS)
                frame = np.array(pil)

            # Erase the overlay's painted region (skip during clean capture —
            # the overlay is transparent so there is nothing to erase, and
            # zeroing pixels would destroy the clean content we want).
            if not self._skip_erasure.is_set():
                if self.capture_mask_queue is not None:
                    try:
                        new_mask = None
                        while not self.capture_mask_queue.empty():
                            new_mask = self.capture_mask_queue.get_nowait()
                        if new_mask is not None:
                            self._erase_mask = new_mask
                    except Exception:
                        pass

                if self._erase_mask is not None:
                    try:
                        mask = self._erase_mask
                        fh2, fw2 = frame.shape[:2]
                        mh2, mw2 = mask.shape
                        rh = min(mh2, fh2)
                        rw = min(mw2, fw2)
                        frame[:rh, :rw][mask[:rh, :rw] == 1] = 0
                    except Exception:
                        pass

            with self._lock:
                self._latest = frame
                self._frame_seq += 1
        except Exception as e:
            print(f"[PipeWire] Frame decode error: {e}")
        finally:
            buf.unmap(mapinfo)

        return Gst.FlowReturn.OK

    def get_frame(self):
        """Return the most recent RGB frame (numpy array) or None."""
        with self._lock:
            return self._latest

    def get_frame_seq(self):
        """Return (latest_frame, sequence_number) for clean capture sync."""
        with self._lock:
            return self._latest, self._frame_seq

    def stop(self):
        if self._pipeline:
            from gi.repository import Gst
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
            print("[PipeWire] Pipeline stopped")
