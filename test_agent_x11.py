#!/usr/bin/env python3
"""
X11 Testing Agent - Captures visual output and converts to numerical metrics.
Runs for 15 seconds alongside the main program, then kills it.
"""

import sys
import time
import subprocess
import signal
import numpy as np
from PIL import Image
import json
from datetime import datetime
from pathlib import Path


class X11TestAgent:
    """Test agent for X11 display server."""
    
    def __init__(self, target_pid, output_file="test_results_x11.json"):
        self.target_pid = target_pid
        self.output_file = output_file
        self.start_time = time.time()
        self.test_duration = 15  # seconds
        self.samples = []
        self.capture_interval = 0.5  # seconds
        
    def capture_screen_x11(self):
        """Capture screen using X11 tools (scrot or import)."""
        try:
            # Try scrot first (faster)
            result = subprocess.run(
                ['scrot', '-o', '/tmp/test_capture_x11.png'],
                capture_output=True,
                timeout=2
            )
            if result.returncode == 0:
                img = Image.open('/tmp/test_capture_x11.png')
                return np.array(img)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        try:
            # Fallback to ImageMagick's import
            result = subprocess.run(
                ['import', '-window', 'root', '/tmp/test_capture_x11.png'],
                capture_output=True,
                timeout=2
            )
            if result.returncode == 0:
                img = Image.open('/tmp/test_capture_x11.png')
                return np.array(img)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        return None
    
    def analyze_frame(self, frame):
        """Convert visual frame to numerical metrics."""
        if frame is None:
            return None
        
        # Convert to numpy array if needed
        if not isinstance(frame, np.ndarray):
            frame = np.array(frame)
        
        metrics = {
            'timestamp': time.time() - self.start_time,
            'shape': frame.shape,
            'mean_rgb': [float(frame[:, :, i].mean()) for i in range(min(3, frame.shape[2]))],
            'std_rgb': [float(frame[:, :, i].std()) for i in range(min(3, frame.shape[2]))],
            'min_rgb': [float(frame[:, :, i].min()) for i in range(min(3, frame.shape[2]))],
            'max_rgb': [float(frame[:, :, i].max()) for i in range(min(3, frame.shape[2]))],
        }
        
        # Detect red overlay regions (specifically looking for red values)
        if frame.shape[2] >= 3:
            # Look for reddish pixels (high R, lower G and B)
            red_channel = frame[:, :, 0].astype(float)
            green_channel = frame[:, :, 1].astype(float)
            blue_channel = frame[:, :, 2].astype(float)
            
            # Red pixels have R > 200 and R > G+50 and R > B+50
            red_mask = (red_channel > 200) & (red_channel > green_channel + 50) & (red_channel > blue_channel + 50)
            red_pixel_count = np.sum(red_mask)
            red_coverage = red_pixel_count / (frame.shape[0] * frame.shape[1])
            
            metrics['red_overlay_detected'] = bool(red_pixel_count > 1000)  # At least 1000 red pixels
            metrics['red_coverage_percent'] = float(red_coverage * 100)
            metrics['red_pixel_count'] = int(red_pixel_count)
            
            # Detect if red region is moving (compare with previous frame)
            if red_pixel_count > 0:
                y_coords, x_coords = np.where(red_mask)
                center_x = float(np.mean(x_coords))
                center_y = float(np.mean(y_coords))
                metrics['red_center_x'] = center_x
                metrics['red_center_y'] = center_y
                
                # Check if moved from previous position
                if len(self.samples) > 0 and 'red_center_x' in self.samples[-1]:
                    prev_x = self.samples[-1].get('red_center_x', center_x)
                    movement = abs(center_x - prev_x)
                    metrics['red_movement_pixels'] = float(movement)
                    metrics['is_moving'] = movement > 10  # Moved more than 10 pixels
        
        return metrics
    
    def run(self):
        """Main test loop - runs for 15 seconds then kills target."""
        print(f"[X11 Test Agent] Starting test for PID {self.target_pid}")
        print(f"[X11 Test Agent] Will run for {self.test_duration} seconds")
        print(f"[X11 Test Agent] Capturing every {self.capture_interval} seconds")
        
        sample_count = 0
        
        while time.time() - self.start_time < self.test_duration:
            # Capture screen
            frame = self.capture_screen_x11()
            
            if frame is not None:
                # Analyze frame
                metrics = self.analyze_frame(frame)
                
                if metrics:
                    self.samples.append(metrics)
                    sample_count += 1
                    
                    # Print progress
                    elapsed = metrics['timestamp']
                    red_detected = metrics.get('red_overlay_detected', False)
                    red_coverage = metrics.get('red_coverage_percent', 0)
                    
                    print(f"[X11 Test Agent] Sample {sample_count} @ {elapsed:.1f}s: "
                          f"Red={'YES' if red_detected else 'NO'} "
                          f"Coverage={red_coverage:.2f}%")
            else:
                print(f"[X11 Test Agent] Failed to capture frame at {time.time() - self.start_time:.1f}s")
            
            # Wait for next sample
            time.sleep(self.capture_interval)
        
        # Test complete - kill target process
        print(f"\n[X11 Test Agent] Test duration complete")
        self.save_results()
        self.kill_target()
    
    def save_results(self):
        """Save test results to JSON file."""
        results = {
            'agent': 'X11',
            'target_pid': self.target_pid,
            'test_duration': self.test_duration,
            'samples_collected': len(self.samples),
            'timestamp': datetime.now().isoformat(),
            'samples': self.samples,
            'summary': self.generate_summary()
        }
        
        with open(self.output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"[X11 Test Agent] Results saved to {self.output_file}")
        self.print_summary(results['summary'])
    
    def generate_summary(self):
        """Generate summary statistics from samples."""
        if not self.samples:
            return {'error': 'No samples collected'}
        
        red_detections = [s.get('red_overlay_detected', False) for s in self.samples]
        red_coverages = [s.get('red_coverage_percent', 0) for s in self.samples]
        movements = [s.get('red_movement_pixels', 0) for s in self.samples if 'red_movement_pixels' in s]
        
        summary = {
            'total_samples': len(self.samples),
            'red_detected_count': sum(red_detections),
            'red_detected_percent': (sum(red_detections) / len(red_detections) * 100) if red_detections else 0,
            'avg_red_coverage': np.mean(red_coverages) if red_coverages else 0,
            'max_red_coverage': np.max(red_coverages) if red_coverages else 0,
            'avg_movement': np.mean(movements) if movements else 0,
            'max_movement': np.max(movements) if movements else 0,
            'is_animated': np.mean(movements) > 5 if movements else False,  # Average movement > 5px
        }
        
        return summary
    
    def print_summary(self, summary):
        """Print human-readable summary."""
        print("\n" + "=" * 60)
        print("X11 TEST RESULTS SUMMARY")
        print("=" * 60)
        print(f"Total samples: {summary.get('total_samples', 0)}")
        print(f"Red overlay detected: {summary.get('red_detected_count', 0)}/{summary.get('total_samples', 0)} samples "
              f"({summary.get('red_detected_percent', 0):.1f}%)")
        print(f"Average red coverage: {summary.get('avg_red_coverage', 0):.2f}%")
        print(f"Max red coverage: {summary.get('max_red_coverage', 0):.2f}%")
        print(f"Average movement: {summary.get('avg_movement', 0):.1f} pixels")
        print(f"Max movement: {summary.get('max_movement', 0):.1f} pixels")
        print(f"Animation detected: {'YES' if summary.get('is_animated', False) else 'NO'}")
        print("=" * 60 + "\n")
    
    def kill_target(self):
        """Send kill signal to target process."""
        try:
            print(f"[X11 Test Agent] Sending SIGTERM to PID {self.target_pid}")
            subprocess.run(['kill', '-TERM', str(self.target_pid)], timeout=1)
            time.sleep(1)
            
            # Check if still running
            result = subprocess.run(['ps', '-p', str(self.target_pid)], 
                                  capture_output=True, timeout=1)
            if result.returncode == 0:
                print(f"[X11 Test Agent] Process still running, sending SIGKILL")
                subprocess.run(['kill', '-KILL', str(self.target_pid)], timeout=1)
        except Exception as e:
            print(f"[X11 Test Agent] Error killing target: {e}")


def main():
    """Entry point for X11 test agent."""
    if len(sys.argv) < 2:
        print("Usage: test_agent_x11.py <target_pid>")
        sys.exit(1)
    
    target_pid = int(sys.argv[1])
    output_file = sys.argv[2] if len(sys.argv) > 2 else "test_results_x11.json"
    
    agent = X11TestAgent(target_pid, output_file)
    agent.run()


if __name__ == '__main__':
    main()
