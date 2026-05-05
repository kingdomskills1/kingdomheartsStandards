class NodeEditor:
    def __init__(self, core):
        self.core = core

        # real node data (this is what you move)
        self.nodes = {
            "n": {"x": 0, "y": 0},
            "s": {"x": 0, "y": 0}
        }

        self.enabled = False
        self.selected_node = None

        # toggle edit mode
        self.core.root.bind("<Control-s>", self.toggle_edit)

        # IMPORTANT: use KeyPress (more reliable than bind alone)
        self.core.root.bind("<KeyPress-Up>", self.move)
        self.core.root.bind("<KeyPress-Down>", self.move)
        self.core.root.bind("<KeyPress-Left>", self.move)
        self.core.root.bind("<KeyPress-Right>", self.move)

    # =========================================================
    # TOGGLE EDIT MODE
    # =========================================================
    def toggle_edit(self, event=None):
        self.enabled = not self.enabled
        self.selected_node = None
        print("Edit mode:", self.enabled)

    # =========================================================
    # SELECT NODE
    # =========================================================
    def select_node(self, node):
        if not self.enabled:
            return

        self.selected_node = node
        print("Selected node:", node)

        # IMPORTANT: force redraw so rectangle stays visible
        self.core.update_rect()
        self.core.draw_handles()

    # =========================================================
    # MOVE NODE (ARROWS)
    # =========================================================
    def move(self, dx, dy):
        if not self.enabled or not self.selected_node:
            return

        c = self.core
        n = self.selected_node

        # ---------------- MOVE CORNERS ----------------
        if n == "nw":
            c.start_x += dx
            c.start_y += dy

        elif n == "ne":
            c.end_x += dx
            c.start_y += dy

        elif n == "se":
            c.end_x += dx
            c.end_y += dy

        elif n == "sw":
            c.start_x += dx
            c.end_y += dy

        # ---------------- MOVE EDGES ----------------
        elif n == "n":
            c.start_y += dy

        elif n == "s":
            c.end_y += dy

        elif n == "w":
            c.start_x += dx

        elif n == "e":
            c.end_x += dx

        # ---------------- SAFETY FIX (VERY IMPORTANT) ----------------
        # prevent rectangle flipping or breaking
        if c.start_x > c.end_x:
            c.start_x, c.end_x = c.end_x, c.start_x

        if c.start_y > c.end_y:
            c.start_y, c.end_y = c.end_y, c.start_y

        # ---------------- REFRESH UI ----------------
        c.update_rect()
        c.draw_handles()