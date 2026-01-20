#!/usr/bin/env python3
"""Check system requirements for overlay system."""

import os
import sys
import subprocess

def check_display_server():
    """Check if running on X11 (required)."""
    session_type = os.environ.get('XDG_SESSION_TYPE', 'unknown')
    
    print(f"Display server: {session_type}")
    
    if session_type != 'x11':
        print("\n" + "="*60)
        print("❌ ERROR: This system requires X11, but you're running on", session_type.upper())
        print("="*60)
        print("\nTo switch to X11:")
        print("1. Log out of your current session")
        print("2. At the login screen, click the gear icon")
        print("3. Select 'GNOME on Xorg' or 'Plasma (X11)'")
        print("4. Log back in")
        print("5. Run this check again")
        print("\nOr in terminal, log out and select X11 session at login.")
        print("="*60)
        return False
    
    print("✓ X11 detected - system requirements met")
    return True

def check_python_version():
    """Check Python version."""
    version = sys.version_info
    print(f"Python version: {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print(f"❌ Python 3.8+ required, found {version.major}.{version.minor}")
        return False
    
    print("✓ Python version OK")
    return True

def check_venv():
    """Check if virtual environment exists."""
    venv_path = os.path.join(os.path.dirname(__file__), 'venv')
    
    if os.path.exists(venv_path):
        print(f"✓ Virtual environment found at {venv_path}")
        
        # Check if activated
        if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            print("✓ Virtual environment is ACTIVATED")
            return True
        else:
            print("⚠ Virtual environment NOT activated")
            print("\n  Activate with:")
            print(f"  source {venv_path}/bin/activate")
            return False
    else:
        print(f"❌ Virtual environment not found")
        print("\n  Create with:")
        print(f"  python3 -m venv venv")
        print(f"  source venv/bin/activate")
        print(f"  pip install -r requirements.txt")
        return False

def check_dependencies():
    """Check if required packages are installed."""
    required = ['PyQt6', 'numpy', 'cv2', 'Xlib', 'PIL', 'skimage']
    
    missing = []
    for package in required:
        try:
            __import__(package)
            print(f"✓ {package}")
        except ImportError:
            print(f"❌ {package} - NOT FOUND")
            missing.append(package)
    
    if missing:
        print("\nInstall missing packages:")
        print("  pip install -r requirements.txt")
        return False
    
    return True

def main():
    print("="*60)
    print("SYSTEM REQUIREMENTS CHECK")
    print("="*60)
    print()
    
    all_ok = True
    
    print("1. Display Server")
    print("-" * 40)
    all_ok &= check_display_server()
    print()
    
    print("2. Python Version")
    print("-" * 40)
    all_ok &= check_python_version()
    print()
    
    print("3. Virtual Environment")
    print("-" * 40)
    all_ok &= check_venv()
    print()
    
    print("4. Dependencies")
    print("-" * 40)
    all_ok &= check_dependencies()
    print()
    
    print("="*60)
    if all_ok:
        print("✓ ALL CHECKS PASSED - Ready to run!")
        print("\nRun the overlay:")
        print("  python main.py")
        print("\nRun verification:")
        print("  python verify_v2.py --duration 6 --verbose")
        sys.exit(0)
    else:
        print("❌ SOME CHECKS FAILED - Fix issues above")
        sys.exit(1)

if __name__ == '__main__':
    main()
