import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from recent_files import add_recent_file, load_recent_files
from windows_registration import (
    open_default_apps_settings,
    register_default_app,
)


class ViewerUIMixin:

    def _load_recent_files(self):
        try:
            return load_recent_files()
        except (OSError, ValueError) as error:
            messagebox.showerror(
                "Unable to Load Recent Files",
                f"Could not load the recent files list:\n\n{error}",
            )
            return []

    def _record_recent_file(self, filename):
        try:
            self.recent_files = add_recent_file(
                self.recent_files,
                filename,
            )
        except OSError as error:
            messagebox.showerror(
                "Unable to Save Recent Files",
                f"The image opened, but the recent files list "
                f"could not be saved:\n\n{error}",
            )
        self._refresh_recent_files_menu()

    def _open_recent_file(self, filename):
        self.load_image(filename)

    def _show_recent_files_menu(self, event=None):
        if self.recent_menu_close_after_id is not None:
            self.root.after_cancel(self.recent_menu_close_after_id)
            self.recent_menu_close_after_id = None

        if not self.recent_files_menu.winfo_ismapped():
            self.recent_files_menu.post(
                self.recent_files_button.winfo_rootx(),
                self.recent_files_button.winfo_rooty()
                + self.recent_files_button.winfo_height(),
            )

    def _schedule_recent_files_menu_close(self, event=None):
        if self.recent_menu_close_after_id is None:
            self.recent_menu_close_after_id = self.root.after(
                250,
                self._close_recent_files_menu,
            )

    def _close_recent_files_menu(self):
        self.recent_menu_close_after_id = None
        self.recent_files_menu.unpost()

    def _refresh_recent_files_menu(self):
        self.recent_files_menu.delete(0, tk.END)
        if not self.recent_files:
            self.recent_files_menu.add_command(
                label="No recent files",
                state=tk.DISABLED,
            )
            return

        for filename in self.recent_files:
            path = Path(filename)
            self.recent_files_menu.add_command(
                label=f"{path.name} ({path.parent})",
                command=lambda selected=filename: self._open_recent_file(
                    selected
                ),
            )

    def register_windows_default_app(self):
        try:
            register_default_app(
                Path(__file__).with_name("main.py"),
                self.SUPPORTED_FORMATS,
            )
        except (OSError, RuntimeError) as error:
            messagebox.showerror(
                "Windows Registration Failed",
                f"Could not register Image Viewer with Windows:\n\n{error}",
            )
            return

        try:
            open_default_apps_settings()
        except OSError as error:
            messagebox.showerror(
                "Could Not Open Default Apps",
                "Image Viewer is registered with Windows, but Default apps "
                f"settings could not be opened:\n\n{error}",
            )
            return

        messagebox.showinfo(
            "Choose Image Viewer",
            "Image Viewer is now listed in Windows Default apps.\n\n"
            "Choose it for each image file type you want to open with this app.",
        )

    def _build_interface(self):
        # Toolbar
        self.toolbar = tk.Frame(self.root, bg="#303030", padx=8, pady=8)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)
        self.toolbar_controls = tk.Frame(self.toolbar, bg="#303030")
        self.toolbar_controls.pack(side=tk.TOP, fill=tk.X)
        self.collage_toolbar = tk.Frame(self.toolbar, bg="#303030")
        self.collage_toolbar.pack(side=tk.TOP, fill=tk.X)
        self.recent_files_menu = tk.Menu(
            self.root,
            tearoff=False,
            bg="#454545",
            fg="white",
            activebackground="#606060",
            activeforeground="white",
        )
        self.recent_files_button = tk.Menubutton(
            self.toolbar_controls,
            text="Recent Files",
            menu=self.recent_files_menu,
            bg="#454545",
            fg="white",
            activebackground="#606060",
            activeforeground="white",
            relief=tk.FLAT,
            padx=8,
            pady=5,
            cursor="hand2",
        )
        self.recent_files_button.pack(side=tk.LEFT, padx=2)
        self.recent_menu_close_after_id = None
        self.recent_files_button.bind(
            "<Enter>", self._show_recent_files_menu
        )
        self.recent_files_button.bind(
            "<Leave>", self._schedule_recent_files_menu_close
        )
        self.recent_files_menu.bind(
            "<Enter>", self._show_recent_files_menu
        )
        self.recent_files_menu.bind(
            "<Leave>", self._schedule_recent_files_menu_close
        )
        self._refresh_recent_files_menu()

        buttons = [
            ("Open", self.open_image),
            ("Move / Resize", self.begin_image_layout),
            ("Full Screen Size", self.fit_image_to_screen),
            ("Save Image", self.save_image),
            ("Create Collage", self.create_collage),
            ("Add Images", self.add_collage_images),
            ("Save Collage", self.save_collage),
            ("Register with Windows", self.register_windows_default_app),
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
                if label in {
                    "Create Collage",
                    "Add Images",
                    "Save Collage",
                    "Register with Windows",
                }
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
            elif label == "Register with Windows":
                continue
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
        self.root.bind("<Control-c>", lambda event: self.copy_current_file())
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
        self.root.bind("<KeyPress-f>", lambda event: self.toggle_fullscreen())
        self.root.bind("<KeyPress-F>", lambda event: self.toggle_fullscreen())
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
        self._clear_animation()
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
