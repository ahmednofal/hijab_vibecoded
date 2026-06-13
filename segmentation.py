"""Segmentation worker using MediaPipe Tasks API for person detection."""

import os
import time
import urllib.request
from multiprocessing import Queue, Event
import numpy as np
import cv2

_LOG_FILE = os.path.join(os.getcwd(), 'segmentation_debug.log')

def log(msg):
    with open(_LOG_FILE, 'a') as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite"
MODEL_PATH = os.path.join(os.path.dirname(__file__), 'selfie_segmenter.tflite')


def _ensure_model():
    if not os.path.exists(MODEL_PATH):
        log(f"Downloading selfie_segmenter model...")
        try:
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
            log(f"Model downloaded to {MODEL_PATH}")
        except Exception as e:
            log(f"Failed to download model: {e}")
            raise


def segmentation_worker(
    input_queue: Queue,
    output_queue: Queue,
    stop_event: Event,
    scale_factor: float = 0.5
):
    log(f"Starting segmentation worker (scale={scale_factor})")

    # Import mediapipe tasks API
    try:
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        import mediapipe as mp
        log("MediaPipe Tasks API imported successfully")
    except Exception as e:
        log(f"CRITICAL: Failed to import MediaPipe Tasks API: {e}")
        return

    # Download model if needed
    try:
        _ensure_model()
    except Exception as e:
        log(f"CRITICAL: Model not available: {e}")
        return

    # Initialize ImageSegmenter
    try:
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.ImageSegmenterOptions(
            base_options=base_options,
            output_confidence_masks=True,
        )
        segmenter = vision.ImageSegmenter.create_from_options(options)
        log("ImageSegmenter initialized successfully")
    except Exception as e:
        log(f"Failed to initialize ImageSegmenter: {e}")
        return

    try:
        frame_count = 0
        start_time = time.time()

        while not stop_event.is_set():
            try:
                # Get frame from queue (with timeout)
                try:
                    frame = input_queue.get(timeout=0.1)
                except:
                    continue

                orig_height, orig_width = frame.shape[:2]

                if frame_count == 0:
                    log(f"First frame received: {orig_width}x{orig_height}")

                # Downscale for faster processing
                if scale_factor < 1.0:
                    small_frame = cv2.resize(
                        frame, None, fx=scale_factor, fy=scale_factor,
                        interpolation=cv2.INTER_LINEAR
                    )
                else:
                    small_frame = frame

                # Convert to MediaPipe Image and run segmentation
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=small_frame)
                result = segmenter.segment(mp_image)

                if result is None or not result.confidence_masks:
                    log("WARNING: segmentation returned no masks")
                    continue

                # Selfie segmenter categories: 0=background, 1=person
                if len(result.confidence_masks) >= 2:
                    person_conf = result.confidence_masks[1].numpy_view()
                    if frame_count == 0:
                        log(f"Got {len(result.confidence_masks)} confidence masks, using index 1 (person)")
                elif len(result.confidence_masks) == 1:
                    person_conf = result.confidence_masks[0].numpy_view()
                    if frame_count == 0:
                        log(f"Got 1 confidence mask, using index 0")
                else:
                    log("WARNING: no confidence masks available")
                    continue
                binary_mask = (person_conf > 0.5).astype(np.uint8)

                # Upscale mask back to original size if needed
                if scale_factor < 1.0:
                    binary_mask = cv2.resize(
                        binary_mask, (orig_width, orig_height),
                        interpolation=cv2.INTER_NEAREST
                    )

                if frame_count == 0:
                    person_pixels = int(binary_mask.sum())
                    total_pixels = binary_mask.size
                    log(f"First mask: person={person_pixels}/{total_pixels} ({100.0 * person_pixels / total_pixels:.1f}%)")

                # Put mask in queue (non-blocking)
                try:
                    output_queue.put(binary_mask, block=False)
                    frame_count += 1
                except:
                    pass

                # Log FPS every 30 frames
                if frame_count % 30 == 0:
                    elapsed = time.time() - start_time
                    fps = frame_count / elapsed
                    log(f"FPS: {fps:.2f}")
                    frame_count = 0
                    start_time = time.time()

            except Exception as e:
                log(f"Processing error: {e}")
                time.sleep(0.1)

    except Exception as e:
        log(f"Fatal error in segmentation worker: {e}")
    finally:
        segmenter.close()
        log("Segmentation worker stopped")
