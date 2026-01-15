# Hijab by Copilot

Real-time person detection and overlay system using semantic segmentation.

## Requirements

- Linux with X11
- X11 compositor running (Picom, Compton, or built-in KDE/GNOME compositor)
- Python 3.8+

## Installation

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Linux/Mac
# or
# venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

Press F12 to exit.

## How it Works

1. Captures screen content using XComposite (excluding overlay window)
2. Detects people using MediaPipe semantic segmentation
3. Renders red semi-transparent overlay on detected persons
4. Uses multiprocessing for parallel capture/segmentation/rendering
