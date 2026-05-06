from snip_core import SnipCore
from pynput import keyboard
import threading
import time
from PIL import ImageGrab
from tkinter import filedialog

def start_hotkeys(app):

    def on_activate():
        threading.Thread(target=delayed_capture, daemon=True).start()

    listener = keyboard.GlobalHotKeys({
        '<ctrl>+<space>+s': on_activate
    })

    listener.start()

def delayed_capture():

    time.sleep(1)

    app.root.after(0, do_capture)


def do_capture():
    # hide your app
    # app.root.withdraw()
    # app.root.update()

    from PIL import ImageGrab
    img = ImageGrab.grab()

    file_path = filedialog.asksaveasfilename(
        defaultextension=".png",
        filetypes=[
            ("PNG Image", "*.png"),
            ("JPG Image", "*.jpg"),
            ("All Files", "*.*")
        ]
    )

    if file_path:
        img.save(file_path)
        print("Saved to:", file_path)
    else:
        print("Save cancelled")


    # show app again
    app.root.deiconify()


if __name__ == "__main__":
    app = SnipCore()

    threading.Thread(
        target=start_hotkeys,
        args=(app,),
        daemon=True
    ).start()

    app.root.mainloop()

