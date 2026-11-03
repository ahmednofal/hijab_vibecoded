"""Live capture viewer — shows the cleaned frames that go to the CV model."""

import os
import time
import sys
import numpy as np
from multiprocessing import Queue, Event


def viewer_worker(viewer_queue: Queue, stop_event: Event,
                  window_title: str = "CV Input Feed  [q to quit]",
                  scale: float = 0.5,
                  monitor_geometry: tuple = None):
    """
    Display cleaned capture frames in a Tkinter window.

    Uses Tkinter (stdlib, no Qt fork-safety issues) so it works correctly
    when started as a subprocess after the main process already created a
    QApplication for monitor detection.

    Args:
        viewer_queue:     Queue fed by capture_worker.
        stop_event:       Shared Event; window closes when set.
        window_title:     Window title.
        scale:            Display scale factor (0.5 = half resolution).
        monitor_geometry: (x, y, width, height) of the target monitor.
    """
    # Force X11 for Tk as well (it defaults to Wayland on some GNOME setups)
    os.environ.setdefault('DISPLAY', ':0')
    os.environ['GDK_BACKEND'] = 'x11'

    import tkinter as tk
    from PIL import Image, ImageTk, ImageDraw, ImageFont
    import cv2

    print(f"[Viewer] Opening live feed window (scale={scale})")

    # Display dimensions
    if monitor_geometry is not None:
        dw = int(monitor_geometry[2] * scale)
        dh = int(monitor_geometry[3] * scale)
    else:
        dw = int(1536 * scale)
        dh = int(864  * scale)

    root = tk.Tk()
    root.title(window_title)
    root.geometry(f"{dw}x{dh}")
    root.configure(bg='black')
    root.resizable(True, True)

    canvas = tk.Canvas(root, width=dw, height=dh, bg='black',
                       highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)

    # Placeholder text
    canvas.create_text(dw // 2, dh // 2,
                       text="Waiting for capture frames...",
                       fill='#00c800', font=('Helvetica', 14))

    state = {'tk_image': None, 'fps': 0.0, 'frame_count': 0,
             'last_fps_time': time.time(), 'running': True}

    def on_key(event):
        if event.char == 'q':
            print("[Viewer] User pressed q — closing")
            stop_event.set()
            state['running'] = False
            root.destroy()

    root.bind('<Key>', on_key)

    def poll():
        if not state['running'] or stop_event.is_set():
            root.destroy()
            return

        # Drain queue — show only newest frame
        frame = None
        try:
            while True:
                frame = viewer_queue.get_nowait()
        except Exception:
            pass

        if frame is not None:
            state['frame_count'] += 1

            # Scale
            fh, fw = frame.shape[:2]
            tw = int(fw * scale)
            th = int(fh * scale)
            display = cv2.resize(frame, (tw, th), interpolation=cv2.INTER_LINEAR)

            # Annotate erased (pure-black) band in cyan
            bgr = cv2.cvtColor(display, cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            _, black_mask = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(black_mask, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                if cv2.contourArea(cnt) > 2000:
                    cv2.drawContours(bgr, [cnt], -1, (255, 255, 0), 2)

            # FPS
            now = time.time()
            elapsed = now - state['last_fps_time']
            if elapsed >= 2.0:
                state['fps'] = state['frame_count'] / elapsed
                state['last_fps_time'] = now
                state['frame_count'] = 0

            cv2.putText(bgr,
                        f"CV Input | {state['fps']:.1f} fps | q=quit",
                        (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (0, 255, 0), 1, cv2.LINE_AA)

            # BGR → RGB → PIL → Tk
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)
            tk_img = ImageTk.PhotoImage(pil_img)

            canvas.delete('all')
            canvas.create_image(0, 0, anchor=tk.NW, image=tk_img)
            state['tk_image'] = tk_img  # keep reference

        root.after(33, poll)  # ~30 fps

    print("[Viewer] Window created — press q to quit")
    root.after(33, poll)
    root.mainloop()
    print("[Viewer] Viewer closed")
