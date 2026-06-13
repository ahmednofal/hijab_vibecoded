"""Segmentation worker using MediaPipe for person detection."""

import time
from multiprocessing import Queue, Event
import numpy as np
import cv2

try:
    from mediapipe.python.solutions import selfie_segmentation as mp_selfie_segmentation
except ImportError:
    # Try alternative import for different mediapipe versions
    import mediapipe as mp
    mp_selfie_segmentation = mp.solutions.selfie_segmentation


def segmentation_worker(
    input_queue: Queue,
    output_queue: Queue,
    stop_event: Event,
    scale_factor: float = 0.5
):
    """
    Continuously processes frames from input queue and outputs segmentation masks.
    
    Args:
        input_queue: Queue to get frames from
        output_queue: Queue to put segmentation masks into
        stop_event: Event to signal when to stop processing
        scale_factor: Factor to downscale frames before segmentation (for speed)
    """
    print(f"[Segmentation] Starting segmentation worker (scale={scale_factor})")
    
    # Initialize MediaPipe Selfie Segmentation
    try:
        segmenter = mp_selfie_segmentation.SelfieSegmentation(model_selection=0)
        print("[Segmentation] MediaPipe initialized successfully")
    except Exception as e:
        print(f"[Segmentation] Failed to initialize MediaPipe: {e}")
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
                    print(f"[Segmentation] First frame received: {orig_width}x{orig_height}")
                
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
                
                # Get the segmentation mask
                mask = results.segmentation_mask
                
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
                    print(f"[Segmentation] First mask: person={person_pixels}/{total_pixels} pixels ({100.0 * person_pixels / total_pixels:.1f}%)")
                
                # Try to put mask in queue (non-blocking)
                try:
                    output_queue.put(binary_mask, block=False)
                    frame_count += 1
                except:
                    # Queue is full, drop this mask
                    pass
                
                # Print FPS every 30 frames
                if frame_count % 30 == 0:
                    elapsed = time.time() - start_time
                    fps = frame_count / elapsed
                    print(f"[Segmentation] FPS: {fps:.2f}")
                    frame_count = 0
                    start_time = time.time()
                
            except Exception as e:
                print(f"[Segmentation] Error: {e}")
                time.sleep(0.1)
    
    finally:
        segmenter.close()
        print("[Segmentation] Segmentation worker stopped")
