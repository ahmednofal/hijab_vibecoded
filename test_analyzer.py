#!/usr/bin/env python3
"""
Test Analyzer - Reads and analyzes results from X11 and Wayland test agents.
Provides comprehensive comparison and feedback for coding agents.
"""

import json
import sys
from pathlib import Path
from datetime import datetime


def load_results(filename):
    """Load test results from JSON file."""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing {filename}: {e}")
        return None


def print_detailed_results(results, agent_name):
    """Print detailed results for a specific agent."""
    print("\n" + "=" * 70)
    print(f"{agent_name.upper()} TEST RESULTS")
    print("=" * 70)
    
    if not results:
        print(f"No results found for {agent_name}")
        return False
    
    print(f"Test timestamp: {results.get('timestamp', 'unknown')}")
    print(f"Target PID: {results.get('target_pid', 'unknown')}")
    print(f"Test duration: {results.get('test_duration', 0)} seconds")
    print(f"Samples collected: {results.get('samples_collected', 0)}")
    print()
    
    summary = results.get('summary', {})
    
    if 'error' in summary:
        print(f"ERROR: {summary['error']}")
        return False
    
    # Print summary statistics
    print("SUMMARY STATISTICS:")
    print("-" * 70)
    print(f"  Total samples: {summary.get('total_samples', 0)}")
    print(f"  Red overlay detected: {summary.get('red_detected_count', 0)} / {summary.get('total_samples', 0)} samples")
    print(f"  Detection rate: {summary.get('red_detected_percent', 0):.1f}%")
    print(f"  Average red coverage: {summary.get('avg_red_coverage', 0):.2f}%")
    print(f"  Maximum red coverage: {summary.get('max_red_coverage', 0):.2f}%")
    print(f"  Average movement: {summary.get('avg_movement', 0):.1f} pixels")
    print(f"  Maximum movement: {summary.get('max_movement', 0):.1f} pixels")
    print(f"  Animation detected: {'YES' if summary.get('is_animated', False) else 'NO'}")
    print()
    
    # Sample-by-sample breakdown
    samples = results.get('samples', [])
    if samples:
        print("SAMPLE-BY-SAMPLE BREAKDOWN:")
        print("-" * 70)
        print(f"{'Time':>6s} {'Red':>5s} {'Coverage':>10s} {'Movement':>10s} {'Status':>10s}")
        print("-" * 70)
        
        for i, sample in enumerate(samples[:30]):  # Show first 30 samples
            time_s = sample.get('timestamp', 0)
            red_det = 'YES' if sample.get('red_overlay_detected', False) else 'NO'
            coverage = sample.get('red_coverage_percent', 0)
            movement = sample.get('red_movement_pixels', 0) if 'red_movement_pixels' in sample else 0
            is_moving = sample.get('is_moving', False)
            status = 'MOVING' if is_moving else 'STATIC'
            
            print(f"{time_s:6.1f} {red_det:>5s} {coverage:9.2f}% {movement:9.1f}px {status:>10s}")
        
        if len(samples) > 30:
            print(f"... ({len(samples) - 30} more samples)")
    
    return True


def compare_results(x11_results, wayland_results):
    """Compare results from X11 and Wayland agents."""
    print("\n" + "=" * 70)
    print("COMPARATIVE ANALYSIS")
    print("=" * 70)
    
    if not x11_results and not wayland_results:
        print("No results available for comparison")
        return
    
    if x11_results and wayland_results:
        x11_sum = x11_results.get('summary', {})
        way_sum = wayland_results.get('summary', {})
        
        print(f"{'Metric':<30s} {'X11':>15s} {'Wayland':>15s} {'Difference':>15s}")
        print("-" * 70)
        
        metrics = [
            ('Samples collected', 'total_samples', ''),
            ('Detection rate', 'red_detected_percent', '%'),
            ('Avg red coverage', 'avg_red_coverage', '%'),
            ('Max red coverage', 'max_red_coverage', '%'),
            ('Avg movement', 'avg_movement', 'px'),
            ('Max movement', 'max_movement', 'px'),
        ]
        
        for label, key, unit in metrics:
            x11_val = x11_sum.get(key, 0)
            way_val = way_sum.get(key, 0)
            diff = x11_val - way_val
            
            print(f"{label:<30s} {x11_val:14.2f}{unit:>1s} {way_val:14.2f}{unit:>1s} {diff:+14.2f}{unit:>1s}")
        
        # Animation detection
        x11_anim = 'YES' if x11_sum.get('is_animated', False) else 'NO'
        way_anim = 'YES' if way_sum.get('is_animated', False) else 'NO'
        print(f"{'Animation detected':<30s} {x11_anim:>15s} {way_anim:>15s} {'':>15s}")
        
    elif x11_results:
        print("Only X11 results available - cannot compare")
    elif wayland_results:
        print("Only Wayland results available - cannot compare")


def generate_feedback(x11_results, wayland_results):
    """Generate actionable feedback for coding agents."""
    print("\n" + "=" * 70)
    print("FEEDBACK FOR CODING AGENTS")
    print("=" * 70)
    
    feedback = []
    
    # Analyze X11
    if x11_results:
        x11_sum = x11_results.get('summary', {})
        detection_rate = x11_sum.get('red_detected_percent', 0)
        animation = x11_sum.get('is_animated', False)
        avg_coverage = x11_sum.get('avg_red_coverage', 0)
        
        if detection_rate < 50:
            feedback.append("❌ X11: Low overlay detection rate - overlay may not be rendering correctly")
        elif detection_rate < 80:
            feedback.append("⚠️  X11: Moderate overlay detection - some frames missing overlay")
        else:
            feedback.append("✓ X11: Good overlay detection rate")
        
        if not animation:
            feedback.append("❌ X11: No animation detected - rectangle should be moving")
        else:
            feedback.append("✓ X11: Animation working correctly")
        
        if avg_coverage < 5:
            feedback.append("⚠️  X11: Very low red coverage - overlay might be too small")
        elif avg_coverage > 50:
            feedback.append("⚠️  X11: Very high red coverage - overlay might be too large")
    
    # Analyze Wayland
    if wayland_results:
        way_sum = wayland_results.get('summary', {})
        detection_rate = way_sum.get('red_detected_percent', 0)
        animation = way_sum.get('is_animated', False)
        avg_coverage = way_sum.get('avg_red_coverage', 0)
        
        if detection_rate < 50:
            feedback.append("❌ Wayland: Low overlay detection rate - overlay may not be rendering correctly")
        elif detection_rate < 80:
            feedback.append("⚠️  Wayland: Moderate overlay detection - some frames missing overlay")
        else:
            feedback.append("✓ Wayland: Good overlay detection rate")
        
        if not animation:
            feedback.append("❌ Wayland: No animation detected - rectangle should be moving")
        else:
            feedback.append("✓ Wayland: Animation working correctly")
        
        if avg_coverage < 5:
            feedback.append("⚠️  Wayland: Very low red coverage - overlay might be too small")
        elif avg_coverage > 50:
            feedback.append("⚠️  Wayland: Very high red coverage - overlay might be too large")
    
    # Compare if both available
    if x11_results and wayland_results:
        x11_sum = x11_results.get('summary', {})
        way_sum = wayland_results.get('summary', {})
        
        x11_rate = x11_sum.get('red_detected_percent', 0)
        way_rate = way_sum.get('red_detected_percent', 0)
        
        if abs(x11_rate - way_rate) > 20:
            feedback.append("⚠️  Large discrepancy between X11 and Wayland - check platform-specific code")
    
    if feedback:
        for item in feedback:
            print(f"  {item}")
    else:
        print("  No specific feedback generated")
    
    print()


def main():
    """Main analyzer function."""
    print("=" * 70)
    print("TEST RESULTS ANALYZER")
    print("=" * 70)
    
    # Load results
    x11_results = load_results('test_results_x11.json')
    wayland_results = load_results('test_results_wayland.json')
    
    if not x11_results and not wayland_results:
        print("\nNo test results found.")
        print("Run 'python test_orchestrator.py' first to generate test data.")
        sys.exit(1)
    
    # Print detailed results
    if x11_results:
        print_detailed_results(x11_results, 'X11')
    
    if wayland_results:
        print_detailed_results(wayland_results, 'Wayland')
    
    # Compare results
    if x11_results or wayland_results:
        compare_results(x11_results, wayland_results)
    
    # Generate feedback
    generate_feedback(x11_results, wayland_results)
    
    print("=" * 70)
    print("Analysis complete")
    print("=" * 70)


if __name__ == '__main__':
    main()
