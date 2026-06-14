"""Segmentation worker using SegFormer for multi-person semantic segmentation."""

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

    # Import SegFormer
    try:
        from transformers import SegformerImageProcessor, SegformerForSemanticSegmentation
        import torch
        log("SegFormer dependencies loaded")
    except Exception as e:
        log(f"CRITICAL: Failed to import SegFormer: {e}")
        return

    # Load model
    model_name = "nvidia/segformer-b0-finetuned-ade-512-512"
    try:
        processor = SegformerImageProcessor.from_pretrained(model_name)
        model = SegformerForSemanticSegmentation.from_pretrained(model_name)
        model.eval()
        log(f"SegFormer-B0 model loaded")
    except Exception as e:
        log(f"CRITICAL: Failed to load model: {e}")
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
        start_time = time.time()
        detect_interval = 0.5
        last_detect_time = 0.0
        last_mask = None

        with torch.no_grad():
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
                    if (now - last_detect_time) >= detect_interval:
                        last_detect_time = now

                        # Downscale
                        if scale_factor < 1.0:
                            small = cv2.resize(
                                frame, None, fx=scale_factor, fy=scale_factor,
                                interpolation=cv2.INTER_LINEAR
                            )
                        else:
                            small = frame

                        # Run SegFormer
                        inputs = processor(images=small, return_tensors="pt")
                        outputs = model(**inputs)
                        logits = outputs.logits

                        # Upsample to downscaled frame size and get person class
                        sh, sw = small.shape[:2]
                        upsampled = torch.nn.functional.interpolate(
                            logits, size=(sh, sw), mode='bilinear', align_corners=False
                        )
                        pred = upsampled.argmax(dim=1)[0].cpu().numpy()
                        # ADE20K class 12 = person
                        combined = (pred == 12).astype(np.uint8)

                        num_persons = int(combined.sum() > 0)

                        # Face exclusion
                        if face_cascade is not None and num_persons > 0:
                            try:
                                gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
                                faces = face_cascade.detectMultiScale(
                                    gray, scaleFactor=1.1, minNeighbors=5, minSize=(15, 15)
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
                            except Exception:
                                pass

                        # Upscale to original size
                        if scale_factor < 1.0:
                            combined = cv2.resize(
                                combined, (orig_w, orig_h),
                                interpolation=cv2.INTER_NEAREST
                            )

                        last_mask = combined

                        if frame_count == 0:
                            has_person = int(combined.sum() > 0)
                            p = int(combined.sum())
                            t = orig_w * orig_h
                            log(f"Person pixels: {p}/{t} ({100.0*p/t:.1f}%)")

                    # Push mask every frame
                    if last_mask is not None:
                        try:
                            output_queue.put(last_mask, block=False)
                        except:
                            pass

                    if frame_count > 0 and frame_count % 50 == 0:
                        elapsed = now - start_time
                        fps = frame_count / elapsed
                        log(f"Frame FPS: {fps:.2f}")

                    frame_count += 1

                except Exception as e:
                    log(f"Processing error: {e}")
                    time.sleep(0.1)

    except Exception as e:
        log(f"Fatal error: {e}")
    finally:
        log("Segmentation worker stopped")
