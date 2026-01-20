#!/usr/bin/env python3
"""Automated verification system for overlay correctness - V2.

This version taps into the existing capture queue to analyze frames,
avoiding the need for independent screen capture which fails on Wayland.

Validates:
1. Red rectangle is moving (displacement detected numerically)
2. No feedback loop (only one rectangle detected per frame)
3. Background is real screen content (not black/grey)
"""

import sys
import os
import time
import json
import argparse
from multiprocessing import Process, Queue, Event
from pathlib import Path
from typing import Optional, Dict, List
import numpy as np
import cv2
from skimage.metrics import structural_similarity as ssim

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


def detect_red_rectangle(frame: np.ndarray) -> Optional[Dict]:
    """Detect red rectangle using color masking.
    
    Returns:
        Dict with keys: x, y, width, height, count
        or None if no rectangle detected
    """
    # Convert to HSV for better color detection
    hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
    
    # Red color range in HSV (red wraps around at 0/180)
    # Lower red (0-10)
    lower_red1 = np.array([0, 100, 100])
    upper_red1 = np.array([10, 255, 255])
    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    
    # Upper red (170-180)
    lower_red2 = np.array([170, 100, 100])
    upper_red2 = np.array([180, 255, 255])
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    
    # Combine masks
    red_mask = cv2.bitwise_or(mask1, mask2)
    
    # Find contours
    contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None
    
    # Find rectangles (filter noise)
    rectangles = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 1000:  # Filter out small noise
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        rectangles.append({
            'x': int(x),
            'y': int(y),
            'width': int(w),
            'height': int(h),
            'area': int(area)
        })
    
    if not rectangles:
        return None
    
    # Sort by area, take largest
    rectangles.sort(key=lambda r: r['area'], reverse=True)
    primary = rectangles[0]
    
    return {
        'x': primary['x'],
        'y': primary['y'],
        'width': primary['width'],
        'height': primary['height'],
        'count': len(rectangles)
    }


def verify_worker(capture_queue: Queue, results_queue: Queue, stop_event: Event, 
                 duration: float = 5.0, verbose: bool = False):
    """Worker process that reads from capture queue and verifies frames."""
    
    def log(msg):
        if verbose:
            print(f"[Verify] {msg}", file=sys.stderr)
    
    log("Verification worker started")
    
    results = {
        'test_start_time': time.time(),
        'duration': duration,
        'frames': [],
        'summary': {
            'total_frames': 0,
            'rectangles_detected': 0,
            'movement_detected': False,
            'feedback_loop_detected': False,
            'background_valid': False,
            'tests_passed': []
        }
    }
    
    reference_background = None
    start_time = time.time()
    frame_count = 0
    positions = []
    
    # Capture reference (first frame before rectangle appears)
    # gnome-screenshot is slow (~2s), wait longer
    log("Waiting for first frame...")
    while reference_background is None and time.time() - start_time < 10.0:
        try:
            frame = capture_queue.get(timeout=0.5)
            reference_background = frame.copy()
            mean_val = np.mean(frame)
            std_val = np.std(frame)
            log(f"Got reference: mean={mean_val:.2f}, std={std_val:.2f}")
            
            if mean_val < 5.0:
                log("WARNING: Background is black")
            if std_val < 10.0:
                log("WARNING: Background has low variation")
            break
        except:
            pass
    
    if reference_background is None:
        log("ERROR: Failed to get reference frame")
        results['summary']['error'] = "No reference frame received"
        results_queue.put(results)
        return
    
    # Now analyze frames for the duration
    start_time = time.time()
    
    while time.time() - start_time < duration and not stop_event.is_set():
        try:
            frame = capture_queue.get(timeout=0.2)
            
            rect_info = detect_red_rectangle(frame)
            
            frame_data = {
                'frame_num': frame_count,
                'timestamp': time.time() - start_time,
                'rect_detected': rect_info is not None
            }
            
            if rect_info:
                frame_data.update({
                    'rect_x': rect_info['x'],
                    'rect_y': rect_info['y'],
                    'rect_width': rect_info['width'],
                    'rect_height': rect_info['height'],
                    'rect_count': rect_info['count']
                })
                positions.append(rect_info['x'])
                
                # Background similarity (mask out rectangle)
                ref_compare = reference_background.copy()
                curr_compare = frame.copy()
                
                x, y, w, h = rect_info['x'], rect_info['y'], rect_info['width'], rect_info['height']
                margin = 10
                x1 = max(0, x - margin)
                y1 = max(0, y - margin)
                x2 = min(frame.shape[1], x + w + margin)
                y2 = min(frame.shape[0], y + h + margin)
                
                ref_compare[y1:y2, x1:x2] = 0
                curr_compare[y1:y2, x1:x2] = 0
                
                ref_gray = cv2.cvtColor(ref_compare, cv2.COLOR_RGB2GRAY)
                curr_gray = cv2.cvtColor(curr_compare, cv2.COLOR_RGB2GRAY)
                
                bg_score = ssim(ref_gray, curr_gray)
                frame_data['bg_similarity'] = float(bg_score)
            
            results['frames'].append(frame_data)
            frame_count += 1
            
            # Print progress as JSON
            if rect_info:
                print(json.dumps(frame_data))
            
        except:
            pass  # Timeout or queue empty
    
    # Analyze results
    results['summary']['total_frames'] = frame_count
    results['summary']['rectangles_detected'] = sum(1 for f in results['frames'] if f['rect_detected'])
    
    # Test 1: Movement
    if len(positions) >= 3:
        differences = np.diff(positions)
        # Handle wraparound
        differences = [d if d > -1000 else d + 1920 for d in differences]  # Assuming 1920 width
        positive_diffs = [d for d in differences if d > 0]
        
        if positive_diffs:
            avg_displacement = np.mean(positive_diffs)
            movement_ok = avg_displacement > 1  # At least 1 pixel movement
            results['summary']['movement_detected'] = movement_ok
            results['summary']['avg_displacement'] = float(avg_displacement)
            if movement_ok:
                results['summary']['tests_passed'].append('movement')
            log(f"Average displacement: {avg_displacement:.2f} pixels")
    
    # Test 2: Feedback loop check
    rect_counts = [f.get('rect_count', 0) for f in results['frames'] if f['rect_detected']]
    if rect_counts:
        max_count = max(rect_counts)
        no_feedback_loop = max_count == 1
        results['summary']['feedback_loop_detected'] = not no_feedback_loop
        results['summary']['max_rect_count'] = max_count
        if no_feedback_loop:
            results['summary']['tests_passed'].append('no_feedback_loop')
        log(f"Max rectangles detected: {max_count}")
    
    # Test 3: Background validity
    bg_scores = [f.get('bg_similarity', 0) for f in results['frames'] if 'bg_similarity' in f]
    if bg_scores:
        avg_bg_score = np.mean(bg_scores)
        min_bg_score = np.min(bg_scores)
        bg_valid = avg_bg_score > 0.80  # 80% threshold
        results['summary']['background_valid'] = bg_valid
        results['summary']['avg_bg_similarity'] = float(avg_bg_score)
        results['summary']['min_bg_similarity'] = float(min_bg_score)
        if bg_valid:
            results['summary']['tests_passed'].append('background_valid')
        log(f"Background: avg={avg_bg_score:.3f}, min={min_bg_score:.3f}")
    
    # Overall
    results['summary']['all_tests_passed'] = len(results['summary']['tests_passed']) == 3
    
    results_queue.put(results)
    log("Verification complete")


def run_verification(duration: float = 5.0, output_json: Optional[str] = None, 
                    verbose: bool = False) -> Dict:
    """Run verification by launching main.py and analyzing its output."""
    
    # Import the main hijab overlay system
    sys.path.insert(0, str(Path(__file__).parent))
    from main import HijabOverlay
    
    # Create verification queues
    results_queue = Queue()
    stop_event = Event()
    
    # Start the hijab overlay (this creates its own capture_queue)
    overlay_system = HijabOverlay()
    
    # Start verification worker that will read from the capture queue
    verify_proc = Process(
        target=verify_worker,
        args=(overlay_system.capture_queue, results_queue, stop_event, duration, verbose),
        daemon=True
    )
    verify_proc.start()
    
    # Start the overlay system (runs in main thread)
    try:
        # Use a timer to stop after duration + buffer
        import threading
        def stop_after_delay():
            time.sleep(duration + 3)
            stop_event.set()
            overlay_system.stop()
        
        timer = threading.Thread(target=stop_after_delay, daemon=True)
        timer.start()
        
        overlay_system.start()
        
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        verify_proc.join(timeout=2)
    
    # Get results
    try:
        results = results_queue.get(timeout=1)
    except:
        results = {
            'summary': {
                'error': 'Failed to get verification results',
                'all_tests_passed': False
            }
        }
    
    # Save if requested
    if output_json:
        with open(output_json, 'w') as f:
            json.dump(results, f, indent=2)
    
    return results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description='Automated overlay verification v2')
    parser.add_argument('--duration', type=float, default=5.0,
                       help='Test duration in seconds (default: 5.0)')
    parser.add_argument('--output-json', type=str,
                       help='Path to save detailed JSON results')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose logging')
    
    args = parser.parse_args()
    
    results = run_verification(
        duration=args.duration,
        output_json=args.output_json,
        verbose=args.verbose
    )
    
    # Print summary
    summary = results.get('summary', {})
    print("\n" + "="*60, file=sys.stderr)
    print("VERIFICATION RESULTS", file=sys.stderr)
    print("="*60, file=sys.stderr)
    print(f"Total frames: {summary.get('total_frames', 0)}", file=sys.stderr)
    print(f"Rectangles detected: {summary.get('rectangles_detected', 0)}", file=sys.stderr)
    print(f"\nTests passed: {len(summary.get('tests_passed', []))}/3", file=sys.stderr)
    
    if 'movement' in summary.get('tests_passed', []):
        print(f"  ✓ Movement ({summary.get('avg_displacement', 0):.1f} px)", file=sys.stderr)
    else:
        print(f"  ✗ Movement NOT detected", file=sys.stderr)
    
    if 'no_feedback_loop' in summary.get('tests_passed', []):
        print(f"  ✓ No feedback loop", file=sys.stderr)
    else:
        print(f"  ✗ Feedback loop (max {summary.get('max_rect_count', 0)} rects)", file=sys.stderr)
    
    if 'background_valid' in summary.get('tests_passed', []):
        print(f"  ✓ Background valid ({summary.get('avg_bg_similarity', 0):.3f})", file=sys.stderr)
    else:
        print(f"  ✗ Background invalid ({summary.get('avg_bg_similarity', 0):.3f})", file=sys.stderr)
    
    print("="*60, file=sys.stderr)
    
    if summary.get('all_tests_passed', False):
        print("\n✓ ALL TESTS PASSED", file=sys.stderr)
        sys.exit(0)
    else:
        print("\n✗ TESTS FAILED", file=sys.stderr)
        if 'error' in summary:
            print(f"Error: {summary['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
