"""Segmentation worker using MediaPipe Tasks PoseLandmarker for multi-person body detection."""

import os
import time
import ssl
import urllib.request
from multiprocessing import Queue, Event
import numpy as np
import cv2

_LOG_FILE = os.path.join(os.getcwd(), 'segmentation_debug.log')

def log(msg):
    with open(_LOG_FILE, 'a') as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
MODEL_PATH = os.path.join(os.path.dirname(__file__), 'pose_landmarker_lite.task')
_MIN_MODEL_SIZE = 100000

_FACE_LANDMARK_IDS = list(range(0, 11))  # nose, eyes, ears, mouth


def _model_valid():
    if not os.path.exists(MODEL_PATH):
        return False
    try:
        return os.path.getsize(MODEL_PATH) > _MIN_MODEL_SIZE
    except OSError:
        return False


def _ensure_model():
    if _model_valid():
        log(f"Pose model exists ({os.path.getsize(MODEL_PATH)} bytes)")
        return
    log("Downloading pose_landmarker_lite model...")
    try:
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    except Exception:
        log("SSL download failed, retrying with unverified context...")
        ctx = ssl._create_unverified_context()
        resp = urllib.request.urlopen(MODEL_URL, context=ctx)
        with open(MODEL_PATH, 'wb') as f:
            f.write(resp.read())
    size = os.path.getsize(MODEL_PATH)
    log(f"Model downloaded ({size} bytes)")


def _body_mask_from_landmarks(landmarks, img_w, img_h, body_pad=0.15):
    """Create a body mask from pose landmarks using bounding box."""
    xs = [lm.x * img_w for lm in landmarks]
    ys = [lm.y * img_h for lm in landmarks]
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    bw = x2 - x1
    bh = y2 - y1
    pad_x = int(bw * body_pad)
    pad_y = int(bh * body_pad)
    x1 = max(0, int(x1) - pad_x)
    y1 = max(0, int(y1) - pad_y)
    x2 = min(img_w, int(x2) + pad_x)
    y2 = min(img_h, int(y2) + pad_y)
    mask = np.zeros((img_h, img_w), dtype=np.uint8)
    mask[y1:y2, x1:x2] = 1
    return mask


def _face_mask_from_landmarks(landmarks, img_w, img_h, face_expand=0.5):
    """Create a face mask from face landmark indices."""
    xs = [landmarks[i].x * img_w for i in _FACE_LANDMARK_IDS]
    ys = [landmarks[i].y * img_h for i in _FACE_LANDMARK_IDS]
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    fw = x2 - x1
    fh = y2 - y1
    expand_x = int(fw * face_expand)
    expand_y = int(fh * face_expand)
    x1 = max(0, int(x1) - expand_x)
    y1 = max(0, int(y1) - expand_y)
    x2 = min(img_w, int(x2) + expand_x)
    y2 = min(img_h, int(y2) + expand_y)
    mask = np.zeros((img_h, img_w), dtype=np.uint8)
    mask[y1:y2, x1:x2] = 1
    return mask


def segmentation_worker(
    input_queue: Queue,
    output_queue: Queue,
    stop_event: Event,
    scale_factor: float = 0.5
):
    from logging_setup import setup_logging
    setup_logging("segmentation")

    log(f"Starting segmentation worker (scale={scale_factor})")

    # Download model if needed
    try:
        _ensure_model()
    except Exception as e:
        log(f"CRITICAL: Model not available: {e}")
        return

    # Import mediapipe tasks API
    try:
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        import mediapipe as mp
        log("MediaPipe Tasks API imported successfully")
    except Exception as e:
        log(f"CRITICAL: Failed to import MediaPipe Tasks API: {e}")
        return

    # Initialize PoseLandmarker
    try:
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            min_pose_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            output_segmentations=False,
        )
        landmarker = vision.PoseLandmarker.create_from_options(options)
        log("PoseLandmarker initialized")
    except Exception as e:
        log(f"Failed to initialize PoseLandmarker: {e}")
        return

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
                        frame = input_queue.get(timeout=0.05)
                    except:
                        break
                if frame is None:
                    continue

                orig_h, orig_w = frame.shape[:2]

                # Run inference every 3rd frame; reuse last mask for skipped frames
                if inf_count % 3 == 0:
                    if scale_factor < 1.0:
                        small = cv2.resize(
                            frame, None, fx=scale_factor, fy=scale_factor,
                            interpolation=cv2.INTER_LINEAR
                        )
                    else:
                        small = frame

                    sh, sw = small.shape[:2]
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=small)
                    result = landmarker.detect(mp_image)

                    combined = np.zeros((sh, sw), dtype=np.uint8)
                    if result.pose_landmarks:
                        for pose_lm in result.pose_landmarks:
                            body = _body_mask_from_landmarks(pose_lm, sw, sh)
                            face = _face_mask_from_landmarks(pose_lm, sw, sh)
                            combined = np.maximum(combined, body & (1 - face))

                    if frame_count == 0:
                        log(f"Detected {len(result.pose_landmarks) if result.pose_landmarks else 0} persons")

                    # Upscale to original size
                    if scale_factor < 1.0:
                        combined = cv2.resize(
                            combined, (orig_w, orig_h),
                            interpolation=cv2.INTER_NEAREST
                        )

                    last_mask = combined
                    inf_count += 1

                    if frame_count == 0:
                        body_pixels = int(combined.sum())
                        log(f"First mask: body={body_pixels}/{orig_w*orig_h} ({100.0*body_pixels/(orig_w*orig_h):.1f}%)")

                    if inf_count % 10 == 0:
                        elapsed = time.time() - start_time
                        log(f"Inference FPS: {inf_count / elapsed:.2f}")

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
        log(f"Fatal error: {e}")
    finally:
        landmarker.close()
        log("Segmentation worker stopped")
