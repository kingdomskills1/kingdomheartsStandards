import tkinter as tk
from tkinter import ttk, filedialog
import subprocess
import threading
import keyboard
import os
import re

# ==========================================
# GLOBALS
# ==========================================
recording_process = None

save_folder = ""

paused = False

segment_index = 0

segments = []

# ==========================================
# TIMER GLOBALS
# ==========================================
recording_seconds = 0
timer_running = False


# ==========================================
# GET AUDIO DEVICES
# ==========================================
def get_audio_devices():

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    result = subprocess.run(
        [
            "ffmpeg",
            "-list_devices",
            "true",
            "-f",
            "dshow",
            "-i",
            "dummy"
        ],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        startupinfo=startupinfo
    )

    output = result.stderr

    devices = []

    for line in output.splitlines():

        if "Alternative name" in line:
            continue

        match = re.search(r'"(.*?)"', line)

        if match:

            name = match.group(1)

            if (
                "DirectShow audio devices" not in name
                and
                "DirectShow video devices" not in name
            ):
                devices.append(name)

    return devices


# ==========================================
# CHOOSE SAVE FOLDER
# ==========================================
def choose_folder():

    global save_folder

    folder = filedialog.askdirectory()

    if folder:
        save_folder = folder
        folder_label.config(text=save_folder)


# ==========================================
# RECORD TIMER
# ==========================================
def update_timer():

    global recording_seconds
    global timer_running

    if timer_running:

        hrs = recording_seconds // 3600
        mins = (recording_seconds % 3600) // 60
        secs = recording_seconds % 60

        timer_label.config(
            text=f"⏱ {hrs:02}:{mins:02}:{secs:02}"
        )

        recording_seconds += 1

    root.after(1000, update_timer)


# ==========================================
# START RECORDING
# ==========================================
def start_recording():

    global recording_process
    global segment_index
    global segments
    global paused
    global timer_running

    if recording_process:
        return

    if not save_folder:
        status_label.config(text="❌ Choose folder first")
        return

    audio_device = audio_var.get()

    if not audio_device:
        status_label.config(text="❌ Select audio device")
        return

    filename = f"segment_{segment_index}.mp4"

    output_path = os.path.join(
        save_folder,
        filename
    )

    segments.append(output_path)

    command = [

        "ffmpeg",

        "-y",

        # ======================================
        # SCREEN
        # ======================================
        "-f", "gdigrab",

        "-draw_mouse", "1",

        "-framerate", "30",

        "-probesize", "10M",

        "-rtbufsize", "512M",

        "-i", "desktop",

        # ======================================
        # AUDIO
        # ======================================
        "-f", "dshow",

        "-audio_buffer_size", "50",

        "-i", f"audio={audio_device}",

        # ======================================
        # SYNC
        # ======================================
        "-use_wallclock_as_timestamps", "1",

        "-fflags", "+genpts",

        "-af", "aresample=async=1",

        # ======================================
        # VIDEO
        # ======================================
        "-c:v", "h264_nvenc",

        "-preset", "p5",

        "-cq", "28",

        "-pix_fmt", "yuv420p",

        # ======================================
        # AUDIO
        # ======================================
        "-c:a", "aac",

        "-b:a", "192k",

        output_path
    ]

    try:

        # ======================================
        # HIDE CMD WINDOW
        # ======================================
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        recording_process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP
                |
                subprocess.CREATE_NO_WINDOW
            ),
            startupinfo=startupinfo
        )

        paused = False

        # START TIMER
        timer_running = True

        status_label.config(
            text="🔴 Recording..."
        )

    except Exception as e:

        status_label.config(
            text=f"❌ Error: {e}"
        )


# ==========================================
# PAUSE / RESUME
# ==========================================
def toggle_pause():

    global recording_process
    global paused
    global segment_index
    global timer_running

    # ======================================
    # RESUME
    # ======================================
    if not recording_process:

        start_recording()

        return

    # ======================================
    # PAUSE
    # ======================================
    try:

        recording_process.communicate(
            input=b'q',
            timeout=3
        )

    except:

        try:
            recording_process.terminate()
        except:
            pass

    recording_process = None

    paused = True

    # PAUSE TIMER
    timer_running = False

    segment_index += 1

    status_label.config(
        text="⏸ Paused"
    )


# ==========================================
# STOP RECORDING
# ==========================================
def stop_recording():

    global recording_process
    global segments
    global segment_index
    global paused
    global timer_running
    global recording_seconds

    # ======================================
    # STOP CURRENT SEGMENT
    # ======================================
    if recording_process:

        try:

            recording_process.communicate(
                input=b'q',
                timeout=3
            )

        except:

            try:
                recording_process.terminate()
            except:
                pass

        recording_process = None

    # STOP TIMER
    timer_running = False

    # ======================================
    # NOTHING TO MERGE
    # ======================================
    if not segments:

        status_label.config(
            text="❌ No recordings found"
        )

        return

    # ======================================
    # CONCAT FILE
    # ======================================
    concat_file = os.path.join(
        save_folder,
        "concat.txt"
    )

    with open(concat_file, "w", encoding="utf-8") as f:

        for segment in segments:

            fixed = segment.replace("\\", "/")

            f.write(f"file '{fixed}'\n")

    # ======================================
    # FINAL OUTPUT
    # ======================================
    final_output = os.path.join(
        save_folder,
        "final_output.mp4"
    )

    # delete old final
    if os.path.exists(final_output):

        try:
            os.remove(final_output)
        except:
            pass

    # ======================================
    # MERGE
    # ======================================
    merge_command = [

        "ffmpeg",

        "-y",

        "-f", "concat",

        "-safe", "0",

        "-i", concat_file,

        "-c", "copy",

        final_output
    ]

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    subprocess.run(
        merge_command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
        startupinfo=startupinfo
    )

    # ======================================
    # CLEANUP
    # ======================================
    try:
        os.remove(concat_file)
    except:
        pass

    # ======================================
    # RESET
    # ======================================
    segments = []

    segment_index = 0

    paused = False

    recording_seconds = 0

    timer_label.config(
        text="⏱ 00:00:00"
    )

    status_label.config(
        text="✅ Final Video Saved"
    )


# ==========================================
# HOTKEYS
# ==========================================
keyboard.add_hotkey(
    "ctrl+alt+s",
    lambda: threading.Thread(
        target=start_recording
    ).start()
)

keyboard.add_hotkey(
    "ctrl+alt+p",
    toggle_pause
)

keyboard.add_hotkey(
    "ctrl+alt+x",
    stop_recording
)

# ==========================================
# UI
# ==========================================
root = tk.Tk()

root.title("PRO Screen Recorder")

root.geometry("600x400")

frame = ttk.Frame(
    root,
    padding=20
)

frame.pack(fill="both", expand=True)

# ==========================================
# AUDIO DEVICES
# ==========================================
ttk.Label(
    frame,
    text="Audio Device:"
).grid(
    row=0,
    column=0,
    sticky="w"
)

audio_devices = get_audio_devices()

audio_var = tk.StringVar()

if audio_devices:
    audio_var.set(audio_devices[0])

audio_box = ttk.Combobox(
    frame,
    textvariable=audio_var,
    values=audio_devices,
    width=50
)

audio_box.grid(
    row=0,
    column=1,
    pady=10
)

# ==========================================
# SAVE FOLDER
# ==========================================
ttk.Button(
    frame,
    text="Choose Folder",
    command=choose_folder
).grid(
    row=1,
    column=0,
    pady=10
)

folder_label = ttk.Label(
    frame,
    text="No folder selected"
)

folder_label.grid(
    row=1,
    column=1
)

# ==========================================
# START BUTTON
# ==========================================
start_btn = ttk.Button(
    frame,
    text="Start Recording",
    command=lambda: threading.Thread(
        target=start_recording
    ).start()
)

start_btn.grid(
    row=2,
    column=0,
    pady=20
)

# ==========================================
# PAUSE BUTTON
# ==========================================
pause_btn = ttk.Button(
    frame,
    text="Pause / Resume",
    command=toggle_pause
)

pause_btn.grid(
    row=2,
    column=1
)

# ==========================================
# STOP BUTTON
# ==========================================
stop_btn = ttk.Button(
    frame,
    text="Stop Recording",
    command=stop_recording
)

stop_btn.grid(
    row=2,
    column=2
)

# ==========================================
# STATUS
# ==========================================
status_label = ttk.Label(
    frame,
    text="Idle"
)

status_label.grid(
    row=3,
    column=0,
    columnspan=3,
    pady=20
)

# ==========================================
# TIMER LABEL
# ==========================================
timer_label = ttk.Label(
    frame,
    text="⏱ 00:00:00",
    font=("Arial", 16, "bold")
)

timer_label.grid(
    row=4,
    column=0,
    columnspan=3,
    pady=10
)

# ==========================================
# HOTKEYS INFO
# ==========================================
hotkeys_label = ttk.Label(
    frame,
    text=(
        "HOTKEYS\n"
        "CTRL + ALT + S = Start\n"
        "CTRL + ALT + P = Pause / Resume\n"
        "CTRL + ALT + X = Stop"
    )
)

hotkeys_label.grid(
    row=5,
    column=0,
    columnspan=3
)

# ==========================================
# START TIMER LOOP
# ==========================================
update_timer()

# ==========================================
# MAIN LOOP
# ==========================================
root.mainloop()