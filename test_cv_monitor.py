#!/usr/bin/env python3
"""Computer vision monitoring task for GUI testing.

This module runs as a separate process/thread that monitors the visual
output of the GUI application and converts visual correctness into
numerical metrics.

Key features:
- Runs independently from the drawing loop
- Started on execution and runs for a configurable duration (default: 15s)
- Uses computer vision to extract numerical metrics from visual output
- Outputs JSON-serializable metrics for automated testing
"""

import time
import json
import sys
from typing import Dict, List, Optional
from pathlib import Path
from multiprocessing import Process, Queue
import numpy as np
import cv2


class CVMonitor:
    """Computer vision monitor for visual GUI testing."""
    
    def __init__(self, duration: float = 15.0, capture_func=None, verbose: bool = False):
        """Initialize CV monitor.
        
        Args:
            duration: How long to monitor (seconds)
            capture_func: Function to capture screen frames (returns np.ndarray)
            verbose: Enable verbose logging
        """
        self.duration = duration
        self.capture_func = capture_func
        self.verbose = verbose
        self.metrics = []
        self.start_time = None
        
    def _log(self, msg: str):
        """Log message if verbose enabled."""
        if self.verbose:
            print(f"[CVMonitor] {msg}", file=sys.stderr)
    
    def analyze_frame(self, frame: np.ndarray, frame_num: int) -> Dict:
        """Analyze a single frame and extract numerical metrics.
        
        Args:
            frame: RGB numpy array of screen capture
            frame_num: Frame sequence number
            
        Returns:
            Dict of numerical metrics extracted from frame
        """
        metrics = {
            'frame_num': frame_num,
            'timestamp': time.time() - self.start_time if self.start_time else 0,
        }
        
        # Convert to different color spaces for analysis
        hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        
        # Metric 1: Detect red overlay regions
        # Red in HSV (wraps around at 0/180)
        lower_red1 = np.array([0, 100, 100])
        upper_red1 = np.array([10, 255, 255])
        mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
        
        lower_red2 = np.array([170, 100, 100])
        upper_red2 = np.array([180, 255, 255])
        mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
        
        red_mask = cv2.bitwise_or(mask1, mask2)
        
        # Count red pixels
        red_pixel_count = np.count_nonzero(red_mask)
        red_percentage = (red_pixel_count / red_mask.size) * 100
        
        metrics['red_pixel_count'] = int(red_pixel_count)
        metrics['red_percentage'] = float(red_percentage)
        
        # Metric 2: Detect red rectangles using contours
        contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        rectangles = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 1000:  # Filter noise
                continue
            
            x, y, w, h = cv2.boundingRect(cnt)
            
            # Calculate aspect ratio and solidity
            aspect_ratio = float(w) / h if h > 0 else 0
            hull = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            solidity = float(area) / hull_area if hull_area > 0 else 0
            
            rectangles.append({
                'x': int(x),
                'y': int(y),
                'width': int(w),
                'height': int(h),
                'area': int(area),
                'aspect_ratio': float(aspect_ratio),
                'solidity': float(solidity)
            })
        
        # Sort by area (largest first)
        rectangles.sort(key=lambda r: r['area'], reverse=True)
        
        metrics['rectangle_count'] = len(rectangles)
        if rectangles:
            metrics['primary_rectangle'] = rectangles[0]
            if len(rectangles) > 1:
                metrics['secondary_rectangles'] = rectangles[1:min(4, len(rectangles))]
        
        # Metric 3: Overall image statistics
        metrics['frame_mean_intensity'] = float(np.mean(gray))
        metrics['frame_std_intensity'] = float(np.std(gray))
        metrics['frame_min_intensity'] = int(np.min(gray))
        metrics['frame_max_intensity'] = int(np.max(gray))
        
        # Metric 4: Edge detection (to verify real content vs black screen)
        edges = cv2.Canny(gray, 50, 150)
        edge_pixel_count = np.count_nonzero(edges)
        edge_percentage = (edge_pixel_count / edges.size) * 100
        
        metrics['edge_pixel_count'] = int(edge_pixel_count)
        metrics['edge_percentage'] = float(edge_percentage)
        
        return metrics
    
    def detect_movement(self, metrics_history: List[Dict]) -> Dict:
        """Analyze metrics history to detect movement patterns.
        
        Args:
            metrics_history: List of per-frame metrics
            
        Returns:
            Dict with movement analysis results
        """
        if len(metrics_history) < 3:
            return {'movement_detected': False, 'reason': 'insufficient_frames'}
        
        # Extract primary rectangle positions over time
        positions = []
        for m in metrics_history:
            if 'primary_rectangle' in m:
                positions.append((m['frame_num'], m['primary_rectangle']['x']))
        
        if len(positions) < 3:
            return {'movement_detected': False, 'reason': 'insufficient_rectangles'}
        
        # Calculate displacement between consecutive frames
        displacements = []
        for i in range(1, len(positions)):
            frame_diff = positions[i][0] - positions[i-1][0]
            pos_diff = positions[i][1] - positions[i-1][1]
            
            if frame_diff > 0:  # Only if frames are sequential
                displacements.append(pos_diff)
        
        if not displacements:
            return {'movement_detected': False, 'reason': 'no_displacements'}
        
        # Handle wraparound (rectangle going back to left edge)
        screen_width = 1920  # TODO: get from frame dimensions
        displacements_adjusted = []
        for d in displacements:
            if d < -1000:  # Likely wraparound
                displacements_adjusted.append(d + screen_width)
            else:
                displacements_adjusted.append(d)
        
        # Filter out zero displacements (same position)
        positive_displacements = [d for d in displacements_adjusted if d > 0]
        
        if not positive_displacements:
            return {
                'movement_detected': False,
                'reason': 'no_positive_displacement',
                'displacements': displacements_adjusted
            }
        
        avg_displacement = np.mean(positive_displacements)
        std_displacement = np.std(positive_displacements)
        
        # Movement is detected if average displacement is within expected range
        # Expected: 5 pixels per 33ms frame, but we might sample at different rates
        movement_detected = 2 <= avg_displacement <= 100
        
        return {
            'movement_detected': movement_detected,
            'avg_displacement': float(avg_displacement),
            'std_displacement': float(std_displacement),
            'displacement_count': len(positive_displacements),
            'positions': positions
        }
    
    def detect_feedback_loop(self, metrics_history: List[Dict]) -> Dict:
        """Detect if there's a feedback loop (overlay capturing itself).
        
        Args:
            metrics_history: List of per-frame metrics
            
        Returns:
            Dict with feedback loop analysis
        """
        rect_counts = [m['rectangle_count'] for m in metrics_history if 'rectangle_count' in m]
        
        if not rect_counts:
            return {'feedback_detected': None, 'reason': 'no_rectangles'}
        
        max_count = max(rect_counts)
        avg_count = np.mean(rect_counts)
        
        # If we ever see more than 1 rectangle, it's likely a feedback loop
        feedback_detected = max_count > 1
        
        return {
            'feedback_detected': feedback_detected,
            'max_rectangle_count': int(max_count),
            'avg_rectangle_count': float(avg_count),
            'rect_count_distribution': {
                str(i): rect_counts.count(i) 
                for i in set(rect_counts)
            }
        }
    
    def run(self, output_queue: Optional[Queue] = None) -> Dict:
        """Run the monitoring loop for configured duration.
        
        Args:
            output_queue: Optional queue to send periodic updates
            
        Returns:
            Dict with complete monitoring results
        """
        self._log(f"Starting CV monitor (duration: {self.duration}s)")
        self.start_time = time.time()
        
        frame_num = 0
        capture_interval = 0.1  # 100ms between captures
        
        try:
            while time.time() - self.start_time < self.duration:
                # Capture frame
                if self.capture_func:
                    frame = self.capture_func()
                else:
                    self._log("No capture function provided, using dummy frame")
                    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
                
                # Analyze frame
                frame_metrics = self.analyze_frame(frame, frame_num)
                self.metrics.append(frame_metrics)
                
                # Send update to queue if provided
                if output_queue:
                    output_queue.put(('frame', frame_metrics))
                
                frame_num += 1
                time.sleep(capture_interval)
        
        except Exception as e:
            self._log(f"Error during monitoring: {e}")
            if output_queue:
                output_queue.put(('error', str(e)))
        
        # Analyze complete results
        movement_analysis = self.detect_movement(self.metrics)
        feedback_analysis = self.detect_feedback_loop(self.metrics)
        
        results = {
            'duration': time.time() - self.start_time,
            'total_frames': frame_num,
            'frame_metrics': self.metrics,
            'movement_analysis': movement_analysis,
            'feedback_analysis': feedback_analysis,
            'timestamp': time.time()
        }
        
        # Send final results
        if output_queue:
            output_queue.put(('complete', results))
        
        self._log(f"Monitoring complete: {frame_num} frames analyzed")
        return results
    
    def save_results(self, filepath: str, results: Dict = None):
        """Save monitoring results to JSON file.
        
        Args:
            filepath: Path to save JSON file
            results: Results dict (uses self.metrics if not provided)
        """
        if results is None:
            results = {
                'duration': self.duration,
                'total_frames': len(self.metrics),
                'frame_metrics': self.metrics,
                'movement_analysis': self.detect_movement(self.metrics),
                'feedback_analysis': self.detect_feedback_loop(self.metrics),
                'timestamp': time.time()
            }
        
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2)
        
        self._log(f"Results saved to {filepath}")


def run_monitor_process(duration: float, capture_func, output_queue: Queue, verbose: bool = False):
    """Entry point for running monitor as a separate process.
    
    Args:
        duration: How long to monitor
        capture_func: Screen capture function
        output_queue: Queue for sending results
        verbose: Enable verbose logging
    """
    monitor = CVMonitor(duration=duration, capture_func=capture_func, verbose=verbose)
    results = monitor.run(output_queue=output_queue)
    return results


def main():
    """CLI entry point for standalone testing."""
    import argparse
    
    parser = argparse.ArgumentParser(description='CV Monitor for GUI Testing')
    parser.add_argument('--duration', type=float, default=15.0,
                       help='Monitoring duration in seconds (default: 15)')
    parser.add_argument('--output', type=str, default='cv_monitor_results.json',
                       help='Output JSON file path')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Import PyQt6 capture function
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QScreen
    import tempfile
    import os
    
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    def capture_frame() -> np.ndarray:
        """Capture screen using PyQt6."""
        screen = app.primaryScreen()
        pixmap = screen.grabWindow(0)
        
        fd, temp_path = tempfile.mkstemp(suffix='.png')
        os.close(fd)
        
        try:
            pixmap.save(temp_path, 'PNG')
            frame = cv2.imread(temp_path)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return frame
        finally:
            if Path(temp_path).exists():
                Path(temp_path).unlink()
    
    # Run monitor
    monitor = CVMonitor(duration=args.duration, capture_func=capture_frame, verbose=args.verbose)
    results = monitor.run()
    
    # Save results
    monitor.save_results(args.output, results)
    
    # Print summary
    print("\n" + "="*60)
    print("CV MONITORING RESULTS")
    print("="*60)
    print(f"Duration: {results['duration']:.2f}s")
    print(f"Total frames: {results['total_frames']}")
    print(f"\nMovement Analysis:")
    print(f"  Detected: {results['movement_analysis'].get('movement_detected', 'N/A')}")
    if 'avg_displacement' in results['movement_analysis']:
        print(f"  Avg displacement: {results['movement_analysis']['avg_displacement']:.2f} px")
    print(f"\nFeedback Loop Analysis:")
    print(f"  Detected: {results['feedback_analysis'].get('feedback_detected', 'N/A')}")
    print(f"  Max rectangles: {results['feedback_analysis'].get('max_rectangle_count', 'N/A')}")
    print("="*60)
    print(f"\nResults saved to: {args.output}")


if __name__ == '__main__':
    main()
