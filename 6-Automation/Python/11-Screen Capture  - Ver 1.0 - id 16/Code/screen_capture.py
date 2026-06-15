import keyboard
from snip_core import SnipCore

app = SnipCore()

keyboard.add_hotkey("ctrl+space", app.capture_screen)

app.root.mainloop()