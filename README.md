# Hijab by Copilot

Real-time person detection and overlay system using semantic segmentation.

## Supported Platforms

- **Linux** with X11 (Wayland has experimental support)
- **Windows** 10/11

## Requirements

### Linux
- X11 compositor running (Picom, Compton, or built-in KDE/GNOME compositor)
- Python 3.8+

### Windows
- Windows 10 or 11
- Python 3.8+

## Installation

```bash
# Create and activate virtual environment
python3 -m venv venv

# On Linux/Mac
source venv/bin/activate

# On Windows
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

Press F12 or Ctrl+C to exit.

## How it Works

1. **Screen Capture**
   - Linux: Uses XComposite (X11) or gnome-screenshot/grim (Wayland)
   - Windows: Uses MSS (ultra-fast screen capture library)
   
2. **Person Detection**
   - Detects people using MediaPipe semantic segmentation
   
3. **Overlay Rendering**
   - Renders red semi-transparent overlay on detected persons
   - Uses PyQt6 for transparent, click-through window overlay
   
4. **Multiprocessing**
   - Parallel capture/segmentation/rendering for smooth performance

## Platform-Specific Notes

### Windows
- Uses MSS for fast, efficient screen capture
- Overlay window uses Windows-native transparency
- No additional system requirements

### Linux (X11)
- Excludes overlay window from capture to prevent feedback loop
- Requires compositor for transparency effects
- Best performance on X11 (faster than Wayland)

### Linux (Wayland)
- Experimental support using gnome-screenshot or grim
- Pre-captures background to avoid feedback loop
- Slower performance due to screenshot tool overhead

## Troubleshooting

### Linux
If transparency doesn't work:
1. Ensure you're running a compositor (check with `ps aux | grep -E '(picom|compton|kwin|mutter)'`)
2. Try switching to X11 session (logout, select X11 at login screen)

### Windows
If the overlay is not visible:
1. Check that Windows transparency effects are enabled
2. Run as administrator if needed
3. Check antivirus isn't blocking screen capture
