import tkinter as tk
from tkinter import filedialog
from threading import Thread
import time
import mss
from PIL import Image
from pynput import keyboard

class GifRecorder:
    def __init__(self, root):
        self.root = root
        self.root.title("GIF Recorder")

        self.recording = False
        self.paused = False
        self.frames = []

        self.start_time = 0
        self.elapsed_time = 0

        # UI
        tk.Button(root, text="Start (Ctrl+Alt+S)", command=self.start_recording, width=30).pack(pady=5)
        tk.Button(root, text="Pause (Ctrl+Alt+P)", command=self.pause_resume, width=30).pack(pady=5)
        tk.Button(root, text="Stop (Ctrl+Alt+T)", command=self.stop_recording, width=30).pack(pady=5)

        self.status = tk.Label(root, text="Status: Idle")
        self.status.pack()

        self.timer_label = tk.Label(root, text="Time: 0s")
        self.timer_label.pack()

        self.update_timer()

        # ✅ PROPER GLOBAL HOTKEYS
        self.hotkeys = keyboard.GlobalHotKeys({
            '<ctrl>+<alt>+s': self.start_recording,
            '<ctrl>+<alt>+p': self.pause_resume,
            '<ctrl>+<alt>+t': self.stop_recording,
        })
        self.hotkeys.start()

    # ⏱ Timer
    def update_timer(self):
        if self.recording and not self.paused:
            self.elapsed_time = time.time() - self.start_time
            self.timer_label.config(text=f"Time: {int(self.elapsed_time)}s")

        self.root.after(500, self.update_timer)

    # 🎥 Screen capture
    def record_screen(self):
        with mss.MSS() as sct:
            monitor = sct.monitors[1]

            while self.recording:
                if not self.paused:
                    img = sct.grab(monitor)
                    frame = Image.frombytes("RGB", img.size, img.rgb)
                    self.frames.append(frame)

                time.sleep(0.1)

    # ▶ Start
    def start_recording(self):
        if self.recording:
            return

        self.frames = []
        self.recording = True
        self.paused = False
        self.start_time = time.time()

        self.status.config(text="Recording...")
        self.root.withdraw()

        Thread(target=self.record_screen, daemon=True).start()

    # ⏸ Pause/Resume
    def pause_resume(self):
        if not self.recording:
            return

        self.paused = not self.paused
        self.status.config(text="Paused" if self.paused else "Recording")

    # ⏹ Stop + Save
    def stop_recording(self):
        if not self.recording:
            return

        self.recording = False
        self.root.deiconify()

        self.status.config(text="Saving GIF...")

        file_path = filedialog.asksaveasfilename(
            defaultextension=".gif",
            filetypes=[("GIF files", "*.gif")],
            title="Save GIF"
        )

        if file_path and self.frames:
            self.frames[0].save(
                file_path,
                save_all=True,
                append_images=self.frames[1:],
                duration=100,
                loop=0
            )
            self.status.config(text="Saved successfully")
        else:
            self.status.config(text="Cancelled")


# Run app
root = tk.Tk()
app = GifRecorder(root)
root.mainloop()