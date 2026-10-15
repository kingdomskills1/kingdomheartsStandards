from pathlib import Path
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk


class ViewerLayoutMixin:
    def _rotated_source_image(self):
        return self.original_image.rotate(
            self.rotation,
            expand=True,
            resample=Image.Resampling.BICUBIC
        )

    def begin_image_layout(self):
        if self.original_image is None or self.collage_mode:
            return

        if self.image_layout_mode:
            self.image_layout_mode = False
            self.image_layout_drag_action = None
            self._set_image_layout_controls()
            self.canvas.configure(cursor="")
            self.display_current_image()
            return

        if self.crop_mode:
            self.cancel_crop()

        rotated = self._rotated_source_image()
        self.image_layout_canvas_width = max(
            self.root.winfo_screenwidth(),
            rotated.width
        )
        self.image_layout_canvas_height = max(
            self.root.winfo_screenheight(),
            rotated.height
        )
        self.image_layout_x = (
            self.image_layout_canvas_width - rotated.width
        ) / 2
        self.image_layout_y = (
            self.image_layout_canvas_height - rotated.height
        ) / 2
        self.image_layout_width = rotated.width
        self.image_layout_height = rotated.height
        self.image_layout_mode = True
        self.image_layout_drag_action = None
        self._set_image_layout_controls()
        self.canvas.configure(cursor="crosshair")
        self.display_current_image()

    def fit_image_to_screen(self):
        if self.original_image is None or self.collage_mode:
            return

        rotated = self._rotated_source_image()
        self.image_layout_canvas_width = max(1, self.root.winfo_screenwidth())
        self.image_layout_canvas_height = max(1, self.root.winfo_screenheight())
        margin = 24
        scale = min(
            (self.image_layout_canvas_width - 2 * margin) / rotated.width,
            (self.image_layout_canvas_height - 2 * margin) / rotated.height
        )
        self.image_layout_width = max(1, round(rotated.width * scale))
        self.image_layout_height = max(1, round(rotated.height * scale))
        self.image_layout_x = (
            self.image_layout_canvas_width - self.image_layout_width
        ) / 2
        self.image_layout_y = (
            self.image_layout_canvas_height - self.image_layout_height
        ) / 2
        self.image_layout_mode = True
        self.image_layout_drag_action = None
        self._set_image_layout_controls()
        self.canvas.configure(cursor="crosshair")
        self.display_current_image()
        self.status.config(
            text=(
                f"Screen-sized canvas: {self.image_layout_canvas_width} × "
                f"{self.image_layout_canvas_height} px; image fitted without "
                "stretching. Save Image when ready."
            )
        )

    def _set_image_layout_controls(self):
        for button in self.toolbar_buttons:
            button.configure(state="disabled" if self.image_layout_mode else "normal")
        for button in self.image_layout_buttons:
            button.configure(state="normal")

    def _image_layout_view(self):
        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        scale = max(
            0.001,
            min(
                1.0,
                max(1, canvas_width - 40) / self.image_layout_canvas_width,
                max(1, canvas_height - 40) / self.image_layout_canvas_height
            )
        )
        return (
            scale,
            (canvas_width - self.image_layout_canvas_width * scale) / 2,
            (canvas_height - self.image_layout_canvas_height * scale) / 2
        )

    def _render_image_layout(self):
        if self.original_image is None:
            return

        self.canvas.delete("all")
        source = self._rotated_source_image()
        scale, offset_x, offset_y = self._image_layout_view()
        self.image_layout_view_scale = max(0.001, scale)
        self.image_layout_view_offset_x = offset_x
        self.image_layout_view_offset_y = offset_y

        preview_size = (
            max(1, round(self.image_layout_width * scale)),
            max(1, round(self.image_layout_height * scale))
        )
        preview = source.resize(preview_size, Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(preview)
        x1 = offset_x + self.image_layout_x * scale
        y1 = offset_y + self.image_layout_y * scale
        x2 = x1 + preview.width
        y2 = y1 + preview.height
        self.canvas.create_image(x1, y1, image=self.photo, anchor="nw")
        self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline="#7ad7ff",
            width=2,
            dash=(4, 4)
        )

        handle_size = 5
        for handle_x, handle_y in (
            ((x1 + x2) / 2, y1),
            (x2, (y1 + y2) / 2),
            ((x1 + x2) / 2, y2),
            (x1, (y1 + y2) / 2),
            (x1, y1), (x2, y1), (x2, y2), (x1, y2)
        ):
            self.canvas.create_rectangle(
                handle_x - handle_size,
                handle_y - handle_size,
                handle_x + handle_size,
                handle_y + handle_size,
                fill="#7ad7ff",
                outline="#202020"
            )

        self.status.config(
            text=(
                f"Layout {self.image_layout_canvas_width} × "
                f"{self.image_layout_canvas_height} px | "
                "Drag the image to move it; drag an edge or handle to resize"
            )
        )

    def _image_layout_point(self, event):
        return (
            (event.x - self.image_layout_view_offset_x)
            / self.image_layout_view_scale,
            (event.y - self.image_layout_view_offset_y)
            / self.image_layout_view_scale
        )

    def _image_layout_press(self, event):
        x, y = self._image_layout_point(event)
        self.image_layout_drag_start = (x, y)
        x1 = self.image_layout_x
        y1 = self.image_layout_y
        x2 = x1 + self.image_layout_width
        y2 = y1 + self.image_layout_height
        tolerance = 12 / self.image_layout_view_scale
        near_left = abs(x - x1) <= tolerance and y1 - tolerance <= y <= y2 + tolerance
        near_right = abs(x - x2) <= tolerance and y1 - tolerance <= y <= y2 + tolerance
        near_top = abs(y - y1) <= tolerance and x1 - tolerance <= x <= x2 + tolerance
        near_bottom = abs(y - y2) <= tolerance and x1 - tolerance <= x <= x2 + tolerance

        if near_left or near_right or near_top or near_bottom:
            self.image_layout_drag_action = (
                ("w" if near_left else "e" if near_right else "")
                + ("n" if near_top else "s" if near_bottom else "")
            )
        elif x1 <= x <= x2 and y1 <= y <= y2:
            self.image_layout_drag_action = "move"
        else:
            self.image_layout_drag_action = None
            return

        self.image_layout_initial_bounds = (
            self.image_layout_x,
            self.image_layout_y,
            self.image_layout_width,
            self.image_layout_height
        )

    def _image_layout_drag(self, event):
        if self.image_layout_drag_action is None:
            return

        x, y = self._image_layout_point(event)
        start_x, start_y = self.image_layout_drag_start
        x0, y0, width, height = self.image_layout_initial_bounds
        right = x0 + width
        bottom = y0 + height
        minimum_size = 20

        if self.image_layout_drag_action == "move":
            self.image_layout_x = min(
                max(0, x0 + x - start_x),
                max(0, self.image_layout_canvas_width - width)
            )
            self.image_layout_y = min(
                max(0, y0 + y - start_y),
                max(0, self.image_layout_canvas_height - height)
            )
        else:
            if "w" in self.image_layout_drag_action:
                new_left = min(max(0, x), right - minimum_size)
                self.image_layout_x = new_left
                self.image_layout_width = right - new_left
            elif "e" in self.image_layout_drag_action:
                self.image_layout_width = min(
                    max(minimum_size, x - x0),
                    self.image_layout_canvas_width - x0
                )
            if "n" in self.image_layout_drag_action:
                new_top = min(max(0, y), bottom - minimum_size)
                self.image_layout_y = new_top
                self.image_layout_height = bottom - new_top
            elif "s" in self.image_layout_drag_action:
                self.image_layout_height = min(
                    max(minimum_size, y - y0),
                    self.image_layout_canvas_height - y0
                )

        self._render_image_layout()

    def _image_layout_release(self, event):
        self.image_layout_drag_action = None
        self.image_layout_initial_bounds = None

    def save_image(self):
        if self.original_image is None:
            return

        initial_name = (
            f"{self.image_path.stem}_edited.png"
            if self.image_path else "edited.png"
        )
        filename = filedialog.asksaveasfilename(
            title="Save Edited Image",
            initialfile=initial_name,
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")]
        )
        if not filename:
            return

        try:
            if self.image_layout_mode:
                output = Image.new(
                    "RGBA",
                    (
                        self.image_layout_canvas_width,
                        self.image_layout_canvas_height
                    ),
                    (0, 0, 0, 0)
                )
                resized = self._rotated_source_image().resize(
                    (
                        max(1, round(self.image_layout_width)),
                        max(1, round(self.image_layout_height))
                    ),
                    Image.Resampling.LANCZOS
                )
                output.alpha_composite(
                    resized,
                    (
                        round(self.image_layout_x),
                        round(self.image_layout_y)
                    )
                )
            else:
                output = self._rotated_source_image()

            output.save(Path(filename), format="PNG")
        except (OSError, ValueError, MemoryError) as error:
            messagebox.showerror(
                "Unable to Save Image",
                f"Could not save this image:\n\n{error}"
            )
            return

        self.status.config(text=f"Saved image: {Path(filename).name}")
