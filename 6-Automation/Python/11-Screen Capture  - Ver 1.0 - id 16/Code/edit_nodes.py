class NodeEditor:
    def __init__(self, core):
        self.core = core

        # ================= 8 NODES =================
        self.nodes = {
            "nw": {"x": 0, "y": 0},
            "n":  {"x": 0, "y": 0},
            "ne": {"x": 0, "y": 0},
            "e":  {"x": 0, "y": 0},
            "se": {"x": 0, "y": 0},
            "s":  {"x": 0, "y": 0},
            "sw": {"x": 0, "y": 0},
            "w":  {"x": 0, "y": 0},
        }

        self.enabled = False
        self.selected_node = None
        self.dragging = False

        # mouse events
        self.core.canvas.bind("<ButtonPress-1>", self.on_press)
        self.core.canvas.bind("<B1-Motion>", self.on_drag)
        self.core.canvas.bind("<ButtonRelease-1>", self.on_release)

    # =========================================================
    # SELECT NODE
    # =========================================================
    def get_node(self, x, y):
        for name, node in self.nodes.items():
            nx, ny = node["x"], node["y"]
            if abs(nx - x) < 6 and abs(ny - y) < 6:
                return name
        return None

    # =========================================================
    # MOUSE PRESS
    # =========================================================
    def on_press(self, event):
        if not self.enabled:
            return

        node = self.get_node(event.x, event.y)

        if node:
            self.selected_node = node
            self.dragging = True

    # =========================================================
    # DRAG NODE (RESIZE RECTANGLE)
    # =========================================================
    def on_drag(self, event):
        if not self.enabled or not self.dragging:
            return

        c = self.core
        n = self.selected_node

        x, y = event.x, event.y

        # ================= CORNERS =================
        if n == "nw":
            c.sel_start = (x, y)

        elif n == "ne":
            c.sel_start = (c.sel_start[0], y)
            c.sel_end = (x, c.sel_end[1])

        elif n == "se":
            c.sel_end = (x, y)

        elif n == "sw":
            c.sel_start = (x, c.sel_start[1])
            c.sel_end = (c.sel_end[0], y)

        # ================= EDGES =================
        elif n == "n":
            c.sel_start = (c.sel_start[0], y)

        elif n == "s":
            c.sel_end = (c.sel_end[0], y)

        elif n == "w":
            c.sel_start = (x, c.sel_start[1])

        elif n == "e":
            c.sel_end = (x, c.sel_end[1])

        # refresh rectangle
        c.update_selection_rect()
        self.update_nodes()

    # =========================================================
    # RELEASE
    # =========================================================
    def on_release(self, event):
        self.dragging = False
        self.selected_node = None

    # =========================================================
    # UPDATE NODE POSITIONS FROM RECT
    # =========================================================
    def update_nodes(self):
        c = self.core

        if not c.sel_start or not c.sel_end:
            return

        x1, y1 = c.sel_start
        x2, y2 = c.sel_end

        self.nodes["nw"] = {"x": x1, "y": y1}
        self.nodes["ne"] = {"x": x2, "y": y1}
        self.nodes["se"] = {"x": x2, "y": y2}
        self.nodes["sw"] = {"x": x1, "y": y2}

        self.nodes["n"] = {"x": (x1 + x2) // 2, "y": y1}
        self.nodes["s"] = {"x": (x1 + x2) // 2, "y": y2}
        self.nodes["w"] = {"x": x1, "y": (y1 + y2) // 2}
        self.nodes["e"] = {"x": x2, "y": (y1 + y2) // 2}

    def draw_nodes(self):
        c = self.core

        # remove old nodes
        c.canvas.delete("node")

        if not c.sel_start or not c.sel_end:
            return

        x1, y1 = c.sel_start
        x2, y2 = c.sel_end

        # normalize
        x1, x2 = sorted([x1, x2])
        y1, y2 = sorted([y1, y2])

        # 8 node positions
        points = {
            "nw": (x1, y1),
            "n":  ((x1+x2)//2, y1),
            "ne": (x2, y1),

            "w":  (x1, (y1+y2)//2),
            "e":  (x2, (y1+y2)//2),

            "sw": (x1, y2),
            "s":  ((x1+x2)//2, y2),
            "se": (x2, y2),
        }

        self.nodes = points

        # draw red dots
        for name, (x, y) in points.items():
            c.canvas.create_oval(
                x-5, y-5,
                x+5, y+5,
                fill="white",
                outline="black",
                tags="node"
            )

    def get_handle(self, x, y):
        for name, (hx, hy) in self.nodes.items():
            if abs(hx - x) <= 6 and abs(hy - y) <= 6:
                return name
        return None