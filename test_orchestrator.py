#!/usr/bin/env python3
"""
Test Orchestrator - Launches main program and appropriate test agent(s).
Coordinates parallel testing on X11 and Wayland systems.
"""

import os
import sys
import subprocess
import time
import signal
from pathlib import Path


def detect_display_server():
    """Detect if running X11, Wayland, or both."""
    session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
    wayland_display = os.environ.get('WAYLAND_DISPLAY', '')
    x_display = os.environ.get('DISPLAY', '')
    
    systems = []
    
    if session_type == 'wayland' or wayland_display:
        systems.append('wayland')
    
    if session_type == 'x11' or x_display:
        systems.append('x11')
    
    # If session type not set but displays are, infer from that
    if not systems:
        if wayland_display:
            systems.append('wayland')
        if x_display:
            systems.append('x11')
    
    return systems


def check_dependencies():
    """Check if required screen capture tools are available."""
    print("[Orchestrator] Checking dependencies...")
    
    # X11 tools
    x11_tools = []
    for tool in ['scrot', 'import']:
        try:
            result = subprocess.run(['which', tool], capture_output=True, timeout=1)
            if result.returncode == 0:
                x11_tools.append(tool)
        except:
            pass
    
    # Wayland tools
    wayland_tools = []
    for tool in ['grim', 'gnome-screenshot', 'spectacle']:
        try:
            result = subprocess.run(['which', tool], capture_output=True, timeout=1)
            if result.returncode == 0:
                wayland_tools.append(tool)
        except:
            pass
    
    return x11_tools, wayland_tools


def main():
    """Main orchestrator logic."""
    print("=" * 70)
    print("TEST ORCHESTRATOR - Visual Testing System")
    print("=" * 70)
    print()
    
    # Detect display systems
    systems = detect_display_server()
    print(f"[Orchestrator] Detected display systems: {', '.join(systems) if systems else 'NONE'}")
    
    if not systems:
        print("[Orchestrator] ERROR: Could not detect X11 or Wayland")
        print("[Orchestrator] Set DISPLAY or WAYLAND_DISPLAY environment variable")
        sys.exit(1)
    
    # Check dependencies
    x11_tools, wayland_tools = check_dependencies()
    
    if 'x11' in systems:
        print(f"[Orchestrator] X11 capture tools available: {', '.join(x11_tools) if x11_tools else 'NONE'}")
        if not x11_tools:
            print("[Orchestrator] WARNING: No X11 capture tools found (install scrot or imagemagick)")
    
    if 'wayland' in systems:
        print(f"[Orchestrator] Wayland capture tools available: {', '.join(wayland_tools) if wayland_tools else 'NONE'}")
        if not wayland_tools:
            print("[Orchestrator] WARNING: No Wayland capture tools found (install grim, gnome-screenshot, or spectacle)")
    
    print()
    
    # Start the main program
    print("[Orchestrator] Starting main program...")
    main_process = subprocess.Popen(
        [sys.executable, 'main.py'],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    main_pid = main_process.pid
    print(f"[Orchestrator] Main program started with PID {main_pid}")
    
    # Give program time to initialize
    print("[Orchestrator] Waiting 2 seconds for program initialization...")
    time.sleep(2)
    
    # Check if main program is still running
    if main_process.poll() is not None:
        print("[Orchestrator] ERROR: Main program exited prematurely")
        output = main_process.stdout.read()
        print(output)
        sys.exit(1)
    
    print("[Orchestrator] Main program running successfully")
    print()
    
    # Start test agents in parallel
    test_agents = []
    
    if 'x11' in systems and x11_tools:
        print("[Orchestrator] Starting X11 test agent...")
        x11_agent = subprocess.Popen(
            [sys.executable, 'test_agent_x11.py', str(main_pid), 'test_results_x11.json'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        test_agents.append(('x11', x11_agent))
        print(f"[Orchestrator] X11 agent started with PID {x11_agent.pid}")
    
    if 'wayland' in systems and wayland_tools:
        print("[Orchestrator] Starting Wayland test agent...")
        wayland_agent = subprocess.Popen(
            [sys.executable, 'test_agent_wayland.py', str(main_pid), 'test_results_wayland.json'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        test_agents.append(('wayland', wayland_agent))
        print(f"[Orchestrator] Wayland agent started with PID {wayland_agent.pid}")
    
    if not test_agents:
        print("[Orchestrator] ERROR: No test agents could be started")
        print("[Orchestrator] Killing main program...")
        main_process.terminate()
        sys.exit(1)
    
    print()
    print(f"[Orchestrator] {len(test_agents)} test agent(s) running in parallel")
    print("[Orchestrator] Agents will run for 15 seconds then terminate main program")
    print("[Orchestrator] Monitoring output...")
    print()
    
    # Monitor test agents and collect output
    agent_outputs = {name: [] for name, _ in test_agents}
    
    # Wait for all test agents to complete
    for name, agent in test_agents:
        print(f"[Orchestrator] Waiting for {name} agent to complete...")
        
        # Read output in real-time
        for line in agent.stdout:
            line = line.strip()
            if line:
                agent_outputs[name].append(line)
                print(line)
        
        agent.wait()
        print(f"[Orchestrator] {name} agent completed with exit code {agent.returncode}")
        print()
    
    # Ensure main program is terminated
    print("[Orchestrator] Checking main program status...")
    if main_process.poll() is None:
        print("[Orchestrator] Main program still running, terminating...")
        main_process.terminate()
        try:
            main_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            print("[Orchestrator] Main program didn't terminate, killing...")
            main_process.kill()
    else:
        print(f"[Orchestrator] Main program already exited with code {main_process.returncode}")
    
    print()
    print("=" * 70)
    print("TEST ORCHESTRATION COMPLETE")
    print("=" * 70)
    
    # Print summary of results files
    print("\nResults files generated:")
    for name, _ in test_agents:
        result_file = f"test_results_{name}.json"
        if os.path.exists(result_file):
            size = os.path.getsize(result_file)
            print(f"  - {result_file} ({size} bytes)")
        else:
            print(f"  - {result_file} (NOT FOUND)")
    
    print("\nUse 'python test_analyzer.py' to view detailed results")
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Orchestrator] Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[Orchestrator] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
