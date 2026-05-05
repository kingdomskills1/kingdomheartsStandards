import tkinter as tk
from tkinter import filedialog
from PIL import ImageGrab
import ctypes
from edit_nodes import NodeEditor

try:
    ctypes.windll.user32.SetProcessDPIAware()
except:
    pass


class SnipCore:
    def __init__(self):
        self.root = tk.Tk()

        self.root.attributes("-fullscreen", True)
        self.root.attributes("-alpha", 0.25)
        self.root.configure(bg="black")

        self.canvas = tk.Canvas(self.root, cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # ---------------- RECT ----------------
        self.start_x = self.start_y = 0
        self.end_x = self.end_y = 0
        self.rect = None

        # ---------------- NODES ----------------
        self.handles = []
        self.selected_node = None

        # ---------------- MODES ----------------
        self.blur_mode = False

        # ---------------- EDIT SYSTEM ----------------
        self.editor = NodeEditor(self)


        # ================= DRAW SYSTEM STATE =================
        self.draw_mode = False
        self.draw_objects = []
        self.undo_stack = []
        self.redo_stack = []
        self.current_tool = "pen"
        self.color = "red"
        self.size = 3
        self.start_point = None
        self.canvas_draw = None
        self.draw_win = None
        self.image = None
        self.draw_history = []   # full actions
        self.history_index = -1
        self.undo_stack
        self.redo_stack 
        self.input_lock = False
        self.active_mode = "snip"  # snip | draw
        self.preview_item = None

        # ---------------- EVENTS ----------------
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        self.root.bind("<Return>", self.capture)
        self.root.bind("<Control-b>", self.toggle_blur)
        self.root.bind("<Control-d>", self.toggle_draw_mode)
        self.root.bind("<Control-z>", self.undo_draw)
        self.root.bind("<Control-y>", self.redo_draw)

        self.root.bind("<Up>", self.global_move)
        self.root.bind("<Down>", self.global_move)
        self.root.bind("<Left>", self.global_move)
        self.root.bind("<Right>", self.global_move)

        self.root.bind("w", self.global_move)
        self.root.bind("a", self.global_move)
        self.root.bind("s", self.global_move)
        self.root.bind("d", self.global_move)


        self.root.mainloop()

    # =========================================================
    # BLUR MODE
    # =========================================================
    def toggle_blur(self, event=None):
        self.blur_mode = not self.blur_mode
        print("Blur mode:", self.blur_mode)
        self.update_rect()

    # =========================================================
    # MOUSE DOWN
    # =========================================================
    def on_press(self, event):
        
        if self.active_mode == "draw":
            return  # ❌ stop snip selection completely

        x, y = self.pos()

        # ---------------- CHECK NODE FIRST (HIGHEST PRIORITY) ----------------
        node = self.get_handle(x, y)

        if node:
            if self.editor.enabled:
                self.selected_node = node
                self.editor.select_node(node)

                # force visual update (yellow highlight)
                self.draw_handles()

            # ❗ IMPORTANT: STOP HERE (prevents new screenshot start)
            return

        # ---------------- ONLY IF NOT NODE → START NEW SNIP ----------------
        self.clear_handles()
        self.selected_node = None
        self.editor.selected_node = None

        self.start_x = self.end_x = x
        self.start_y = self.end_y = y

        if self.rect:
            self.canvas.delete(self.rect)

        self.rect = self.canvas.create_rectangle(
            x, y, x, y,
            outline="red",
            width=2
        )

    # =========================================================
    # DRAG
    # =========================================================
    def on_drag(self, event):

        if self.active_mode == "draw":
            return
        
        x, y = self.pos()

        if self.editor.enabled and self.selected_node:
            return

        self.end_x = x
        self.end_y = y

        self.update_rect()

    # =========================================================
    # RELEASE
    # =========================================================
    def on_release(self, event):

        if self.active_mode == "draw":
            return
        
        self.draw_handles()

    # =========================================================
    # RECT UPDATE
    # =========================================================
    def update_rect(self):
        if not self.rect:
            return

        x1, y1, x2, y2 = self.get_coords()

        self.canvas.coords(self.rect, x1, y1, x2, y2)

        self.draw_overlay()
        self.draw_handles()

    # =========================================================
    # OVERLAY (BLUR VISUAL)
    # =========================================================
    def draw_overlay(self):
        if not self.blur_mode or not self.rect:
            return

        self.canvas.create_rectangle(
            0, 0,
            self.canvas.winfo_width(),
            self.canvas.winfo_height(),
            fill="black",
            stipple="gray25",
            outline=""
        )

        x1, y1, x2, y2 = self.get_coords()

        self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline="yellow",
            width=2
        )



    # =========================================================
    # CLEAR HANDLES
    # =========================================================
    def clear_handles(self):
        for h, _ in self.handles:
            self.canvas.delete(h)
        self.handles.clear()

    # =========================================================
    # HANDLE DETECTION
    # =========================================================
    def get_handle(self, x, y):
        for h, name in self.handles:
            x1, y1, x2, y2 = self.canvas.coords(h)
            if x1 <= x <= x2 and y1 <= y <= y2:
                return name
        return None

    # =========================================================
    # CAPTURE
    # =========================================================
    def capture(self, event=None):
        x1, y1, x2, y2 = self.get_coords()

        if x1 == x2 or y1 == y2:
            print("Invalid selection area")
            return

        # 1) hide EVERYTHING (including blur overlay)
        self.root.withdraw()
        self.root.update()

        # 2) take screenshot
        img = ImageGrab.grab(bbox=(x1, y1, x2, y2))

        # 3) show UI again
        self.root.deiconify()
        self.root.update()

        self.image = img

        file_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png")]
        )

        if not file_path:
            return

        img.save(file_path)
        print("Saved:", file_path)

    # =========================================================
    # HELPERS
    # =========================================================
    def get_coords(self):
        return (
            min(self.start_x, self.end_x),
            min(self.start_y, self.end_y),
            max(self.start_x, self.end_x),
            max(self.start_y, self.end_y),
        )

    def pos(self):
        return (
            self.canvas.winfo_pointerx() - self.canvas.winfo_rootx(),
            self.canvas.winfo_pointery() - self.canvas.winfo_rooty(),
        )
    
    def toggle_draw_mode(self, event=None):
        if getattr(self, "image", None) is None:
            print("No screenshot captured yet")
            return

        self.draw_mode = not self.draw_mode

        if self.draw_mode:
            self.active_mode = "draw"
            self.open_draw_window()
        else:
            self.active_mode = "snip"

    def open_draw_window(self):
        import tkinter as tk
        from PIL import ImageTk

        img = getattr(self, "image", None)
        if img is None:
            print("No image available")
            return

        self.draw_win = tk.Toplevel(self.root)
        self.draw_win.title("Draw Mode")

        w, h = img.size

        # ================= TOOLBAR =================
        bar = tk.Frame(self.draw_win)
        bar.pack(side="top", fill="x")

        tk.Button(bar, text="Pen", command=lambda: self.set_tool("pen")).pack(side="left")
        tk.Button(bar, text="Text", command=lambda: self.set_tool("text")).pack(side="left")
        tk.Button(bar, text="Arrow", command=lambda: self.set_tool("arrow")).pack(side="left")
        tk.Button(bar, text="Rect", command=lambda: self.set_tool("rect")).pack(side="left")

        tk.Button(bar, text="Undo", command=self.undo_draw).pack(side="left")
        tk.Button(bar, text="Redo", command=self.redo_draw).pack(side="left")
        tk.Button(bar, text="Color", command=self.pick_color).pack(side="left")
        tk.Button(bar, text="Save", command=self.save_dialog).pack(side="left")

        # ================= CANVAS =================
        self.canvas_draw = tk.Canvas(self.draw_win, width=w, height=h, bg="white")
        self.canvas_draw.pack()

        self.tk_img = ImageTk.PhotoImage(img)
        self.canvas_draw.create_image(0, 0, anchor="nw", image=self.tk_img)

        # ================= EVENTS =================
        self.canvas_draw.bind("<Button-1>", self.draw_start)
        self.canvas_draw.bind("<B1-Motion>", self.draw_move)
        self.canvas_draw.bind("<ButtonRelease-1>", self.draw_end)

        # =========================================================
        # ✅ STEP 2 — BIND KEYS ON BOTH WINDOW + CANVAS (IMPORTANT FIX)
        # =========================================================

        self.draw_win.bind("<KeyPress>", self.key_move)
        self.canvas_draw.bind("<KeyPress>", self.key_move)

        # force delete/backspace also directly
        self.draw_win.bind("<Delete>", self.key_move)
        self.draw_win.bind("<BackSpace>", self.key_move)
        self.canvas_draw.bind("<Delete>", self.key_move)
        self.canvas_draw.bind("<BackSpace>", self.key_move)

        # ================= FORCE FOCUS =================
        self.draw_win.lift()
        self.draw_win.focus_force()
        self.canvas_draw.focus_set()

    def set_tool(self, tool):
        self.current_tool = tool

        if self.canvas_draw:
            if tool == "pen":
                self.canvas_draw.config(cursor="pencil")
            else:
                self.canvas_draw.config(cursor="cross")

    def pick_color(self):
        from tkinter import colorchooser

        # prevent any interaction with snip canvas
        self.active_mode = "dialog"

        # open color picker
        color = colorchooser.askcolor(title="Pick Color")[1]

        # restore draw mode safely
        self.active_mode = "draw"

        if color:
            self.color = color
            print("Selected color:", color)

    def draw_start(self, event):
        x, y = event.x, event.y

        self.last_point = (x, y)  # ✅ start pen tracking

        obj = self.get_object_at(x, y)

        if obj:
            self.selected_object = obj
            self.drag_offset = (x, y)
            return

        self.selected_object = None
        self.start_point = (x, y)

        if self.current_tool == "text":
            from tkinter import simpledialog
            t = simpledialog.askstring("Text", "Enter text")

            if t:
                obj = ("text", self.start_point, t, self.color, self.size)
                self.add_object(obj)
                self.render()

    def draw_move(self, event):
        x, y = event.x, event.y

        # ================= MOVE SELECTED OBJECT =================
        if getattr(self, "selected_object", None):

            dx = x - self.drag_offset[0]
            dy = y - self.drag_offset[1]

            obj = self.selected_object
            t = obj[0]

            if t in ("arrow", "rect", "line"):
                a = obj[1]
                b = obj[2]

                new_obj = (
                    t,
                    (a[0] + dx, a[1] + dy),
                    (b[0] + dx, b[1] + dy),
                    obj[3],
                    obj[4]
                )

            elif t == "text":
                p = obj[1]

                new_obj = (
                    "text",
                    (p[0] + dx, p[1] + dy),
                    obj[2],
                    obj[3],
                    obj[4]
                )

            else:
                return

            # 🔥 replace safely
            idx = self.draw_objects.index(obj)
            self.draw_objects[idx] = new_obj
            self.selected_object = new_obj

            self.drag_offset = (x, y)
            self.render()
            return

        # ================= REALTIME PEN DRAW =================
        if self.current_tool == "pen":
            if not hasattr(self, "last_point") or self.last_point is None:
                self.last_point = (x, y)
                return

            x1, y1 = self.last_point
            x2, y2 = x, y

            obj = ("line", (x1, y1), (x2, y2), self.color, self.size)
            self.add_object(obj)

            self.last_point = (x, y)

            self.render()
            return

        # ================= SHAPE PREVIEW (RECT / ARROW) =================
        if not self.start_point:
            return

        x1, y1 = self.start_point
        x2, y2 = x, y

        if self.preview_item:
            self.canvas_draw.delete(self.preview_item)

        if self.current_tool == "rect":
            self.preview_item = self.canvas_draw.create_rectangle(
                x1, y1, x2, y2,
                outline=self.color,
                width=self.size,
                dash=(4, 2)
            )

        elif self.current_tool == "arrow":
            self.preview_item = self.canvas_draw.create_line(
                x1, y1, x2, y2,
                fill=self.color,
                width=self.size,
                arrow=tk.LAST,
                dash=(4, 2)
            )

    def draw_end(self, event):
        self.last_point = None  # ✅ stop pen

        if not self.start_point:
            return

        x1, y1 = self.start_point
        x2, y2 = event.x, event.y

        if self.preview_item:
            self.canvas_draw.delete(self.preview_item)
            self.preview_item = None

        if self.current_tool == "arrow":
            obj = ("arrow", (x1, y1), (x2, y2), self.color, self.size)

        elif self.current_tool == "rect":
            obj = ("rect", (x1, y1), (x2, y2), self.color, self.size)

        else:
            self.start_point = None
            return

        self.add_object(obj)
        self.render()

        self.start_point = None

    def render(self):
        if not self.canvas_draw:
            return

        self.canvas_draw.delete("draw")

        for obj in self.draw_objects:
            t = obj[0]

            # ================= PEN (REAL LINES) =================
            if t == "line":
                _, a, b, c, s = obj

                self.canvas_draw.create_line(
                    a[0], a[1], b[0], b[1],
                    fill=c,
                    width=s,
                    capstyle=tk.ROUND,
                    smooth=True,
                    tags="draw"
                )

            # ================= ARROW =================
            elif t == "arrow":
                _, a, b, c, s = obj

                self.canvas_draw.create_line(
                    a[0], a[1], b[0], b[1],
                    fill=c,
                    width=s,
                    arrow=tk.LAST,
                    tags="draw"
                )

                # 🔥 highlight if selected
                if obj == self.selected_object:
                    self.canvas_draw.create_line(
                        a[0], a[1], b[0], b[1],
                        fill="yellow",
                        width=s + 2,
                        dash=(4, 2),
                        arrow=tk.LAST,
                        tags="draw"
                    )

            # ================= RECT =================
            elif t == "rect":
                _, a, b, c, s = obj

                self.canvas_draw.create_rectangle(
                    a[0], a[1], b[0], b[1],
                    outline=c,
                    width=s,
                    tags="draw"
                )

                # 🔥 highlight if selected
                if obj == self.selected_object:
                    self.canvas_draw.create_rectangle(
                        a[0], a[1], b[0], b[1],
                        outline="yellow",
                        width=s + 2,
                        dash=(4, 2),
                        tags="draw"
                    )

            # ================= TEXT =================
            elif t == "text":
                _, p, text, c, s = obj

                self.canvas_draw.create_text(
                    p[0], p[1],
                    text=text,
                    fill=c,
                    font=("Arial", s * 3),
                    anchor="nw",
                    tags="draw"
                )

                # 🔥 highlight if selected
                if obj == self.selected_object:
                    self.canvas_draw.create_rectangle(
                        p[0] - 2,
                        p[1] - 2,
                        p[0] + len(text) * (s * 2),
                        p[1] + (s * 4),
                        outline="yellow",
                        dash=(4, 2),
                        tags="draw"
                    )

    def save_undo(self, obj):
        self.undo_stack.append(obj)
        self.redo_stack.clear()

    def undo_draw(self, event=None):
        if not self.undo_stack:
            return

        action, obj = self.undo_stack.pop()

        if action == "add":
            if obj in self.draw_objects:
                self.draw_objects.remove(obj)
            self.redo_stack.append(("add", obj))

        self.render()

    def redo_draw(self, event=None):
        if not self.redo_stack:
            return

        action, obj = self.redo_stack.pop()

        if action == "add":
            self.draw_objects.append(obj)
            self.undo_stack.append(("add", obj))

        self.render()

    def push_action(self, action):
        # cut future if we undo then draw again
        self.draw_history = self.draw_history[:self.history_index + 1]

        self.draw_history.append(action)
        self.history_index += 1

        self.render()



    def add_object(self, obj):
        self.draw_objects.append(obj)
        self.undo_stack.append(("add", obj))
        self.redo_stack.clear()

    def get_object_at(self, x, y):
        for i in range(len(self.draw_objects) - 1, -1, -1):
            obj = self.draw_objects[i]

            t = obj[0]

            if t in ("arrow", "line"):
                a = obj[1]
                b = obj[2]

                if min(a[0], b[0]) - 5 <= x <= max(a[0], b[0]) + 5 and \
                min(a[1], b[1]) - 5 <= y <= max(a[1], b[1]) + 5:
                    return obj

            elif t == "rect":
                a = obj[1]
                b = obj[2]

                if min(a[0], b[0]) <= x <= max(a[0], b[0]) and \
                min(a[1], b[1]) <= y <= max(a[1], b[1]):
                    return obj

            elif t == "text":
                p = obj[1]
                if abs(p[0] - x) < 50 and abs(p[1] - y) < 20:
                    return obj

        return None

    def move_last(self, dx, dy):
        # ================= SAFETY =================
        if self.active_mode != "draw":
            return

        if not self.draw_objects:
            return

        # ================= GET LAST OBJECT =================
        idx = len(self.draw_objects) - 1
        obj = self.draw_objects[idx]
        t = obj[0]

        # ================= MOVE OBJECT =================
        if t in ("line", "arrow", "rect"):
            a = obj[1]
            b = obj[2]

            new_obj = (
                t,
                (a[0] + dx, a[1] + dy),
                (b[0] + dx, b[1] + dy),
                obj[3],
                obj[4]
            )

        elif t == "text":
            p = obj[1]

            new_obj = (
                "text",
                (p[0] + dx, p[1] + dy),
                obj[2],
                obj[3],
                obj[4]
            )

        else:
            return

        # ================= UPDATE LIST =================
        self.draw_objects[idx] = new_obj

        # ================= FORCE SELECTION UPDATE =================
        self.selected_object = new_obj

        # ================= REDRAW =================
        self.render()
        self.canvas_draw.update_idletasks()

    def move_selected_node(self, dx, dy):
        if not self.editor.enabled or not self.selected_node:
            return

        node = self.selected_node

        # ask editor to move node
        self.editor.move_node(node, dx, dy)

        self.draw_handles()
        self.update_rect()

    def move_input(self, dx, dy):
        # choose target object
        if getattr(self, "selected_object", None):
            obj = self.selected_object
            idx = self.draw_objects.index(obj)
        else:
            if not self.draw_objects:
                return
            idx = len(self.draw_objects) - 1
            obj = self.draw_objects[idx]

        t = obj[0]

        if t in ("line", "arrow", "rect"):
            a = obj[1]
            b = obj[2]

            new_obj = (
                t,
                (a[0] + dx, a[1] + dy),
                (b[0] + dx, b[1] + dy),
                obj[3],
                obj[4]
            )

        elif t == "text":
            p = obj[1]

            new_obj = (
                "text",
                (p[0] + dx, p[1] + dy),
                obj[2],
                obj[3],
                obj[4]
            )

        else:
            return

        self.draw_objects[idx] = new_obj
        self.selected_object = new_obj

        self.render()

    def move_node(self, dx, dy):
        # ================= SAFETY CHECKS =================
        if not self.editor.enabled:
            return

        if not self.selected_node:
            return

        # ================= DELEGATE TO NODE EDITOR =================
        self.editor.move(dx, dy)

        # ================= FORCE VISUAL UPDATE =================
        self.draw_handles()
        self.update_rect()
        self.canvas.update_idletasks()

    def key_move(self, event):
        if self.active_mode != "draw":
            return

        key = event.keysym.lower()

        # ================= DELETE SELECTED OBJECT =================
        if key in ("delete", "backspace"):
            if getattr(self, "selected_object", None):
                obj = self.selected_object

                if obj in self.draw_objects:
                    self.draw_objects.remove(obj)

                self.selected_object = None
                self.render()
            return

        # ================= MOVE SELECTED OBJECT =================
        if key in ("up", "w"):
            self.move_input(0, -5)

        elif key in ("down", "s"):
            self.move_input(0, 5)

        elif key in ("left", "a"):
            self.move_input(-5, 0)

        elif key in ("right", "d"):
            self.move_input(5, 0)

    def global_move(self, event):
        key = event.keysym.lower()

        dx, dy = 0, 0

        if key in ("up", "w"):
            dy = -5
        elif key in ("down", "s"):
            dy = 5
        elif key in ("left", "a"):
            dx = -5
        elif key in ("right", "d"):
            dx = 5
        else:
            return

        # ================= EDIT MODE (NODES) =================
        if self.editor.enabled and self.editor.selected_node:
            self.editor.move(dx, dy)
            return

        # ================= DRAW MODE =================
        if self.active_mode == "draw":
            self.move_last(dx, dy)
            return

        # ================= SNIP MODE =================
        self.move_input(dx, dy)

    def sync_node_to_rect(self):
        if not self.editor.enabled or not self.editor.selected_node:
            return

        n = self.editor.nodes[self.editor.selected_node]

        # make rectangle follow node center
        cx, cy = n["x"], n["y"]

        # keep fixed size box around node
        size = 100  # adjust if needed

        self.start_x = cx - size
        self.start_y = cy - size
        self.end_x = cx + size
        self.end_y = cy + size

        self.update_rect()

    def update_rect_from_nodes(self):
        if not self.editor.enabled:
            return

        n = self.editor.nodes.get("n")
        s = self.editor.nodes.get("s")

        if not n or not s:
            return

        self.start_x, self.start_y = n["x"], n["y"]
        self.end_x, self.end_y = s["x"], s["y"]

        self.update_rect()

    # =========================================================
    # 8 NODES (WITH YELLOW SELECTION)
    # =========================================================
    def draw_handles(self):
        self.clear_handles()

        if not self.rect:
            return

        x1, y1, x2, y2 = self.get_coords()

        points = {
            "nw": (x1, y1),
            "n": ((x1 + x2) // 2, y1),
            "ne": (x2, y1),
            "e": (x2, (y1 + y2) // 2),
            "se": (x2, y2),
            "s": ((x1 + x2) // 2, y2),
            "sw": (x1, y2),
            "w": (x1, (y1 + y2) // 2),
        }

        for name, (x, y) in points.items():

            # highlight selected node only (NO resizing bugs)
            color = "yellow" if name == self.editor.selected_node else "white"

            h = self.canvas.create_rectangle(
                x - 5, y - 5,
                x + 5, y + 5,
                fill=color,
                outline=""
            )

            self.handles.append((h, name))

    def save_draw_result(self, path):
        from PIL import ImageDraw, ImageFont

        if self.image is None:
            print("No image to save")
            return

        img = self.image.copy()
        draw = ImageDraw.Draw(img)

        # ---------------- DRAW ALL OBJECTS ----------------
        for obj in self.draw_objects:
            t = obj[0]

            # ---------------- LINE ----------------
            if t == "line":
                _, a, b, color, size = obj
                draw.line([a, b], fill=color, width=size)

            # ---------------- ARROW ----------------
            elif t == "arrow":
                _, a, b, color, size = obj

                import math

                dx = b[0] - a[0]
                dy = b[1] - a[1]

                length = math.hypot(dx, dy)
                if length == 0:
                    continue

                # unit direction
                ux = dx / length
                uy = dy / length

                # perpendicular
                px = -uy
                py = ux

                # 🔥 SMALL CLEAN ARROW HEAD
                head_len = 12
                head_width = 5

                # back point (this is KEY FIX: prevents cut look)
                bx = b[0] - ux * head_len
                by = b[1] - uy * head_len

                left = (
                    bx + px * head_width,
                    by + py * head_width
                )

                right = (
                    bx - px * head_width,
                    by - py * head_width
                )

                # draw main line BUT STOP BEFORE TIP (IMPORTANT FIX)
                draw.line([a, (bx, by)], fill=color, width=size)

                # draw head
                draw.polygon([b, left, right], fill=color)
            # ---------------- RECT ----------------
            elif t == "rect":
                _, a, b, color, size = obj
                draw.rectangle([a, b], outline=color, width=size)

            # ---------------- TEXT ----------------
            elif t == "text":
                _, pos, text, color, size = obj
                draw.text(pos, text, fill=color)

        # ---------------- SAVE FINAL IMAGE ----------------
        img.save(path)
        print("Saved edited image:", path)

    def save_dialog(self):
        from tkinter import filedialog

        file_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[
                ("PNG", "*.png"),
                ("JPG", "*.jpg"),
                ("All Files", "*.*")
            ]
        )

        if file_path:
            self.save_draw_result(file_path)