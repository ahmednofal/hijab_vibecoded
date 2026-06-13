"""Segmentation worker using MediaPipe for person detection."""

import os
import time
from multiprocessing import Queue, Event
import numpy as np
import cv2

_LOG_FILE = os.path.join(os.getcwd(), 'segmentation_debug.log')

def log(msg):
    with open(_LOG_FILE, 'a') as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

# Try every known import path for MediaPipe SelfieSegmentation
mp_selfie_segmentation = None
import mediapipe as mp
log(f"mediapipe version: {getattr(mp, '__version__', 'unknown')}")
log(f"mediapipe dir: {[x for x in dir(mp) if not x.startswith('_')]}")

import_paths = [
    lambda: mp.solutions.selfie_segmentation,
    lambda: __import__('mediapipe.python.solutions.selfie_segmentation', fromlist=['selfie_segmentation']).selfie_segmentation,
    lambda: __import__('mediapipe.solutions.selfie_segmentation', fromlist=['selfie_segmentation']).selfie_segmentation,
]

for i, path_fn in enumerate(import_paths):
    try:
        mp_selfie_segmentation = path_fn()
        log(f"Import path {i} succeeded")
        break
    except Exception as e:
        log(f"Import path {i} failed: {e}")

if mp_selfie_segmentation is None:
    log("CRITICAL: All import paths failed for mediapipe SelfieSegmentation")


def segmentation_worker(
    input_queue: Queue,
    output_queue: Queue,
    stop_event: Event,
    scale_factor: float = 0.5
):
    log(f"Starting segmentation worker (scale={scale_factor})")
    
    if mp_selfie_segmentation is None:
        log("CRITICAL: mediapipe not available, exiting")
        return
    
    # Initialize MediaPipe Selfie Segmentation
    try:
        segmenter = mp_selfie_segmentation.SelfieSegmentation(model_selection=0)
        log("MediaPipe initialized successfully")
    except Exception as e:
        log(f"Failed to initialize MediaPipe: {e}")
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
                
                # Get original dimensions
                orig_height, orig_width = frame.shape[:2]
                
                if frame_count == 0:
                    log(f"First frame received: {orig_width}x{orig_height}")
                
                # Downscale for faster processing if needed
                if scale_factor < 1.0:
                    small_frame = cv2.resize(
                        frame,
                        None,
                        fx=scale_factor,
                        fy=scale_factor,
                        interpolation=cv2.INTER_LINEAR
                    )
                else:
                    small_frame = frame
                
                # Run segmentation
                results = segmenter.process(small_frame)
                
                if results is None:
                    log("WARNING: segmenter.process returned None")
                    continue
                
                # Get the segmentation mask
                mask = results.segmentation_mask
                
                if mask is None:
                    log("WARNING: segmentation_mask is None")
                    continue
                
                # Upscale mask back to original size if needed
                if scale_factor < 1.0:
                    mask = cv2.resize(
                        mask,
                        (orig_width, orig_height),
                        interpolation=cv2.INTER_LINEAR
                    )
                
                # Convert to binary mask (threshold at 0.5)
                binary_mask = (mask > 0.5).astype(np.uint8)
                
                if frame_count == 0:
                    person_pixels = int(binary_mask.sum())
                    total_pixels = binary_mask.size
                    log(f"First mask: person={person_pixels}/{total_pixels} ({100.0 * person_pixels / total_pixels:.1f}%)")
                
                # Try to put mask in queue (non-blocking)
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
