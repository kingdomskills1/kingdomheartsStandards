PRO Screen Recorder

A simple Windows screen recorder built with Python, Tkinter, FFmpeg, and the keyboard package.
It captures the desktop and selected audio device, supports pause/resume, and merges recorded segments into a single final video file.

Features
- Record desktop screen and microphone/system audio
- Choose output folder
- Start, pause/resume, and stop recording from the app or hotkeys
- Live timer display while recording
- Automatically combines segments into final_output.mp4

Requirements
- Windows 10/11
- Python 3.9+
- FFmpeg installed and available in PATH
- NVIDIA GPU with NVENC support for the default H.264 encoder used in this app
- Python package: keyboard

Install dependencies
1. Install Python from python.org if needed.
2. Open a terminal in this folder.
3. Run:
   pip install keyboard
4. Install FFmpeg and make sure the ffmpeg executable is available in PATH.

Run the recorder
1. Open a terminal in this folder.
2. Run:
   python video_recorder.py
3. Select an audio device from the dropdown.
4. Click "Choose Folder" and select where the video should be saved.
5. Click "Start Recording" or use Ctrl + Alt + S.

Controls
- Ctrl + Alt + S = Start recording
- Ctrl + Alt + P = Pause / Resume
- Ctrl + Alt + X = Stop recording

Output files
- Each recording segment is saved as segment_0.mp4, segment_1.mp4, etc.
- When you stop recording, the app merges all segments into:
  final_output.mp4

Notes
- This app uses Windows DirectShow and desktop capture, so it is designed for Windows only.
- If your system does not support the default NVENC encoder, you may need to change the FFmpeg video codec in video_recorder.py.
- The app saves output in the folder you selected when starting the recording session.

Troubleshooting
- If the app says "Choose folder first", select a save folder before recording.
- If it says "Select audio device", choose a valid microphone or audio capture source.
- If FFmpeg commands fail, confirm that ffmpeg is installed and added to PATH.
