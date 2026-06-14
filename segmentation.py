"""Segmentation worker using HOG people detector for multi-person body masks."""

import os
import time
from multiprocessing import Queue, Event
import numpy as np
import cv2

_LOG_FILE = os.path.join(os.getcwd(), 'segmentation_debug.log')

def log(msg):
    with open(_LOG_FILE, 'a') as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def segmentation_worker(
    input_queue: Queue,
    output_queue: Queue,
    stop_event: Event,
    scale_factor: float = 0.5
):
    from logging_setup import setup_logging
    setup_logging("segmentation")

    log(f"Starting segmentation worker (scale={scale_factor})")

    # Initialize HOG people detector
    try:
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        log("HOG people detector initialized")
    except Exception as e:
        log(f"CRITICAL: Failed to initialize HOG detector: {e}")
        return

    # Initialize face cascade
    try:
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        log("Face cascade loaded")
    except Exception as e:
        log(f"WARNING: Face cascade failed: {e}")
        face_cascade = None

    try:
        frame_count = 0
        start_time = time.time()
        hog_interval = 0.3
        last_hog_time = 0.0
        last_mask = None

        while not stop_event.is_set():
            try:
                try:
                    frame = input_queue.get(timeout=0.1)
                except:
                    continue

                orig_h, orig_w = frame.shape[:2]

                if frame_count == 0:
                    log(f"First frame: {orig_w}x{orig_h}")

                now = time.time()
                if (now - last_hog_time) >= hog_interval:
                    last_hog_time = now

                    # Downscale for speed
                    if scale_factor < 1.0:
                        small = cv2.resize(
                            frame, None, fx=scale_factor, fy=scale_factor,
                            interpolation=cv2.INTER_LINEAR
                        )
                    else:
                        small = frame

                    sh, sw = small.shape[:2]
                    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)

                    # HOG people detection
                    boxes, _ = hog.detectMultiScale(
                        gray, winStride=(4, 4), padding=(8, 8), scale=1.05
                    )

                    # Create body mask from bounding boxes
                    combined = np.zeros((sh, sw), dtype=np.uint8)
                    for (x, y, w, h) in boxes:
                        # Expand bounding box upward (head may be partially detected)
                        exp_y = max(0, y - int(h * 0.15))
                        exp_h = min(sh - exp_y, h + int(h * 0.15))
                        exp_x = max(0, x - int(w * 0.1))
                        exp_w = min(sw - exp_x, w + int(w * 0.1))
                        combined[exp_y:exp_y+exp_h, exp_x:exp_x+exp_w] = 1

                    # Face detection — remove face areas from body mask
                    if face_cascade is not None and len(boxes) > 0:
                        try:
                            faces = face_cascade.detectMultiScale(
                                gray, scaleFactor=1.1, minNeighbors=5, minSize=(20, 20)
                            )
                            for (fx, fy, fw, fh) in faces:
                                expand = 0.5
                                fx2 = max(0, int(fx - fw * expand))
                                fy2 = max(0, int(fy - fh * expand))
                                rw = min(sw - fx2, int(fw * (1 + 2 * expand)))
                                rh = min(sh - fy2, int(fh * (1 + 2 * expand)))
                                combined[fy2:fy2+rh, fx2:fx2+rw] = 0
                            if frame_count == 0:
                                log(f"Excluded {len(faces)} faces")
                        except Exception as e:
                            pass

                    # Upscale to original size
                    if scale_factor < 1.0:
                        combined = cv2.resize(
                            combined, (orig_w, orig_h),
                            interpolation=cv2.INTER_NEAREST
                        )

                    last_mask = combined

                    if frame_count == 0:
                        log(f"Detected {len(boxes)} persons")
                        p = int(combined.sum())
                        t = orig_w * orig_h
                        log(f"First mask: body={p}/{t} ({100.0*p/t:.1f}%)")

                    if frame_count > 0 and frame_count % 30 == 0:
                        elapsed = now - start_time
                        fps = frame_count / elapsed
                        log(f"Processing FPS: {fps:.2f}")

                # Push latest mask (even if HOG didn't run — reuse last)
                if last_mask is not None:
                    try:
                        output_queue.put(last_mask, block=False)
                    except:
                        pass

                frame_count += 1

            except Exception as e:
                log(f"Processing error: {e}")
                time.sleep(0.1)

    except Exception as e:
        log(f"Fatal error: {e}")
    finally:
        log("Segmentation worker stopped")
