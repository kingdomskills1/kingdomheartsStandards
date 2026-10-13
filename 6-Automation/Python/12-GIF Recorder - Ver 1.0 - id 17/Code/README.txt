GIF Recorder

This project records your screen and saves the output as a GIF file.

Features:
- Records screen activity with mouse cursor included
- Start, pause, and stop recording controls
- Global keyboard shortcuts for quick recording
- Saves captured footage as a .gif file

Requirements:
- Python 3
- tkinter
- mss
- Pillow (PIL)
- pynput

Install dependencies:
  pip install mss Pillow pynput

Run the app:
  python gif_recorder.py

Keyboard shortcuts:
- Ctrl + Alt + S = Start recording
- Ctrl + Alt + P = Pause / resume recording
- Ctrl + Alt + T = Stop recording and save as GIF

Notes:
- The app hides the main window while recording.
- After stopping, you will be prompted to choose a save location.
- The GIF is saved using a 100 ms frame delay and loops continuously.
