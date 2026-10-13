Screen Capture Tool

Overview
----------
This project is a Windows desktop screen capture and annotation utility. It lets you capture the full screen, select an area, and edit or annotate the captured image using a Tkinter canvas.

Files
-----
- screen_capture.py
  Main application entry point.
- snip_core.py
  Core screen capture, selection, drawing, and editing logic.
- edit_nodes.py
  Handles node-based editing and UI interactions for selected items.

Requirements
------------
Install the following Python packages before running the app:
- keyboard
- pillow
- tkinter (included with most Python Windows installs)

Example installation:
  pip install keyboard pillow

Run
---
From this folder, start the application with:
  python screen_capture.py

Controls
--------
- Ctrl + Space: capture the screen
- 1: switch to snip mode
- 2: switch to draw mode
- 3: switch to edit mode
- Ctrl + D: toggle draw mode
- Esc: reset selection/state
- Enter: save selection
- Ctrl + E: toggle edit mode

Notes
-----
This tool is designed for Windows, since it uses PIL ImageGrab and Windows-specific behavior such as DPI awareness.
