import tkinter as tk


class ViewerUIMixin:

    def _build_interface(self):
        # Toolbar
        self.toolbar = tk.Frame(self.root, bg="#303030", padx=8, pady=8)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)
        self.toolbar_controls = tk.Frame(self.toolbar, bg="#303030")
        self.toolbar_controls.pack(side=tk.TOP, fill=tk.X)
        self.collage_toolbar = tk.Frame(self.toolbar, bg="#303030")
        self.collage_toolbar.pack(side=tk.TOP, fill=tk.X)

        buttons = [
            ("Open", self.open_image),
            ("Move / Resize", self.begin_image_layout),
            ("Full Screen Size", self.fit_image_to_screen),
            ("Save Image", self.save_image),
            ("Create Collage", self.create_collage),
            ("Add Images", self.add_collage_images),
            ("Save Collage", self.save_collage),
            ("Previous", self.previous_image),
            ("Next", self.next_image),
            ("Zoom +", lambda: self.change_zoom(1.2)),
            ("Zoom -", lambda: self.change_zoom(1 / 1.2)),
            ("Fit", self.fit_image),
            ("Actual Size", self.actual_size),
            ("Rotate Left", lambda: self.rotate_image(-90)),
            ("Rotate Right", lambda: self.rotate_image(90)),
            ("Crop", self.begin_crop),
            ("Apply Crop", self.apply_crop),
            ("Cancel Crop", self.cancel_crop),
            ("Undo", self.undo),
            ("Redo", self.redo),
            ("Fullscreen", self.toggle_fullscreen),
        ]

        self.toolbar_buttons = []
        self.collage_buttons = []
        self.image_layout_buttons = []
        for label, command in buttons:
            button_parent = (
                self.collage_toolbar
                if label in {"Create Collage", "Add Images", "Save Collage"}
                else self.toolbar_controls
            )
            button = tk.Button(
                button_parent,
                text=label,
                command=command,
                bg="#454545",
                fg="white",
                activebackground="#606060",
                activeforeground="white",
                relief=tk.FLAT,
                padx=8,
                pady=5,
                cursor="hand2"
            )
            if label == "Apply Crop":
                self.apply_crop_button = button
                continue
            if label == "Cancel Crop":
                self.cancel_crop_button = button
                continue
            button.pack(side=tk.LEFT, padx=2)
            if label in {"Create Collage", "Add Images", "Save Collage"}:
                self.collage_buttons.append(button)
            elif label in {"Open", "Move / Resize", "Full Screen Size", "Save Image"}:
                self.image_layout_buttons.append(button)
            else:
                self.toolbar_buttons.append(button)

        self.apply_crop_button.pack(side=tk.LEFT, padx=2)
        self.apply_crop_button.pack_forget()
        self.cancel_crop_button.pack(side=tk.LEFT, padx=2)
        self.cancel_crop_button.pack_forget()

        # Image display area
        self.canvas = tk.Canvas(
            self.root,
            bg="#202020",
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Status bar
        self.status = tk.Label(
            self.root,
            text="Open an image to get started",
            bg="#303030",
            fg="#eeeeee",
            anchor="w",
            padx=10,
            pady=7
        )
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas.bind("<Configure>", self._on_resize)

        # Mouse wheel zoom
        self.canvas.bind("<MouseWheel>", self._mouse_zoom)

        # Drag image when zoomed in or crop selection
        self.canvas.bind("<ButtonPress-1>", self._handle_canvas_press)
        self.canvas.bind("<B1-Motion>", self._handle_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._handle_canvas_release)

        # Double-click to toggle fullscreen
        self.canvas.bind(
            "<Double-Button-1>",
            lambda event: self.toggle_fullscreen()
        )

    def _bind_shortcuts(self):
        self.root.bind("<Control-o>", lambda event: self.open_image())
        self.root.bind("<Left>", lambda event: self.previous_image())
        self.root.bind("<Right>", lambda event: self.next_image())
        self.root.bind("<plus>", lambda event: self.change_zoom(1.2))
        self.root.bind("<equal>", lambda event: self.change_zoom(1.2))
        self.root.bind("<minus>", lambda event: self.change_zoom(1 / 1.2))
        self.root.bind("<Control-0>", lambda event: self.fit_image())
        self.root.bind("<Control-1>", lambda event: self.actual_size())
        self.root.bind("<Control-z>", lambda event: self.undo())
        self.root.bind("<Control-y>", lambda event: self.redo())
        self.root.bind("<Control-Z>", lambda event: self.redo())
        self.root.bind("<Escape>", lambda event: self.handle_escape())
        self.root.bind("<F11>", lambda event: self.toggle_fullscreen())
        self.root.bind("<Control-w>", lambda event: self.close_image())

    def _initial_message(self):
        if self.original_image is not None or self.collage_mode:
            return

        self.canvas.create_text(
            max(1, self.canvas.winfo_width() // 2),
            max(1, self.canvas.winfo_height() // 2),
            text="Open an image\n\nCtrl + O",
            fill="#aaaaaa",
            font=("Segoe UI", 20),
            justify=tk.CENTER,
            tags="placeholder"
        )

    def _on_resize(self, event):
        if self.crop_mode:
            self.cancel_crop()
        if self.collage_mode:
            self._render_collage()
            return
        if self.image_layout_mode:
            self._render_image_layout()
            return
        if self.original_image is not None and self.fit_mode:
            self.display_current_image()

    def handle_escape(self):
        if self.crop_mode:
            self.cancel_crop()
        elif self.image_layout_mode:
            self.begin_image_layout()
        else:
            self.exit_fullscreen()

    def close_image(self):
        self.image_path = None
        self.original_image = None
        self.image_layout_mode = False
        self.image_layout_drag_action = None
        self.display_image = None
        self.photo = None
        self.folder_images = []
        self.image_index = 0
        self.collage_mode = False
        self.collage_items = []
        self.collage_selected_index = None
        self.collage_drag_action = None
        self.collage_photos = []
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.crop_mode = False
        self.canvas.configure(cursor="")
        self.apply_crop_button.pack_forget()
        self.cancel_crop_button.pack_forget()
        for button in (
            self.toolbar_buttons
            + self.collage_buttons
            + self.image_layout_buttons
        ):
            button.configure(state=tk.NORMAL)
        if self.crop_rect_id is not None:
            self.canvas.delete(self.crop_rect_id)
            self.crop_rect_id = None
        self._clear_crop_handles()

        self.canvas.delete("all")
        self.root.title("Image Viewer")
        self.status.config(text="Open an image to get started")
        self._initial_message()

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.root.attributes("-fullscreen", self.fullscreen)

        if self.fullscreen:
            self.toolbar.pack_forget()
            self.status.pack_forget()
        else:
            self.toolbar.pack(side=tk.TOP, fill=tk.X)
            self.status.pack(side=tk.BOTTOM, fill=tk.X)

        if self.original_image is not None or self.collage_mode:
            self.root.after(100, self.display_current_image)

    def exit_fullscreen(self):
        if self.fullscreen:
            self.fullscreen = False
            self.root.attributes("-fullscreen", False)
            self.toolbar.pack(side=tk.TOP, fill=tk.X)
            self.status.pack(side=tk.BOTTOM, fill=tk.X)

            if self.original_image is not None or self.collage_mode:
                self.root.after(100, self.display_current_image)
