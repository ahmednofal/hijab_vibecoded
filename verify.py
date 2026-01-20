#!/usr/bin/env python3
"""Automated verification system for overlay correctness.

This module provides machine-readable validation that:
1. Red rectangle is moving (displacement detected numerically)
2. No feedback loop (only one rectangle detected per frame)
3. Background is real screen content (not black/grey, stays consistent)

NOTE: This version uses PyQt6 screen capture (works on both X11 and Wayland)
instead of X11-only Xlib capture.
"""

import sys
import time
import json
import argparse
import subprocess
import signal
from pathlib import Path
from typing import Optional, Tuple, Dict, List
import numpy as np
import cv2
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QScreen
from skimage.metrics import structural_similarity as ssim


class OverlayVerifier:
    """Numerical verification of overlay system behavior."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.app = None
        self.screen = None
        self.width = 0
        self.height = 0
        self.reference_background = None
        
    def _log(self, message: str):
        """Print if verbose mode enabled."""
        if self.verbose:
            print(f"[Verify] {message}", file=sys.stderr)
    
    def initialize_capture(self):
        """Initialize PyQt6 for screen capture."""
        if self.app is None:
            self.app = QApplication.instance()
            if self.app is None:
                self.app = QApplication(sys.argv)
        
        self.screen = self.app.primaryScreen()
        geom = self.screen.geometry()
        self.width = geom.width()
        self.height = geom.height()
        self._log(f"Initialized PyQt6 capture: {self.width}x{self.height}")
    
    def capture_frame(self) -> np.ndarray:
        """Capture current screen content as RGB numpy array."""
        if not self.screen:
            self.initialize_capture()
        
        # Capture screen using PyQt6
        pixmap = self.screen.grabWindow(0)
        
        # Save to temp file and read back with OpenCV (most reliable)
        import tempfile
        import os
        
        fd, temp_path = tempfile.mkstemp(suffix='.png')
        os.close(fd)
        
        try:
            pixmap.save(temp_path, 'PNG')
            frame = cv2.imread(temp_path)
            if frame is None:
                raise ValueError(f"Failed to read captured screenshot from {temp_path}")
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return frame
        finally:
            if Path(temp_path).exists():
                Path(temp_path).unlink()

    
    def detect_red_rectangle(self, frame: np.ndarray) -> Optional[Dict]:
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
        
        # Find the largest contour (should be our rectangle)
        rectangles = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 1000:  # Filter out noise (small detections)
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
            'count': len(rectangles)  # Number of red rectangles detected
        }
    
    def capture_background_reference(self) -> np.ndarray:
        """Capture background before overlay starts."""
        self._log("Capturing background reference...")
        frame = self.capture_frame()
        self.reference_background = frame.copy()
        
        # Check it's not all black/grey
        mean_val = np.mean(frame)
        std_val = np.std(frame)
        self._log(f"Background stats: mean={mean_val:.2f}, std={std_val:.2f}")
        
        if mean_val < 5.0:
            raise ValueError("Background is black - screen capture failed")
        if std_val < 10.0:
            raise ValueError("Background has no variation - likely grey/uniform")
        
        return frame
    
    def compare_backgrounds(self, current_frame: np.ndarray, rect_info: Optional[Dict] = None) -> float:
        """Compare current frame background to reference.
        
        Args:
            current_frame: Current captured frame
            rect_info: Rectangle detection info to mask out rectangle region
            
        Returns:
            Similarity score (0.0 to 1.0, higher is better)
        """
        if self.reference_background is None:
            raise ValueError("Must capture reference background first")
        
        # Create masks to exclude rectangle region from comparison
        ref_compare = self.reference_background.copy()
        curr_compare = current_frame.copy()
        
        if rect_info:
            # Mask out the rectangle region in both images
            x, y, w, h = rect_info['x'], rect_info['y'], rect_info['width'], rect_info['height']
            # Extend mask slightly to account for anti-aliasing
            margin = 5
            x1 = max(0, x - margin)
            y1 = max(0, y - margin)
            x2 = min(current_frame.shape[1], x + w + margin)
            y2 = min(current_frame.shape[0], y + h + margin)
            
            # Set rectangle region to black in both (will be ignored in comparison)
            ref_compare[y1:y2, x1:x2] = 0
            curr_compare[y1:y2, x1:x2] = 0
        
        # Convert to grayscale for SSIM
        ref_gray = cv2.cvtColor(ref_compare, cv2.COLOR_RGB2GRAY)
        curr_gray = cv2.cvtColor(curr_compare, cv2.COLOR_RGB2GRAY)
        
        # Compute structural similarity
        score = ssim(ref_gray, curr_gray)
        
        return score
    
    def run_displacement_test(self, duration_seconds: float = 5.0, 
                             output_json: Optional[str] = None) -> Dict:
        """Run automated verification test.
        
        Args:
            duration_seconds: How long to run test
            output_json: Optional path to save detailed results
            
        Returns:
            Dict with test results and pass/fail status
        """
        results = {
            'test_start_time': time.time(),
            'duration': duration_seconds,
            'frames': [],
            'summary': {
                'total_frames': 0,
                'rectangles_detected': 0,
                'movement_detected': False,
                'feedback_loop_detected': False,
                'background_stable': False,
                'tests_passed': []
            }
        }
        
        # Capture reference background (before starting overlay)
        try:
            self.capture_background_reference()
        except Exception as e:
            self._log(f"ERROR: Failed to capture reference: {e}")
            results['summary']['error'] = str(e)
            return results
        
        # Start the overlay system
        self._log("Starting overlay system...")
        overlay_process = subprocess.Popen(
            [sys.executable, 'main.py'],
            cwd=Path(__file__).parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
        )
        
        # Give it time to start
        time.sleep(2.0)
        
        try:
            start_time = time.time()
            frame_count = 0
            positions = []
            
            while time.time() - start_time < duration_seconds:
                frame = self.capture_frame()
                rect_info = self.detect_red_rectangle(frame)
                
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
                    
                    # Check background similarity
                    bg_score = self.compare_backgrounds(frame, rect_info)
                    frame_data['bg_similarity'] = float(bg_score)
                
                results['frames'].append(frame_data)
                frame_count += 1
                
                # Print progress
                if rect_info:
                    print(json.dumps(frame_data))
                
                time.sleep(0.1)  # 100ms between captures
        
        finally:
            # Stop overlay system
            self._log("Stopping overlay system...")
            overlay_process.terminate()
            try:
                overlay_process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                overlay_process.kill()
        
        # Analyze results
        results['summary']['total_frames'] = frame_count
        results['summary']['rectangles_detected'] = sum(1 for f in results['frames'] if f['rect_detected'])
        
        # Test 1: Movement detection
        if len(positions) >= 3:
            # Check if positions are increasing
            differences = np.diff(positions)
            # Handle wraparound (when rectangle goes back to 0)
            differences = [d if d > -1000 else d + self.width for d in differences]
            avg_displacement = np.mean([d for d in differences if d > 0])
            
            # Expected: ~5 pixels per frame, but we capture every 100ms
            # Overlay updates every 33ms, so ~3 updates between captures = ~15 pixels
            movement_ok = 10 <= avg_displacement <= 50
            results['summary']['movement_detected'] = movement_ok
            results['summary']['avg_displacement'] = float(avg_displacement)
            if movement_ok:
                results['summary']['tests_passed'].append('movement')
            
            self._log(f"Average displacement: {avg_displacement:.2f} pixels")
        
        # Test 2: Feedback loop check (multiple rectangles)
        rect_counts = [f.get('rect_count', 0) for f in results['frames'] if f['rect_detected']]
        if rect_counts:
            max_count = max(rect_counts)
            no_feedback_loop = max_count == 1
            results['summary']['feedback_loop_detected'] = not no_feedback_loop
            results['summary']['max_rect_count'] = max_count
            if no_feedback_loop:
                results['summary']['tests_passed'].append('no_feedback_loop')
            
            self._log(f"Max rectangles detected: {max_count}")
        
        # Test 3: Background stability
        bg_scores = [f.get('bg_similarity', 0) for f in results['frames'] if 'bg_similarity' in f]
        if bg_scores:
            avg_bg_score = np.mean(bg_scores)
            min_bg_score = np.min(bg_scores)
            bg_stable = avg_bg_score > 0.85  # 85% similarity threshold
            results['summary']['background_stable'] = bg_stable
            results['summary']['avg_bg_similarity'] = float(avg_bg_score)
            results['summary']['min_bg_similarity'] = float(min_bg_score)
            if bg_stable:
                results['summary']['tests_passed'].append('background_stable')
            
            self._log(f"Background similarity: avg={avg_bg_score:.3f}, min={min_bg_score:.3f}")
        
        # Overall pass/fail
        expected_tests = 3
        tests_passed = len(results['summary']['tests_passed'])
        results['summary']['all_tests_passed'] = (tests_passed == expected_tests)
        
        # Handle case where no results were obtained
        if 'error' in results['summary']:
            results['summary']['all_tests_passed'] = False
        
        # Save detailed results if requested
        if output_json:
            with open(output_json, 'w') as f:
                json.dump(results, f, indent=2)
            self._log(f"Detailed results saved to {output_json}")
        
        return results


def main():
    """CLI entry point for verification system."""
    parser = argparse.ArgumentParser(
        description='Automated verification for overlay system',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --duration 10              # Run 10 second test
  %(prog)s --verbose --output results.json
  %(prog)s --duration 5 -v            # Short verbose test
        """
    )
    parser.add_argument('--duration', type=float, default=5.0,
                       help='Test duration in seconds (default: 5.0)')
    parser.add_argument('--output-json', type=str,
                       help='Path to save detailed JSON results')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Print verbose logging to stderr')
    
    args = parser.parse_args()
    
    # Run verification
    verifier = OverlayVerifier(verbose=args.verbose)
    results = verifier.run_displacement_test(
        duration_seconds=args.duration,
        output_json=args.output_json
    )
    
    # Print summary
    summary = results['summary']
    print("\n" + "="*60, file=sys.stderr)
    print("VERIFICATION RESULTS", file=sys.stderr)
    print("="*60, file=sys.stderr)
    print(f"Total frames captured: {summary['total_frames']}", file=sys.stderr)
    print(f"Rectangles detected: {summary['rectangles_detected']}", file=sys.stderr)
    print(f"\nTests passed: {len(summary['tests_passed'])}/3", file=sys.stderr)
    
    if 'movement' in summary['tests_passed']:
        print(f"  ✓ Movement detected (avg: {summary.get('avg_displacement', 0):.1f} px)", file=sys.stderr)
    else:
        print(f"  ✗ Movement NOT detected", file=sys.stderr)
    
    if 'no_feedback_loop' in summary['tests_passed']:
        print(f"  ✓ No feedback loop", file=sys.stderr)
    else:
        print(f"  ✗ Feedback loop detected (max {summary.get('max_rect_count', 0)} rectangles)", file=sys.stderr)
    
    if 'background_stable' in summary['tests_passed']:
        print(f"  ✓ Background stable (similarity: {summary.get('avg_bg_similarity', 0):.3f})", file=sys.stderr)
    else:
        print(f"  ✗ Background unstable (similarity: {summary.get('avg_bg_similarity', 0):.3f})", file=sys.stderr)
    
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
