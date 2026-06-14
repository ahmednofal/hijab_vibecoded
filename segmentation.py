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

_FACE_LANDMARK_IDS = list(range(0, 11))


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

    try:
        _ensure_model()
    except Exception as e:
        log(f"CRITICAL: Model not available: {e}")
        return

    try:
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        import mediapipe as mp
    except Exception as e:
        log(f"CRITICAL: Failed to import MediaPipe Tasks API: {e}")
        return

    try:
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_poses=5,
            min_pose_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        landmarker = vision.PoseLandmarker.create_from_options(options)
        log("PoseLandmarker initialized")
    except Exception as e:
        log(f"Failed to initialize PoseLandmarker: {e}")
        return

    try:
        frame_count = 0
        start_time = time.time()
        prev_detect_time = 0.0
        min_detect_interval = 0.5  # max 2 detections per second

        while not stop_event.is_set():
            try:
                try:
                    frame = input_queue.get(timeout=0.1)
                except:
                    continue

                orig_h, orig_w = frame.shape[:2]

                if frame_count == 0:
                    log(f"First frame: {orig_w}x{orig_h}")

                # Limit detection rate
                now = time.time()
                do_detect = (now - prev_detect_time) >= min_detect_interval

                if do_detect:
                    prev_detect_time = now
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
                        n = len(result.pose_landmarks) if result.pose_landmarks else 0
                        log(f"Detected {n} persons")
                        p = int(combined.sum())
                        t = orig_w * orig_h
                        log(f"First mask: body={p}/{t} ({100.0*p/t:.1f}%)")

                    if scale_factor < 1.0:
                        combined = cv2.resize(
                            combined, (orig_w, orig_h),
                            interpolation=cv2.INTER_NEAREST
                        )

                    # Push mask to overlay
                    try:
                        output_queue.put(combined, block=False)
                    except:
                        pass

                    if frame_count > 0 and frame_count % 50 == 0:
                        elapsed = now - start_time
                        log(f"Detect FPS: {frame_count / elapsed:.2f}")

                frame_count += 1

            except Exception as e:
                log(f"Processing error: {e}")
                time.sleep(0.1)

    except Exception as e:
        log(f"Fatal error: {e}")
    finally:
        landmarker.close()
        log("Segmentation worker stopped")
