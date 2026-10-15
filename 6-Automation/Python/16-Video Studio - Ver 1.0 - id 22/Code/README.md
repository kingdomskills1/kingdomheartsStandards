# Python Video Player

A Windows desktop video player built with PySide6 and VLC/libVLC.

## Setup

1. Install the 64-bit VLC desktop application: https://www.videolan.org/vlc/
2. Install FFmpeg and make sure `ffmpeg` and `ffprobe` are available on PATH to trim or join media.
3. Make sure Python is installed and the `py` command works.
4. Double-click `install.bat`.
5. Double-click `start.bat`.

Keep `Video Studio Icon.ico` next to `main.py` when running from source, or next to `Video Studio.exe` when running the packaged application.

## Controls

- Open: choose a video or audio file.
- Recent videos: find the last 10 opened files under **File → Recent videos**. The list is saved between runs; use **Clear recent videos** to empty it.
- Playlist: open the separate Playlist window with the **Playlist** button or **Ctrl+L**. Close that window to hide it; use the button or shortcut to reopen it without losing the list. Add media, double-click an item to play it, use **Previous Track** / **Next Track** to navigate, and choose **Save Playlist** or **Load Playlist** to reuse `.m3u8`/`.m3u` playlists. Playback advances automatically to the next item.
- Trim: open the separate trim window with **Trim** or **Ctrl+T**. It shows the current video and a timeline with green start, red end, and white playback-position markers. Click or drag the timeline to seek the video, and use the **Play** / **Pause** button to control playback. Prominent start, end, and selected-duration readouts show precise milliseconds and update when markers are set or changed. Close it to hide the controls; reopen it later without losing the current trim markers or export progress.
- Join Videos: select at least two videos to combine them into one file. The app normalizes size and frame rate, supports MP4, MKV, MOV, WebM, or AVI output, and shows export progress.
- To trim: play or seek to the desired start and click **Set Trim Start**; move to the desired end and click **Set Trim End**, then click **Save Trimmed As...** and choose MP4, MKV, MOV, WebM, AVI, or GIF. A progress bar shows the export percentage.
- Space: play/pause.
- Click or drag the seek bar to change playback position.
- Zoom from 100% to 300% with the Zoom slider or mouse wheel over the video (wheel zoom stays centered on the pointer); left- or right-drag the zoomed video to pan. Click **Reset View** to restore it. Zoom and pan work while playing or paused.
- `]` / `[`: zoom in/out; `R`: reset zoom and position. `W` / `A` / `S` / `D`: pan up/left/down/right when zoomed. Stop playback with **Ctrl+S**.
- S: stop.
- Left / Right: seek 10 seconds backward/forward.
- Ctrl + Left / Right: seek 60 seconds backward/forward.
- M: mute/unmute.
- F: toggle full screen.
- Double-click the video area or window: toggle full screen.
- Escape: exit full screen.
- Ctrl + O: open a file.
- Ctrl + Q: exit.
- When Windows launches the player for a media file, that file opens in a new player window titled with its filename. Opening another media file starts another window.

## Build and default app

From this folder, build the one-file Windows executable with:

```powershell
pyinstaller --onefile --windowed --icon="Video Studio Icon.ico" --add-data="Video Studio Icon.ico;." main.py
```

The executable is created at `dist\main.exe`. In Windows, choose it as the default app for each desired video and audio extension from **Settings → Apps → Default apps → Choose defaults by file type**. Windows will start a separate player window for each file opened with the app.

## Supported formats

The actual supported formats depend on the installed VLC version and codecs. Common video formats include MP4, MKV, AVI, MOV, WMV, FLV, WebM, MPEG, M4V, 3GP, TS, MTS, M2TS and OGV. Common audio formats include MP3, WAV, FLAC, AAC, M4A, OGG, Opus, WMA, AIFF, APE and MIDI. Use “All files” in the file picker to try other formats.

No player can guarantee every possible file: damaged files, unsupported codecs, DRM-protected videos, or unusual streams may not play.

## Notes

- `python-vlc` is a Python interface; the VLC desktop application provides the playback engine.
- Trimming requires FFmpeg on PATH. Joining requires FFmpeg and ffprobe on PATH. Exports are re-encoded; GIF trim exports contain video only. Joining preserves audio when present and adds silence to clips without audio.
- Install the 64-bit VLC application if using 64-bit Python.
