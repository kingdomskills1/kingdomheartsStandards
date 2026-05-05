import cv2
import numpy as np
from mss import mss
import sounddevice as sd
from scipy.io.wavfile import write
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip
import threading
import tkinter as tk
from tkinter import ttk, filedialog
import time
import keyboard
import os

# =============================
# GLOBAL STATE
# =============================
recording = False
paused = False

pause_event = threading.Event()
pause_event.set()

save_folder = ""
save_format = "mp4"

progress_window = None
progress_var = None
progress_label = None
progress_running = False


# =============================
# DEVICES
# =============================
def list_input_devices():
    devices = sd.query_devices()
    return [(i, d['name']) for i, d in enumerate(devices) if d['max_input_channels'] > 0]


def get_device(var):
    val = var.get()
    if not val:
        return None
    return int(val.split(":")[0])


# =============================
# CHOOSE FOLDER
# =============================
def choose_folder():
    global save_folder
    save_folder = filedialog.askdirectory()
    folder_label.config(text=save_folder if save_folder else "No folder selected")


# =============================
# AUDIO
# =============================
def record_audio(filename, device, samplerate=44100):
    global recording

    audio_data = []

    def callback(indata, frames, time_info, status):
        if recording and pause_event.is_set():
            audio_data.append(indata.copy())

    try:
        with sd.InputStream(device=device, samplerate=samplerate, channels=2, callback=callback):
            while recording:
                sd.sleep(50)
    except:
        return

    if audio_data:
        audio_data = np.concatenate(audio_data, axis=0)
        write(filename, samplerate, audio_data)


# =============================
# SCREEN
# =============================
def record_screen(filename, fps):
    global recording

    fps = min(int(fps), 30)

    with mss() as sct:
        monitor = sct.monitors[1]
        width = monitor["width"]
        height = monitor["height"]

        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        out = cv2.VideoWriter(filename, fourcc, fps, (width, height))

        frame_interval = 1.0 / fps
        next_time = time.perf_counter()

        while recording:
            if not pause_event.is_set():
                time.sleep(0.1)
                next_time = time.perf_counter()
                continue

            img = sct.grab(monitor)
            frame = np.array(img)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            out.write(frame)

            next_time += frame_interval
            sleep = next_time - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)

        out.release()


# =============================
# START
# =============================
def start_recording():
    global recording

    if recording:
        return

    if not save_folder:
        status_label.config(text="❌ Choose folder first")
        return

    recording = True
    pause_event.set()

    fps = int(fps_var.get())

    base_video = os.path.join(save_folder, f"screen.avi")
    audio1_file = os.path.join(save_folder, "audio1.wav")
    audio2_file = os.path.join(save_folder, "audio2.wav")

    dev1 = get_device(dev1_var)
    dev2 = get_device(dev2_var)

    threading.Thread(target=record_screen, args=(base_video, fps), daemon=True).start()

    if dev1 is not None:
        threading.Thread(target=record_audio, args=(audio1_file, dev1), daemon=True).start()

    if dev2 is not None:
        threading.Thread(target=record_audio, args=(audio2_file, dev2), daemon=True).start()

    status_label.config(text="Recording...")


# =============================
# STOP
# =============================
def stop_recording():
    global recording, progress_running

    if not recording:
        return

    recording = False
    pause_event.set()

    status_label.config(text="Processing...")

    fps = int(fps_var.get())

    video_path = os.path.join(save_folder, "screen.avi")
    output_path = os.path.join(save_folder, f"output.{save_format}")

    video = VideoFileClip(video_path)

    audio_clips = []

    try:
        audio_clips.append(AudioFileClip(os.path.join(save_folder, "audio1.wav")))
    except:
        pass

    try:
        audio_clips.append(AudioFileClip(os.path.join(save_folder, "audio2.wav")))
    except:
        pass

    if len(audio_clips) == 1:
        final_audio = audio_clips[0]
    elif len(audio_clips) > 1:
        final_audio = CompositeAudioClip(audio_clips)
    else:
        final_audio = None

    show_loading_window()

    progress_running = True
    threading.Thread(target=smooth_progress, daemon=True).start()

    if final_audio:
        duration = video.duration
        final_audio = final_audio.subclip(0, min(final_audio.duration, duration))
        video = video.subclip(0, final_audio.duration)
        final = video.set_audio(final_audio)
    else:
        final = video

    final.write_videofile(
        output_path,
        fps=fps,
        logger=None,
        verbose=False,
        threads=4,
        codec="libx264",
        audio_codec="aac"
    )

    progress_running = False
    set_progress(100, "100%")

    time.sleep(0.3)

    if progress_window:
        progress_window.destroy()

    status_label.config(text=f"Saved ✔ ({save_format})")


# =============================
# FORMAT CHANGE
# =============================
def change_format(event):
    global save_format
    save_format = format_var.get()


# =============================
# PAUSE
# =============================
def toggle_pause():
    global paused

    if not recording:
        return

    paused = not paused

    if paused:
        pause_event.clear()
        status_label.config(text="Paused ⏸")
    else:
        pause_event.set()
        status_label.config(text="Recording ▶")


# =============================
# PROGRESS UI
# =============================
def show_loading_window():
    global progress_window, progress_var, progress_label

    progress_window = tk.Toplevel(root)
    progress_window.title("Processing")
    progress_window.geometry("300x120")

    ttk.Label(progress_window, text="Processing video...").pack(pady=10)

    progress_var = tk.DoubleVar()
    ttk.Progressbar(progress_window, variable=progress_var, maximum=100).pack(fill="x", padx=20, pady=10)

    progress_label = ttk.Label(progress_window, text="0%")
    progress_label.pack()


def set_progress(value, text):
    def update():
        progress_var.set(value)
        progress_label.config(text=text)
        progress_window.update()

    root.after(0, update)


def smooth_progress():
    percent = 0

    while progress_running and percent < 99:
        percent += 0.7
        set_progress(percent, f"{int(percent)}%")
        time.sleep(0.05)


# =============================
# HOTKEYS
# =============================
keyboard.add_hotkey("ctrl+alt+s", lambda: start_recording())
keyboard.add_hotkey("ctrl+alt+p", lambda: toggle_pause())
keyboard.add_hotkey("ctrl+alt+x", lambda: stop_recording())


# =============================
# UI
# =============================
root = tk.Tk()
root.title("Recorder PRO + Save Options")

frame = ttk.Frame(root, padding=20)
frame.grid()

# FPS
ttk.Label(frame, text="FPS:").grid(row=0, column=0)
fps_var = tk.StringVar(value="30")
ttk.Combobox(frame, textvariable=fps_var, values=("10", "15", "30", "60")).grid(row=0, column=1)

# Devices
devices = list_input_devices()
device_names = [f"{i}: {name}" for i, name in devices]

ttk.Label(frame, text="Audio 1:").grid(row=1, column=0)
dev1_var = tk.StringVar()
ttk.Combobox(frame, textvariable=dev1_var, values=device_names).grid(row=1, column=1)

ttk.Label(frame, text="Audio 2:").grid(row=2, column=0)
dev2_var = tk.StringVar()
ttk.Combobox(frame, textvariable=dev2_var, values=[""] + device_names).grid(row=2, column=1)

# Folder
ttk.Button(frame, text="Choose Folder", command=choose_folder).grid(row=3, column=0)
folder_label = ttk.Label(frame, text="No folder selected")
folder_label.grid(row=3, column=1)

# Format
format_var = tk.StringVar(value="mp4")
format_box = ttk.Combobox(frame, textvariable=format_var, values=("mp4", "avi", "mkv"))
format_box.grid(row=4, column=1)
format_box.bind("<<ComboboxSelected>>", change_format)
ttk.Label(frame, text="Format:").grid(row=4, column=0)

# Buttons
ttk.Button(frame, text="Start", command=start_recording).grid(row=5, column=0)
ttk.Button(frame, text="Pause", command=toggle_pause).grid(row=5, column=1)
ttk.Button(frame, text="Stop", command=stop_recording).grid(row=6, column=0, columnspan=2)

status_label = ttk.Label(frame, text="Idle")
status_label.grid(row=7, column=0, columnspan=2)

root.mainloop()