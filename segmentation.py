"""Segmentation workers: simulation (moving rectangle) and MediaPipe person detection."""

import time
from multiprocessing import Queue, Event
import numpy as np


def simulation_worker(
    output_queue: Queue,
    stop_event: Event,
    screen_width: int,
    screen_height: int,
    rect_width: int = 400,
    speed: int = 10,
    fps: int = 30,
):
    """
    Generate moving-rectangle masks that simulate semantic segmentation output.

    The mask is a numpy uint8 array of shape (screen_height, screen_width) where
    1 means "covered by segmented region" and 0 means transparent.  The rectangle
    wraps around the screen edge so the animation is continuous.

    Args:
        output_queue: Queue to put masks into (consumed by the overlay).
        stop_event:   Multiprocessing Event; worker exits when set.
        screen_width: Pixel width of the target monitor.
        screen_height: Pixel height of the target monitor.
        rect_width:   Width of the simulated segmentation rectangle in pixels.
        speed:        Pixels to advance per frame.
        fps:          Target output frame-rate.
    """
    print(f"[Segmentation] Simulation worker started "
          f"(screen={screen_width}x{screen_height}, rect_width={rect_width}, speed={speed})")

    frame_delay = 1.0 / fps
    x = 0  # left edge of the moving rectangle (float for sub-pixel accuracy)

    while not stop_event.is_set():
        mask = np.zeros((screen_height, screen_width), dtype=np.uint8)

        x_start = int(x) % screen_width
        x_end = x_start + rect_width

        if x_end <= screen_width:
            mask[:, x_start:x_end] = 1
        else:
            # Rectangle wraps around the right edge
            mask[:, x_start:] = 1
            wrap = x_end - screen_width
            mask[:, :wrap] = 1

        try:
            output_queue.put(mask, block=False)
        except Exception:
            pass  # Queue full — drop frame, overlay keeps last mask

        x = (x + speed) % screen_width
        try:
            time.sleep(frame_delay)
        except (KeyboardInterrupt, SystemExit):
            break

    print("[Segmentation] Simulation worker stopped")


# ---------------------------------------------------------------------------
# Real segmentation (MediaPipe) — used when simulation=False
# ---------------------------------------------------------------------------

def _import_mediapipe():
    try:
        from mediapipe.python.solutions import selfie_segmentation as mp_selfie
        return mp_selfie
    except ImportError:
        import mediapipe as mp
        return mp.solutions.selfie_segmentation


def segmentation_worker(
    input_queue: Queue,
    output_queue: Queue,
    stop_event: Event,
    scale_factor: float = 0.5,
):
    """
    Continuously process captured frames and output binary segmentation masks.

    Reads frames from input_queue, runs MediaPipe SelfieSegmentation, and puts
    binary uint8 masks (0/1, shape=frame.shape[:2]) into output_queue.

    Args:
        input_queue:  Queue of captured frames (H×W×3 uint8 RGB numpy arrays).
        output_queue: Queue to receive masks (H×W uint8, values 0 or 1).
        stop_event:   Multiprocessing Event; worker exits when set.
        scale_factor: Downscale factor applied before segmentation for speed.
    """
    import cv2  # imported here to avoid import at module level for sim-only runs

    print(f"[Segmentation] Real segmentation worker started (scale={scale_factor})")

    mp_selfie = _import_mediapipe()

    try:
        segmenter = mp_selfie.SelfieSegmentation(model_selection=0)
        print("[Segmentation] MediaPipe initialized successfully")
    except Exception as e:
        print(f"[Segmentation] Failed to initialize MediaPipe: {e}")
        return

    frame_count = 0
    start_time = time.time()

    try:
        while not stop_event.is_set():
            try:
                frame = input_queue.get(timeout=0.1)
            except Exception:
                continue

            orig_height, orig_width = frame.shape[:2]

            if scale_factor < 1.0:
                small = cv2.resize(frame, None, fx=scale_factor, fy=scale_factor,
                                   interpolation=cv2.INTER_LINEAR)
            else:
                small = frame

            results = segmenter.process(small)
            mask = results.segmentation_mask  # float32 H×W

            if scale_factor < 1.0:
                mask = cv2.resize(mask, (orig_width, orig_height),
                                  interpolation=cv2.INTER_LINEAR)

            binary_mask = (mask > 0.5).astype(np.uint8)

            try:
                output_queue.put(binary_mask, block=False)
                frame_count += 1
            except Exception:
                pass  # Queue full — drop

            if frame_count > 0 and frame_count % 30 == 0:
                elapsed = time.time() - start_time
                print(f"[Segmentation] FPS: {frame_count / elapsed:.2f}")
                frame_count = 0
                start_time = time.time()

    finally:
        segmenter.close()
        print("[Segmentation] Real segmentation worker stopped")
