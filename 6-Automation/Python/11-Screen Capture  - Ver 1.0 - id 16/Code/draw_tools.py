import tkinter as tk
from tkinter import colorchooser, simpledialog
from PIL import ImageDraw, ImageTk


class DrawingEditor:
    def __init__(self, image, root_ref):
        self.image = image
        self.draw = ImageDraw.Draw(self.image)
        self.root_ref = root_ref

        self.win = tk.Toplevel()
        self.win.title("Editor")

        self.color = "red"
        self.size = 3
        self.mode = "draw"

        self.tk_img = ImageTk.PhotoImage(self.image)

        self.canvas = tk.Canvas(self.win, width=image.width, height=image.height)
        self.canvas.pack()

        self.img_id = self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)

        # tools
        toolbar = tk.Frame(self.win)
        toolbar.pack()

        tk.Button(toolbar, text="Draw", command=self.draw_mode).pack(side="left")
        tk.Button(toolbar, text="Text", command=self.text_mode).pack(side="left")
        tk.Button(toolbar, text="Arrow", command=self.arrow_mode).pack(side="left")
        tk.Button(toolbar, text="Pin", command=self.pin_mode).pack(side="left")
        tk.Button(toolbar, text="Color", command=self.pick_color).pack(side="left")

        self.canvas.bind("<B1-Motion>", self.draw_free)
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<ButtonRelease-1>", self.release)

        self.start = None

        self.win.bind("<Return>", self.save)

    # ---------------- MODES ----------------
    def draw_mode(self): self.mode = "draw"
    def text_mode(self): self.mode = "text"
    def arrow_mode(self): self.mode = "arrow"
    def pin_mode(self): self.mode = "pin"

    # ---------------- ACTIONS ----------------
    def draw_free(self, e):
        if self.mode != "draw":
            return

        self.draw.ellipse([e.x, e.y, e.x+self.size, e.y+self.size], fill=self.color)
        self.refresh()

    def click(self, e):
        self.start = (e.x, e.y)

        if self.mode == "text":
            t = simpledialog.askstring("Text", "Enter text")
            if t:
                self.draw.text((e.x, e.y), t, fill=self.color)
                self.refresh()

        if self.mode == "pin":
            self.draw.ellipse([e.x-4, e.y-4, e.x+4, e.y+4], fill=self.color)
            self.refresh()

    def release(self, e):
        if self.mode == "arrow" and self.start:
            self.draw.line([self.start, (e.x, e.y)], fill=self.color, width=self.size)
            self.refresh()

    # ---------------- UI ----------------
    def pick_color(self):
        c = colorchooser.askcolor()[1]
        if c:
            self.color = c

    def refresh(self):
        self.tk_img = ImageTk.PhotoImage(self.image)
        self.canvas.itemconfig(self.img_id, image=self.tk_img)

    # ---------------- SAVE ----------------
    def save(self, event=None):
        self.image.save("output.png")
        print("Saved output.png")
        self.win.destroy()
        self.root_ref.deiconify()