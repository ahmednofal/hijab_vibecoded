#!/usr/bin/env python3
"""Integrated test runner with CV monitoring.

This script orchestrates the complete test:
1. Starts the appropriate overlay (X11 or Wayland)
2. Launches CV monitor in separate process
3. Runs for configured duration (default: 15s)
4. Collects and analyzes results
5. Outputs pass/fail with numerical metrics
"""

import sys
import os
import time
import json
import argparse
import subprocess
import signal
from pathlib import Path
from multiprocessing import Process, Queue
from typing import Dict, Optional
import numpy as np


def detect_display_server() -> str:
    """Detect which display server we're running on.
    
    Returns:
        'x11', 'wayland', or 'unknown'
    """
    session_type = os.environ.get('XDG_SESSION_TYPE', 'unknown').lower()
    
    # Double-check with WAYLAND_DISPLAY and DISPLAY
    if session_type == 'unknown':
        if os.environ.get('WAYLAND_DISPLAY'):
            return 'wayland'
        elif os.environ.get('DISPLAY'):
            return 'x11'
    
    return session_type


def setup_capture_function():
    """Setup screen capture function based on available backends.
    
    Returns:
        Function that captures screen and returns RGB numpy array
    """
    # Try PyQt6 first (works on both X11 and Wayland)
    try:
        from PyQt6.QtWidgets import QApplication
        import cv2
        import tempfile
        
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        
        def capture_pyqt6() -> np.ndarray:
            screen = app.primaryScreen()
            pixmap = screen.grabWindow(0)
            
            fd, temp_path = tempfile.mkstemp(suffix='.png')
            os.close(fd)
            
            try:
                pixmap.save(temp_path, 'PNG')
                frame = cv2.imread(temp_path)
                if frame is None:
                    raise ValueError("Failed to read screenshot")
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                return frame
            finally:
                if Path(temp_path).exists():
                    Path(temp_path).unlink()
        
        print("[TestRunner] Using PyQt6 for screen capture")
        return capture_pyqt6
    
    except ImportError:
        print("[TestRunner] PyQt6 not available")
    
    # Fallback to other methods
    print("[TestRunner] ERROR: No screen capture backend available")
    print("[TestRunner] Please install PyQt6: pip install PyQt6")
    return None


def run_cv_monitor(duration: float, capture_func, results_queue: Queue, verbose: bool = False):
    """Run CV monitor in separate process.
    
    Args:
        duration: How long to monitor
        capture_func: Screen capture function
        results_queue: Queue to send results back
        verbose: Enable verbose logging
    """
    from test_cv_monitor import CVMonitor
    
    monitor = CVMonitor(duration=duration, capture_func=capture_func, verbose=verbose)
    results = monitor.run(output_queue=results_queue)
    results_queue.put(('final', results))


def start_overlay_process(display_server: str, force_backend: Optional[str] = None) -> subprocess.Popen:
    """Start the overlay application process.
    
    Args:
        display_server: 'x11' or 'wayland'
        force_backend: Force specific backend ('x11', 'wayland', 'qt', 'gtk')
        
    Returns:
        Subprocess handle
    """
    env = os.environ.copy()
    
    # Set environment variable to select overlay backend
    if force_backend:
        env['OVERLAY_BACKEND'] = force_backend
    elif display_server == 'x11':
        env['OVERLAY_BACKEND'] = 'x11'
    elif display_server == 'wayland':
        env['OVERLAY_BACKEND'] = 'wayland'
    
    print(f"[TestRunner] Starting overlay (backend: {env.get('OVERLAY_BACKEND', 'auto')})")
    
    process = subprocess.Popen(
        [sys.executable, 'main.py'],
        cwd=Path(__file__).parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
    )
    
    return process


def analyze_results(cv_results: Dict) -> Dict:
    """Analyze CV monitoring results and determine pass/fail.
    
    Args:
        cv_results: Results from CV monitor
        
    Returns:
        Dict with analysis and pass/fail status
    """
    analysis = {
        'timestamp': time.time(),
        'tests': {},
        'overall_pass': False
    }
    
    # Test 1: Movement detection
    movement = cv_results.get('movement_analysis', {})
    movement_pass = movement.get('movement_detected', False)
    
    analysis['tests']['movement'] = {
        'pass': movement_pass,
        'detected': movement.get('movement_detected', False),
        'avg_displacement': movement.get('avg_displacement', 0),
        'reason': movement.get('reason', 'ok' if movement_pass else 'failed')
    }
    
    # Test 2: Feedback loop detection
    feedback = cv_results.get('feedback_analysis', {})
    feedback_detected = feedback.get('feedback_detected', None)
    no_feedback_loop = (feedback_detected is False)  # Must be explicitly False
    
    analysis['tests']['no_feedback_loop'] = {
        'pass': no_feedback_loop,
        'feedback_detected': feedback_detected,
        'max_rectangles': feedback.get('max_rectangle_count', 0)
    }
    
    # Test 3: Visual output present (not black screen)
    frames = cv_results.get('frame_metrics', [])
    if frames:
        # Check that we have reasonable edge detection across frames
        edge_percentages = [f.get('edge_percentage', 0) for f in frames]
        avg_edges = np.mean(edge_percentages) if edge_percentages else 0
        
        # Check intensity variation
        mean_intensities = [f.get('frame_mean_intensity', 0) for f in frames]
        avg_intensity = np.mean(mean_intensities) if mean_intensities else 0
        
        visual_output_ok = (avg_edges > 1.0 and avg_intensity > 10.0)
        
        analysis['tests']['visual_output'] = {
            'pass': visual_output_ok,
            'avg_edge_percentage': float(avg_edges),
            'avg_intensity': float(avg_intensity),
            'total_frames': len(frames)
        }
    else:
        analysis['tests']['visual_output'] = {
            'pass': False,
            'reason': 'no_frames_captured'
        }
    
    # Test 4: Red overlay detected
    red_detections = [f for f in frames if f.get('red_pixel_count', 0) > 0]
    red_detection_rate = len(red_detections) / len(frames) if frames else 0
    red_overlay_ok = red_detection_rate > 0.5  # Should see red in >50% of frames
    
    analysis['tests']['red_overlay'] = {
        'pass': red_overlay_ok,
        'detection_rate': float(red_detection_rate),
        'frames_with_red': len(red_detections),
        'total_frames': len(frames)
    }
    
    # Overall pass: all tests must pass
    all_tests = analysis['tests']
    tests_passed = [name for name, result in all_tests.items() if result.get('pass', False)]
    tests_failed = [name for name, result in all_tests.items() if not result.get('pass', False)]
    
    analysis['overall_pass'] = len(tests_failed) == 0
    analysis['tests_passed'] = tests_passed
    analysis['tests_failed'] = tests_failed
    analysis['pass_rate'] = len(tests_passed) / len(all_tests) if all_tests else 0
    
    return analysis


def main():
    """Main test runner entry point."""
    parser = argparse.ArgumentParser(
        description='Integrated test runner with CV monitoring',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Auto-detect display server, run 15s test
  %(prog)s --duration 30            # Run 30 second test
  %(prog)s --backend x11            # Force X11 backend
  %(prog)s --backend wayland -v     # Force Wayland backend, verbose
  %(prog)s --output results.json    # Save detailed results
        """
    )
    
    parser.add_argument('--duration', type=float, default=15.0,
                       help='Test duration in seconds (default: 15)')
    parser.add_argument('--backend', type=str, choices=['auto', 'x11', 'wayland', 'qt', 'gtk'],
                       default='auto', help='Force specific overlay backend')
    parser.add_argument('--output', type=str, default='test_results.json',
                       help='Output JSON file for detailed results')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--no-monitor', action='store_true',
                       help='Skip CV monitoring (just run overlay)')
    
    args = parser.parse_args()
    
    print("="*70)
    print("INTEGRATED OVERLAY TEST WITH CV MONITORING")
    print("="*70)
    
    # Detect display server
    display_server = detect_display_server()
    print(f"Display Server: {display_server}")
    
    if args.backend == 'auto':
        backend = display_server
    else:
        backend = args.backend
    
    print(f"Overlay Backend: {backend}")
    print(f"Test Duration: {args.duration}s")
    print()
    
    # Setup capture function
    capture_func = setup_capture_function()
    if not capture_func and not args.no_monitor:
        print("ERROR: Cannot run CV monitor without capture function")
        sys.exit(1)
    
    # Start overlay process
    print("[TestRunner] Starting overlay process...")
    overlay_process = start_overlay_process(display_server, backend)
    
    # Give overlay time to initialize
    print("[TestRunner] Waiting for overlay to initialize...")
    time.sleep(3.0)
    
    # Check if overlay is still running
    if overlay_process.poll() is not None:
        print("[TestRunner] ERROR: Overlay process exited prematurely")
        stdout, stderr = overlay_process.communicate()
        if stdout:
            print("Output:", stdout.decode())
        sys.exit(1)
    
    cv_results = None
    
    if not args.no_monitor:
        # Start CV monitor
        print(f"[TestRunner] Starting CV monitor ({args.duration}s)...")
        results_queue = Queue()
        
        monitor_process = Process(
            target=run_cv_monitor,
            args=(args.duration, capture_func, results_queue, args.verbose),
            daemon=False
        )
        monitor_process.start()
        
        # Wait for monitor to complete
        monitor_process.join()
        
        # Collect results
        print("[TestRunner] Collecting results...")
        while not results_queue.empty():
            msg_type, data = results_queue.get()
            if msg_type == 'final':
                cv_results = data
            elif msg_type == 'error':
                print(f"[TestRunner] Monitor error: {data}")
    else:
        # Just run overlay for duration
        print(f"[TestRunner] Running overlay for {args.duration}s (no monitoring)...")
        time.sleep(args.duration)
    
    # Stop overlay
    print("[TestRunner] Stopping overlay process...")
    overlay_process.terminate()
    try:
        overlay_process.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        overlay_process.kill()
        overlay_process.wait()
    
    # Analyze results
    if cv_results:
        print("\n" + "="*70)
        print("ANALYZING RESULTS")
        print("="*70)
        
        analysis = analyze_results(cv_results)
        
        # Print test results
        print(f"\nTests Run: {len(analysis['tests'])}")
        print(f"Tests Passed: {len(analysis['tests_passed'])}")
        print(f"Tests Failed: {len(analysis['tests_failed'])}")
        print(f"Pass Rate: {analysis['pass_rate']*100:.1f}%")
        print()
        
        for test_name, test_result in analysis['tests'].items():
            status = "✓ PASS" if test_result['pass'] else "✗ FAIL"
            print(f"{status} - {test_name}")
            
            # Print relevant details
            if test_name == 'movement':
                if 'avg_displacement' in test_result:
                    print(f"       Avg displacement: {test_result['avg_displacement']:.2f} px")
                if not test_result['pass']:
                    print(f"       Reason: {test_result.get('reason', 'unknown')}")
            
            elif test_name == 'no_feedback_loop':
                print(f"       Max rectangles: {test_result.get('max_rectangles', 0)}")
            
            elif test_name == 'visual_output':
                if 'avg_edge_percentage' in test_result:
                    print(f"       Edge detection: {test_result['avg_edge_percentage']:.2f}%")
                    print(f"       Avg intensity: {test_result['avg_intensity']:.1f}")
            
            elif test_name == 'red_overlay':
                print(f"       Detection rate: {test_result['detection_rate']*100:.1f}%")
                print(f"       Frames with red: {test_result['frames_with_red']}/{test_result['total_frames']}")
        
        print()
        print("="*70)
        
        # Save detailed results
        full_results = {
            'test_config': {
                'duration': args.duration,
                'backend': backend,
                'display_server': display_server,
                'verbose': args.verbose
            },
            'cv_monitoring': cv_results,
            'analysis': analysis
        }
        
        with open(args.output, 'w') as f:
            json.dump(full_results, f, indent=2)
        
        print(f"Detailed results saved to: {args.output}")
        print()
        
        # Final verdict
        if analysis['overall_pass']:
            print("✓✓✓ ALL TESTS PASSED ✓✓✓")
            sys.exit(0)
        else:
            print("✗✗✗ TESTS FAILED ✗✗✗")
            print(f"Failed tests: {', '.join(analysis['tests_failed'])}")
            sys.exit(1)
    else:
        print("\n[TestRunner] No monitoring results (--no-monitor mode)")
        print(f"Overlay ran for {args.duration}s")
        sys.exit(0)


if __name__ == '__main__':
    main()
