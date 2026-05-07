import tkinter as tk
from tkinter import filedialog
from edit_nodes import NodeEditor

class SnipCore:
    def __init__(self):
        self.root = tk.Tk()
        self.root.state("zoomed")
        self.root.configure(bg="black")

        self.last_saved_file = None
        self.last_saved_path = None
        self.edit_mode = False
        self.selected_node = None
        self.draw_win = None
        self.draw_mode = False
        self.sel_start = None
        self.sel_end = None
        self.drag_mode = None   # "move" | "resize" | "draw"
        self.move_offset = (0, 0)
        self.text_size = 24
        self.color = "red"
        self.size = 3
        self.draw_objects = []
        self.selected_object = None
        self.start_point = None
        self.last_point = None
        self.preview_item = None

        self.tk_img_main = None
        self.tk_img_draw = None

        self.current_tool = "pen"
        self.selected_object = None
        self.start_point = None
        self.last_point = None
        self.preview_item = None

        self.canvas = tk.Canvas(self.root, cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.editor = NodeEditor(self)


        self.root.tk.call('tk', 'scaling', 1.0)

        # ================= IMAGE =================
        self.image = None
        self.tk_img = None

        # ================= MODES =================
        self.mode = "snip"   # snip | draw | edit

        # ================= SELECTION =================
        self.selecting = False
        self.sel_start = None
        self.sel_rect = None

        # ================= NODES (8 handles) =================
        self.handles = []
        self.active_handle = None
        self.handle_map = [
            "nw", "ne", "se", "sw",
            "n", "s", "w", "e"
        ]

        # ================= DRAW =================
        self.draw_objects = []
        self.current_tool = "pen"
        self.last_point = None


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


        # ================= EVENTS =================
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.root.bind("<Control-e>", self.toggle_edit_mode)
        self.root.bind("<Return>", self.save_selection)
        self.root.bind("<Escape>", self.reset)
        self.root.bind("<Up>",    lambda e: self.move_node_by(0, -5))
        self.root.bind("<Down>",  lambda e: self.move_node_by(0, 5))
        self.root.bind("<Left>",  lambda e: self.move_node_by(-5, 0))
        self.root.bind("<Right>", lambda e: self.move_node_by(5, 0))
        self.root.bind("<Control-d>", self.toggle_draw_mode)

        # mode switches
        self.root.bind("1", lambda e: self.set_mode("snip"))
        self.root.bind("2", lambda e: self.set_mode("draw"))
        self.root.bind("3", lambda e: self.set_mode("edit"))


    # =========================================================
    # MODE SWITCH
    # =========================================================
    def set_mode(self, mode):
        self.mode = mode
        print("Mode:", mode)

    # =========================================================
    # CAPTURE SCREEN
    # =========================================================
    def capture_screen(self):
        import ctypes
        import time
        from PIL import ImageGrab, ImageTk

        # ===== FIX DPI =====
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except:
            pass

        # ===== HIDE APP FIRST =====
        self.root.withdraw()
        self.root.update()

        # small delay to ensure clean screen
        time.sleep(0.15)

        # ===== TAKE FULL SCREENSHOT =====
        self.image = ImageGrab.grab(all_screens=True)

        # save size for later cropping
        self.img_width, self.img_height = self.image.size

        # ===== SHOW APP AGAIN =====
        self.root.deiconify()

        # force maximize after capture
        self.root.state("zoomed")
        self.root.lift()
        self.root.focus_force()


        # ===== DISPLAY IMAGE =====
        self.tk_img = ImageTk.PhotoImage(self.image)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)

        # reset selection
        self.sel_start = None
        self.sel_rect = None
        self.selecting = True

        print("Full screen captured ✔")

    # =========================================================
    # MOUSE PRESS
    # =========================================================
    def on_press(self, e):

        # ================= EDIT MODE =================
        if self.edit_mode:
            self.select_node(e.x, e.y)
            return

        # ================= NORMAL MODE =================
        if self.mode != "snip":
            return

        result = self.hit_test(e.x, e.y)

        if result:
            self.drag_mode, self.active_handle = result
            self.move_offset = (e.x, e.y)
            return

        self.clear_selection()
        self.sel_start = (e.x, e.y)
        self.sel_end = (e.x, e.y)
        self.drag_mode = "draw"

    # =========================================================
    # DRAG
    # =========================================================
    def on_drag(self, e):

        if self.edit_mode:
            return

        if self.mode != "snip":
            return

        # ================= RESIZE ONLY FROM NODE =================
        if self.drag_mode == "resize":

            x1, y1, x2, y2 = self.get_normalized()
            h = self.active_handle

            if h == "nw":
                x1, y1 = e.x, e.y
            elif h == "ne":
                x2, y1 = e.x, e.y
            elif h == "se":
                x2, y2 = e.x, e.y
            elif h == "sw":
                x1, y2 = e.x, e.y
            elif h == "n":
                y1 = e.y
            elif h == "s":
                y2 = e.y
            elif h == "w":
                x1 = e.x
            elif h == "e":
                x2 = e.x

            self.sel_start = (x1, y1)
            self.sel_end = (x2, y2)

        # ================= MOVE ONLY INSIDE RECT =================
        elif self.drag_mode == "move":

            dx = e.x - self.move_offset[0]
            dy = e.y - self.move_offset[1]

            self.move_offset = (e.x, e.y)

            x1, y1, x2, y2 = self.get_normalized()

            x1 += dx
            y1 += dy
            x2 += dx
            y2 += dy

            self.sel_start = (x1, y1)
            self.sel_end = (x2, y2)

        # ================= DRAW =================
        else:
            self.sel_end = (e.x, e.y)

        self.redraw_selection()

    # =========================================================
    # RELEASE
    # =========================================================
    def on_release(self, e):

        self.drag_mode = None
        self.active_handle = None
        self.selecting = False

        self.redraw_selection()

    # =========================================================
    # SAVE SNIP
    # =========================================================
    def save_selection(self, event=None):

        if not self.image:
            print("No image loaded")
            return

        img_w, img_h = self.image.size

        # ================= NO SELECTION → FULL SCREEN =================
        if not self.sel_start or not self.sel_end:
            cropped = self.image.copy()
            print("No selection → saving full image ✔")
        else:
            x1, y1 = self.sel_start
            x2, y2 = self.sel_end

            left = min(x1, x2)
            top = min(y1, y2)
            right = max(x1, x2)
            bottom = max(y1, y2)

            # clamp to image bounds
            left = max(0, min(left, img_w))
            right = max(0, min(right, img_w))
            top = max(0, min(top, img_h))
            bottom = max(0, min(bottom, img_h))

            if right - left < 2 or bottom - top < 2:
                print("Invalid selection → saving full image ✔")
                cropped = self.image.copy()
            else:
                cropped = self.image.crop((left, top, right, bottom))
                print("Saved selected region ✔")

        # ================= SAVE =================
        path = filedialog.asksaveasfilename(defaultextension=".png")

        if path:
            try:
                cropped.save(path)
                self.last_saved_file = path
            except Exception as e:
                print("Save failed:", e)

    # =========================================================
    # RESET
    # =========================================================
    def reset(self, e=None):
        self.canvas.delete("all")
        self.root.withdraw()

    # =========================================================
    # NODE DETECTION (placeholder)
    # =========================================================
    def get_handle(self, x, y):
        for h in self.handles:
            hx, hy = h
            if abs(hx - x) < 5 and abs(hy - y) < 5:
                return h
        return None
    
    def start_select(self, event):
        self.sel_start = (event.x, event.y)

    def update_select(self, event):
        self.sel_end = (event.x, event.y)

    def sync_rect_to_nodes(self):
        x1, y1 = self.sel_start
        x2, y2 = self.sel_end

        self.editor.nodes["nw"] = {"x": x1, "y": y1}
        self.editor.nodes["ne"] = {"x": x2, "y": y1}
        self.editor.nodes["se"] = {"x": x2, "y": y2}
        self.editor.nodes["sw"] = {"x": x1, "y": y2}

    def update_selection_rect(self):
        if self.sel_rect:
            self.canvas.delete(self.sel_rect)

        x1, y1 = self.sel_start
        x2, y2 = self.sel_end

        self.sel_rect = self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline="red",
            width=2
        )


    def clear_selection(self):

        # remove rectangle
        if self.sel_rect:
            self.canvas.delete(self.sel_rect)
            self.sel_rect = None

        # remove all nodes
        for h in self.handles:
            self.canvas.delete(h)

        self.handles = []

    def build_handles(self, x1, y1, x2, y2):

        size = 5
        color = "black"

        points = [
            (x1, y1),
            (x2, y1),
            (x2, y2),
            (x1, y2),

            ((x1 + x2)//2, y1),
            ((x1 + x2)//2, y2),
            (x1, (y1 + y2)//2),
            (x2, (y1 + y2)//2),
        ]

        self.handles = []

        for x, y in points:
            h = self.canvas.create_rectangle(
                x-size, y-size,
                x+size, y+size,
                fill="white",
                outline="black"
            )
            self.handles.append(h)

        def is_inside_rect(self, x, y):

            if not self.sel_rect:
                return False

            coords = self.canvas.coords(self.sel_rect)
            x1, y1, x2, y2 = coords

            return x1 <= x <= x2 and y1 <= y <= y2
        
        def move_rectangle(self, x, y):

            dx = x - self.move_offset[0]
            dy = y - self.move_offset[1]

            self.move_offset = (x, y)

            # move rectangle
            self.canvas.move(self.sel_rect, dx, dy)

            # move handles
            for h in self.handles:
                self.canvas.move(h, dx, dy)

            # update stored coords
            coords = self.canvas.coords(self.sel_rect)
            x1, y1, x2, y2 = coords

            self.sel_start = (x1, y1)
            self.sel_end = (x2, y2)

        def resize_from_handle(self, x, y):

            coords = self.canvas.coords(self.sel_rect)
            x1, y1, x2, y2 = coords

            h = self.active_handle

            if h == "nw":
                x1, y1 = x, y
            elif h == "ne":
                x2, y1 = x, y
            elif h == "se":
                x2, y2 = x, y
            elif h == "sw":
                x1, y2 = x, y

            # update rectangle
            self.canvas.coords(self.sel_rect, x1, y1, x2, y2)

            # rebuild nodes
            for h in self.handles:
                self.canvas.delete(h)

            self.build_handles(x1, y1, x2, y2)

    def hit_test(self, x, y):
        if not self.sel_start or not self.sel_end:
            return None

        x1, y1 = self.sel_start
        x2, y2 = self.sel_end

        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)

        # ================= 1. NODES FIRST (HIGHEST PRIORITY) =================
        points = {
            "nw": (x1, y1),
            "ne": (x2, y1),
            "se": (x2, y2),
            "sw": (x1, y2),
            "n":  ((x1+x2)//2, y1),
            "s":  ((x1+x2)//2, y2),
            "w":  (x1, (y1+y2)//2),
            "e":  (x2, (y1+y2)//2),
        }

        for name, (hx, hy) in points.items():
            if abs(hx - x) <= 6 and abs(hy - y) <= 6:
                return ("resize", name)

        # ================= 2. INSIDE RECTANGLE =================
        if x1 <= x <= x2 and y1 <= y <= y2:
            return ("move", None)

        return None

    def redraw_selection(self):

        coords = self.get_normalized()
        if not coords:
            return

        x1, y1, x2, y2 = coords

        # ---- rectangle ----
        if self.sel_rect:
            self.canvas.delete(self.sel_rect)

        self.sel_rect = self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline="black",
            width=2
        )

        # ---- handles ----
        for h in self.handles:
            self.canvas.delete(h)

        self.build_handles(x1, y1, x2, y2)

    def on_mouse_move(self, e):

        if self.edit_mode:
            return

        if self.mode != "snip":
            return

        result = self.hit_test(e.x, e.y)

        # ================= RESIZE NODES =================
        if result and result[0] == "resize":
            node = result[1]

            if node in ["nw", "se"]:
                self.canvas.config(cursor="size_nw_se")
            elif node in ["ne", "sw"]:
                self.canvas.config(cursor="size_ne_sw")
            elif node in ["n", "s"]:
                self.canvas.config(cursor="sb_v_double_arrow")
            elif node in ["e", "w"]:
                self.canvas.config(cursor="sb_h_double_arrow")
            return

        # ================= MOVE INSIDE =================
        if result and result[0] == "move":
            self.canvas.config(cursor="fleur")   # Lightshot move hand
            return

        # ================= DEFAULT (LIGHTSHOT STYLE) =================
        self.canvas.config(cursor="crosshair")

    def get_normalized(self):
        if not self.sel_start or not self.sel_end:
            return None

        x1, y1 = self.sel_start
        x2, y2 = self.sel_end

        return (
            min(x1, x2),
            min(y1, y2),
            max(x1, x2),
            max(y1, y2)
        )
    
    def toggle_edit_mode(self, event=None):

        self.edit_mode = not self.edit_mode
        self.selected_node = None

        print("EDIT MODE:", self.edit_mode)

        # ================= TURNING OFF =================
        if not self.edit_mode:
            self.canvas.delete("highlight")   # ❗ remove yellow node highlight
            self.canvas.config(cursor="crosshair")
            return

        # ================= TURNING ON =================
        self.canvas.config(cursor="crosshair")

    def toggle_draw_mode(self, event=None):

        # prevent multiple windows
        if getattr(self, "draw_win", None) and self.draw_win.winfo_exists():
            self.draw_win.lift()
            self.draw_win.focus_force()
            return

        self.draw_mode = not self.draw_mode

        if self.draw_mode:

            self.active_mode = "draw"

            # ================= LOAD LAST SAVED FILE =================
            if self.last_saved_file:

                from PIL import Image

                try:
                    self.image = Image.open(self.last_saved_file)
                    print("Loaded last saved file ✔")

                except Exception as e:
                    print("Failed loading saved file:", e)
                    self.capture_screen()

            else:
                # first time only
                self.capture_screen()

            self.open_draw_window()

        else:

            self.active_mode = "snip"

            if self.draw_win:
                self.draw_win.destroy()
                self.draw_win = None

    def select_node(self, x, y):

        coords = self.get_normalized()
        if not coords:
            return

        x1, y1, x2, y2 = coords

        points = {
            "nw": (x1, y1),
            "ne": (x2, y1),
            "se": (x2, y2),
            "sw": (x1, y2),
            "n":  ((x1+x2)//2, y1),
            "s":  ((x1+x2)//2, y2),
            "w":  (x1, (y1+y2)//2),
            "e":  (x2, (y1+y2)//2),
        }

        for name, (nx, ny) in points.items():
            if abs(nx - x) <= 8 and abs(ny - y) <= 8:
                self.selected_node = name
                self.highlight_nodes()
                return
            
    def highlight_nodes(self):

        self.redraw_selection()

        # remove old highlight
        self.canvas.delete("highlight")

        if not self.selected_node:
            return

        coords = self.get_normalized()
        if not coords:
            return

        x1, y1, x2, y2 = coords

        points = {
            "nw": (x1, y1),
            "ne": (x2, y1),
            "se": (x2, y2),
            "sw": (x1, y2),
            "n":  ((x1+x2)//2, y1),
            "s":  ((x1+x2)//2, y2),
            "w":  (x1, (y1+y2)//2),
            "e":  (x2, (y1+y2)//2),
        }

        x, y = points[self.selected_node]

        self.canvas.create_rectangle(
            x-6, y-6, x+6, y+6,
            outline="yellow",
            width=2,
            tags="highlight"
        )

    def move_node(self, event):

        if not self.edit_mode or not self.selected_node:
            return

        dx, dy = 0, 0

        if event.keysym == "Up":
            dy = -5
        elif event.keysym == "Down":
            dy = 5
        elif event.keysym == "Left":
            dx = -5
        elif event.keysym == "Right":
            dx = 5

        x1, y1, x2, y2 = self.get_normalized()

        if self.selected_node == "nw":
            x1 += dx; y1 += dy
        elif self.selected_node == "ne":
            x2 += dx; y1 += dy
        elif self.selected_node == "se":
            x2 += dx; y2 += dy
        elif self.selected_node == "sw":
            x1 += dx; y2 += dy
        elif self.selected_node == "n":
            y1 += dy
        elif self.selected_node == "s":
            y2 += dy
        elif self.selected_node == "w":
            x1 += dx
        elif self.selected_node == "e":
            x2 += dx

        self.sel_start = (x1, y1)
        self.sel_end = (x2, y2)

        self.redraw_selection()
        self.highlight_nodes()

    def open_draw_window(self):
        import tkinter as tk
        from PIL import Image, ImageTk

        # ================= GET IMAGE OR CREATE EMPTY =================
        img = getattr(self, "image", None)

        if img is None:
            # create empty white canvas image
            img = Image.new("RGB", (800, 600), "white")
            self.image = img

        w, h = img.size

        # ================= WINDOW =================
        self.draw_win = tk.Toplevel(self.root)
        self.draw_win.title("Draw Mode")
        self.draw_win.configure(bg="gray20")

        # IMPORTANT: keep reference focus
        self.draw_win.lift()
        self.draw_win.focus_force()

        # ================= TOOLBAR (FIXED LAYOUT) =================
        bar = tk.Frame(self.draw_win, bg="gray30")
        bar.pack(side="top", fill="x")

        tk.Button(bar, text="Pen", command=lambda: self.set_tool("pen")).pack(side="left")
        tk.Button(bar, text="Text", command=lambda: self.set_tool("text")).pack(side="left")
        tk.Button(bar, text="Arrow", command=lambda: self.set_tool("arrow")).pack(side="left")
        tk.Button(bar, text="Rect", command=lambda: self.set_tool("rect")).pack(side="left")

        tk.Button(bar, text="Undo", command=self.undo_draw).pack(side="left")
        tk.Button(bar, text="Redo", command=self.redo_draw).pack(side="left")
        tk.Button(bar, text="A+", command=self.increase_text_size).pack(side="left")
        tk.Button(bar, text="A-", command=self.decrease_text_size).pack(side="left")
        self.text_size_label = tk.Label(
            bar,
            text=f"Text Size: {self.text_size}",
            bg="gray30",
            fg="white"
        )
        self.text_size_label.pack(side="left", padx=10)
        tk.Button(bar, text="Color", command=self.pick_color).pack(side="left")
        tk.Button(bar, text="Save", command=self.save_dialog).pack(side="left")
        tk.Button(bar, text="Open", command=self.open_image_file).pack(side="left")



        # ================= CANVAS FRAME =================
        canvas_frame = tk.Frame(self.draw_win)
        canvas_frame.pack(fill="both", expand=True)

        self.canvas_draw = tk.Canvas(
            canvas_frame,
            width=w,
            height=h,
            bg="white",
            highlightthickness=0
        )
        self.canvas_draw.pack(fill="both", expand=True)

        # ================= IMAGE =================
        self.tk_img_draw = ImageTk.PhotoImage(img)
        self.canvas_draw.create_image(0, 0, anchor="nw", image=self.tk_img_draw)

        # ================= EVENTS =================
        self.canvas_draw.bind("<Button-1>", self.draw_start)
        self.canvas_draw.bind("<B1-Motion>", self.draw_move)
        self.canvas_draw.bind("<ButtonRelease-1>", self.draw_end)
        # undo / redo shortcuts INSIDE draw window
        self.draw_win.bind("<Control-z>", self.undo_draw)
        self.draw_win.bind("<Control-y>", self.redo_draw)

        # also bind canvas directly
        self.canvas_draw.bind("<Control-z>", self.undo_draw)
        self.canvas_draw.bind("<Control-y>", self.redo_draw)

        self.draw_win.bind("<Control-plus>", self.increase_text_size)
        self.draw_win.bind("<Control-minus>", self.decrease_text_size)
        self.draw_win.bind("<Return>", self.save_dialog)
        self.draw_win.bind("<KeyPress>", self.key_move)
        self.canvas_draw.focus_set()

        print("Draw window opened ✔")


    # draw functions
    def set_tool(self, tool):
        self.current_tool = tool

        if self.canvas_draw:
            if tool == "pen":
                self.canvas_draw.config(cursor="pencil")
            else:
                self.canvas_draw.config(cursor="cross")

    def pick_color(self):
        from tkinter import colorchooser

        self.active_mode = "dialog"

        self.draw_win.lift()
        self.draw_win.focus_force()

        color = colorchooser.askcolor(title="Pick Color")[1]

        self.active_mode = "draw"

        if color:
            self.color = color
            print("Selected color:", color)

        # 🔥 FORCE FOCUS BACK
        if self.draw_win:
            self.draw_win.after(50, lambda: self.draw_win.focus_force())

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
                obj = ("text", self.start_point, t, self.color, self.text_size)
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
                    font=("Arial", s),
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

    def move_node_by(self, dx, dy):
        if not self.edit_mode or not self.selected_node:
            return

        x1, y1, x2, y2 = self.get_normalized()

        if self.selected_node == "nw":
            x1 += dx; y1 += dy
        elif self.selected_node == "ne":
            x2 += dx; y1 += dy
        elif self.selected_node == "se":
            x2 += dx; y2 += dy
        elif self.selected_node == "sw":
            x1 += dx; y2 += dy
        elif self.selected_node == "n":
            y1 += dy
        elif self.selected_node == "s":
            y2 += dy
        elif self.selected_node == "w":
            x1 += dx
        elif self.selected_node == "e":
            x2 += dx

        self.sel_start = (x1, y1)
        self.sel_end = (x2, y2)

        self.redraw_selection()
        self.highlight_nodes()

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

    def save_draw_result(self, file_path):
        from PIL import ImageDraw, ImageFont
        import math

        if not file_path:
            print("No file path selected")
            return

        if self.image is None:
            print("No image to save")
            return

        try:
            img = self.image.copy()
            draw = ImageDraw.Draw(img)

            for obj in list(self.draw_objects):  # defensive copy
                t = obj[0]

                if t == "line":
                    _, a, b, color, size = obj
                    draw.line([a, b], fill=color, width=size)

                elif t == "arrow":
                    _, a, b, color, size = obj

                    ax, ay = a
                    bx, by = b

                    dx = bx - ax
                    dy = by - ay

                    length = math.hypot(dx, dy)
                    if length == 0:
                        continue   # ❗ don't break whole save

                    ux = dx / length
                    uy = dy / length

                    px = -uy
                    py = ux

                    line_size = max(2, int(size * 1.4))

                    head_len = max(7, line_size * 2.3)
                    head_w   = max(5, line_size * 1.5)
                    
                    # small extra spacing between line and head
                    ex = bx - ux * head_len
                    ey = by - uy * head_len
                    shaft_width = max(size + 2, int(size * 1.8))


                    draw.line([(ax, ay), (ex, ey)], fill=color, width=shaft_width)

                    tip = (bx, by)

                    left = (
                        ex - ux * head_len + px * head_w,
                        ey - uy * head_len + py * head_w
                    )

                    right = (
                        ex - ux * head_len - px * head_w,
                        ey - uy * head_len - py * head_w
                    )

                    draw.polygon([tip, left, right], fill=color)

                elif t == "rect":
                    _, a, b, color, size = obj
                    x0 = min(a[0], b[0])
                    y0 = min(a[1], b[1])
                    x1 = max(a[0], b[0])
                    y1 = max(a[1], b[1])
                    draw.rectangle([(x0, y0), (x1, y1)], outline=color, width=size)

                elif t == "text":
                    _, pos, text, color, size = obj
                    try:
                        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", size)
                    except:
                        font = ImageFont.load_default()

                    draw.text(pos, text, fill=color, font=font)

            img.save(file_path)

            self.last_saved_file = file_path
            self.last_saved_path = file_path

            print("Saved ✔", file_path)

        except Exception as e:
            print("SAVE FAILED ❌:", e)

    def save_dialog(self, event=None):
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
            self.last_saved_path = file_path
            self.save_draw_result(file_path)

    def open_image_file(self):
        from tkinter import filedialog
        from PIL import Image, ImageTk

        if self.draw_win:
            self.draw_win.lift()
            self.draw_win.focus_force()

        file_path = filedialog.askopenfilename(
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.bmp"),
                ("All Files", "*.*")
            ]
        )

        # 🔥 return focus immediately
        if self.draw_win:
            self.draw_win.after(50, lambda: self.draw_win.focus_force())

        if not file_path:
            return

        img = Image.open(file_path)
        self.image = img

        self.draw_objects.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()

        w, h = img.size
        self.canvas_draw.config(width=w, height=h)

        self.tk_img = ImageTk.PhotoImage(img)

        self.canvas_draw.delete("all")
        self.canvas_draw.create_image(0, 0, anchor="nw", image=self.tk_img)

        print("Image loaded ✅")

    def increase_text_size(self, event=None):
        self.text_size += 2

        if hasattr(self, "text_size_label"):
            self.text_size_label.config(
                text=f"Text Size: {self.text_size}"
            )

        print("Text Size:", self.text_size)


    def decrease_text_size(self, event=None):
        self.text_size = max(6, self.text_size - 2)

        if hasattr(self, "text_size_label"):
            self.text_size_label.config(
                text=f"Text Size: {self.text_size}"
            )

        print("Text Size:", self.text_size)