"""Segmentation worker using YOLOv8 for multi-person detection."""

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

    # Load YOLO model
    try:
        from ultralytics import YOLO
        model = YOLO('yolov8n-seg.pt')
        log("YOLOv8-seg model loaded")
    except Exception as e:
        log(f"CRITICAL: Failed to load YOLO model: {e}")
        return

    # Load face cascade
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
        inf_count = 0
        start_time = time.time()
        last_mask = None

        while not stop_event.is_set():
            try:
                # Drain stale frames — only keep the latest
                frame = None
                while not stop_event.is_set():
                    try:
                        frame = input_queue.get(timeout=0.1)
                    except:
                        break
                if frame is None:
                    continue

                orig_height, orig_width = frame.shape[:2]

                if frame_count == 0:
                    log(f"First frame received: {orig_width}x{orig_height}")

                # Run inference every 3rd frame; reuse last mask for skipped frames
                if inf_count % 3 == 0:
                    # Downscale for faster processing
                    if scale_factor < 1.0:
                        small_frame = cv2.resize(
                            frame, None, fx=scale_factor, fy=scale_factor,
                            interpolation=cv2.INTER_LINEAR
                        )
                    else:
                        small_frame = frame

                    h, w = small_frame.shape[:2]

                    # YOLO inference at reduced resolution
                    results = model(small_frame, conf=0.3, iou=0.5, verbose=False, imgsz=320)

                    # Combine person masks into one binary mask
                    combined = np.zeros((h, w), dtype=np.uint8)
                    num_persons = 0
                    if results[0].masks is not None:
                        classes = results[0].boxes.cls.cpu().numpy()
                        for i, mask_tensor in enumerate(results[0].masks.data):
                            if classes[i] != 0:  # class 0 = person
                                continue
                            mask_np = mask_tensor.cpu().numpy()
                            if mask_np.shape != (h, w):
                                mask_np = cv2.resize(
                                    mask_np, (w, h), interpolation=cv2.INTER_NEAREST
                                )
                            combined = np.maximum(combined, (mask_np > 0.5).astype(np.uint8))
                            num_persons += 1

                    if num_persons == 0 and frame_count == 0:
                        log("No persons detected in first frame")

                    # Face detection — remove face areas from body mask
                    if face_cascade is not None and num_persons > 0:
                        try:
                            gray = cv2.cvtColor(small_frame, cv2.COLOR_RGB2GRAY)
                            faces = face_cascade.detectMultiScale(
                                gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
                            )
                            if len(faces) > 0:
                                for (fx, fy, fw, fh) in faces:
                                    expand = 0.5
                                    fx2 = max(0, int(fx - fw * expand))
                                    fy2 = max(0, int(fy - fh * expand))
                                    rw = min(w - fx2, int(fw * (1 + 2 * expand)))
                                    rh = min(h - fy2, int(fh * (1 + 2 * expand)))
                                    combined[fy2:fy2+rh, fx2:fx2+rw] = 0
                                if frame_count == 0:
                                    log(f"Excluded {len(faces)} faces")
                        except Exception as e:
                            if frame_count == 0:
                                log(f"Face detection error: {e}")

                    # Upscale mask back to original size
                    if scale_factor < 1.0:
                        combined = cv2.resize(
                            combined, (orig_width, orig_height),
                            interpolation=cv2.INTER_NEAREST
                        )

                    last_mask = combined

                    if frame_count == 0:
                        body_pixels = int(combined.sum())
                        total_pixels = combined.size
                        log(f"First mask: body={body_pixels}/{total_pixels} ({100.0 * body_pixels / total_pixels:.1f}%)")

                    inf_count += 1
                    # Log inference FPS
                    if inf_count % 10 == 0:
                        elapsed = time.time() - start_time
                        fps = inf_count / elapsed
                        log(f"Inference FPS: {fps:.2f}")

                # Reuse last mask for skipped frames
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
        log(f"Fatal error in segmentation worker: {e}")
    finally:
        log("Segmentation worker stopped")
