#!/usr/bin/env python3
"""Check Windows system requirements."""

import sys
import platform

def check_windows_requirements():
    """Check if Windows system meets requirements."""
    print("=" * 60)
    print("Hijab by Copilot - Windows System Check")
    print("=" * 60)
    print()
    
    all_ok = True
    
    # Check OS
    print("1. Operating System")
    os_name = platform.system()
    os_release = platform.release()
    print(f"   OS: {os_name} {os_release}")
    
    if os_name != "Windows":
        print(f"   ❌ ERROR: This script is for Windows. You're running {os_name}")
        all_ok = False
    else:
        print("   ✓ Windows detected")
    print()
    
    # Check Python version
    print("2. Python Version")
    version = sys.version_info
    print(f"   Python: {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print(f"   ❌ Python 3.8+ required, found {version.major}.{version.minor}")
        all_ok = False
    else:
        print("   ✓ Python version OK")
    print()
    
    # Check for MSS
    print("3. Required Packages")
    
    packages = [
        ("PyQt6", "PyQt6"),
        ("MSS", "mss"),
        ("NumPy", "numpy"),
        ("Pillow", "PIL"),
        ("OpenCV", "cv2"),
        ("MediaPipe", "mediapipe"),
        ("scikit-image", "skimage"),
        ("pywin32", "win32gui")
    ]
    
    for name, module in packages:
        try:
            __import__(module)
            print(f"   ✓ {name} installed")
        except ImportError:
            print(f"   ❌ {name} NOT installed")
            all_ok = False
    print()
    
    # Check screen capture capability
    print("4. Screen Capture Test")
    try:
        import mss
        with mss.mss() as sct:
            monitors = sct.monitors
            print(f"   ✓ MSS working - {len(monitors)-1} monitor(s) detected")
            for i, mon in enumerate(monitors[1:], 1):
                print(f"     - Monitor {i}: {mon['width']}x{mon['height']}")
    except Exception as e:
        print(f"   ❌ Screen capture failed: {e}")
        all_ok = False
    print()
    
    # Check PyQt6
    print("5. GUI Framework Test")
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        screens = app.screens()
        print(f"   ✓ PyQt6 working - {len(screens)} screen(s) detected")
        for i, screen in enumerate(screens):
            geom = screen.geometry()
            print(f"     - Screen {i}: {geom.width()}x{geom.height()} ({screen.name()})")
    except Exception as e:
        print(f"   ❌ PyQt6 test failed: {e}")
        all_ok = False
    print()
    
    # Summary
    print("=" * 60)
    if all_ok:
        print("✓ ALL CHECKS PASSED!")
        print()
        print("Your system is ready to run Hijab by Copilot.")
        print("Run the application with:")
        print("  python main.py")
        print("or double-click:")
        print("  run_windows.bat")
    else:
        print("❌ SOME CHECKS FAILED")
        print()
        print("Please fix the issues above before running the application.")
        print()
        print("To install missing packages, run:")
        print("  pip install -r requirements.txt")
        print("or double-click:")
        print("  setup_windows.bat")
    print("=" * 60)
    
    return all_ok


if __name__ == "__main__":
    try:
        result = check_windows_requirements()
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
