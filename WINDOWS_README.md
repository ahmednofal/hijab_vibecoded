# Hijab by Copilot - Windows Installation Guide

This guide will help you set up and run Hijab by Copilot on Windows.

## Prerequisites

### 1. Install Python

1. Download Python 3.8 or higher from [python.org](https://www.python.org/downloads/)
2. **Important**: During installation, check the box that says **"Add Python to PATH"**
3. Complete the installation

To verify Python is installed correctly:
```cmd
python --version
```

You should see something like `Python 3.11.x` or higher.

## Quick Setup (Recommended)

### Method 1: Automatic Setup

1. **Double-click** `setup_windows.bat`
2. Wait for the installation to complete
3. Press any key when done

That's it! The script will:
- Create a virtual environment
- Install all dependencies
- Set everything up automatically

### Method 2: Manual Setup

If the automatic setup doesn't work, follow these steps:

```cmd
# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\activate

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

## Running the Application

### Quick Start

**Double-click** `run_windows.bat`

The application will:
1. Activate the virtual environment
2. Start the overlay window
3. Begin capturing and processing

### Manual Start

```cmd
# Activate virtual environment
venv\Scripts\activate

# Run the application
python main.py
```

## How to Use

1. Once started, you'll see a transparent overlay window covering your screen
2. The overlay is **click-through** - you can interact with applications underneath
3. Currently in test mode: A red rectangle moves across the screen
4. Press **Ctrl+C** in the terminal to exit

## Troubleshooting

### Python Not Found

**Error**: `'python' is not recognized as an internal or external command`

**Solution**: 
1. Reinstall Python and make sure to check "Add Python to PATH"
2. Or manually add Python to PATH:
   - Search for "Environment Variables" in Windows
   - Edit the "Path" variable
   - Add your Python installation directory (e.g., `C:\Python311\`)

### Virtual Environment Issues

**Error**: Cannot activate virtual environment

**Solution**:
1. Run PowerShell as Administrator
2. Execute: `Set-ExecutionPolicy RemoteSigned`
3. Try activating again

Or use Command Prompt instead of PowerShell.

### Overlay Not Visible

**Solutions**:
1. Check that Windows transparency effects are enabled:
   - Settings → Personalization → Colors → Transparency effects: **On**
2. Make sure your graphics drivers are up to date
3. Try running as Administrator (right-click → Run as administrator)

### Screen Capture Not Working

**Error**: MSS capture fails

**Solutions**:
1. Close other screen capture software
2. Check if antivirus is blocking screen capture
3. Add exception for Python in Windows Defender/antivirus
4. Update graphics drivers

### High CPU Usage

**Solutions**:
1. Close other applications
2. Reduce capture rate (modify `capture_delay` in capture_windows.py)
3. Use a single monitor

## Performance Tips

1. **Best Performance**:
   - Close unnecessary applications
   - Use primary monitor only
   - Ensure good GPU drivers

2. **Laptop Users**:
   - Plug in power adapter (for best performance)
   - Set power plan to "High Performance"

3. **Multiple Monitors**:
   - Currently uses primary monitor
   - To change, modify monitor index in code

## System Requirements

- **OS**: Windows 10 or Windows 11
- **Python**: 3.8 or higher
- **RAM**: 4GB minimum, 8GB recommended
- **CPU**: Multi-core processor recommended
- **GPU**: Any GPU with driver support for screen capture

## What Works on Windows

✅ Screen capture using MSS (very fast)
✅ Transparent overlay window
✅ Click-through overlay
✅ Multi-monitor support (primary monitor)
✅ Real-time processing

## Known Limitations

- Segmentation currently disabled (test mode only)
- Only primary monitor supported (can be extended)
- Requires relatively modern GPU drivers

## Next Steps

Once the basic overlay is working, you can:
1. Enable segmentation (uncomment in main.py)
2. Adjust colors/transparency
3. Add keyboard shortcuts
4. Customize detection sensitivity

## Getting Help

If you encounter issues:
1. Check this troubleshooting guide
2. Verify all prerequisites are met
3. Check the console output for error messages
4. Ensure Python and all packages are correctly installed

## Technical Details

### Architecture

```
main.py (Platform detection and orchestration)
    ├── capture_windows.py (MSS screen capture)
    ├── overlay_windows.py (PyQt6 transparent overlay)
    └── segmentation.py (MediaPipe person detection - optional)
```

### Key Features

- **MSS**: Ultra-fast screen capture (50-60 FPS)
- **PyQt6**: Cross-platform GUI framework
- **Multiprocessing**: Parallel capture and processing
- **Click-through**: Overlay doesn't interfere with mouse/keyboard

### Configuration

Edit these values in the code to customize:

- `capture_delay` in capture_windows.py: Control FPS
- `rect_width` in overlay_windows.py: Test rectangle size
- `monitor_index` in main.py: Change monitor

## Uninstalling

To remove the application:

1. Delete the project folder
2. That's it! No system changes were made

The virtual environment is self-contained within the project folder.
