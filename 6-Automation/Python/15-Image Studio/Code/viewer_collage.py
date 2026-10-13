import tkinter as tk
from math import ceil
from pathlib import Path
from tkinter import filedialog, messagebox
from PIL import Image, ImageOps, ImageTk


class ViewerCollageMixin:

    def create_collage(self):
        filenames = filedialog.askopenfilenames(
            title="Select Images for Collage",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp *.gif "
                 "*.tif *.tiff *.webp *.ico"),
                ("All files", "*.*")
            ]
        )
        if not filenames:
            return

        self._add_collage_files(filenames, replace=True)

    def add_collage_images(self):
        if not self.collage_mode:
            messagebox.showinfo(
                "Create a Collage First",
                "Choose Create Collage before adding images."
            )
            return

        filenames = filedialog.askopenfilenames(
            title="Add Images to Collage",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp *.gif "
                 "*.tif *.tiff *.webp *.ico"),
                ("All files", "*.*")
            ]
        )
        if filenames:
            self._add_collage_files(filenames)

    def _add_collage_files(self, filenames, replace=False):
        errors = []
        new_items = []
        existing_items = [] if replace else self.collage_items
        for filename in filenames:
            path = Path(filename)
            try:
                with Image.open(path) as opened_image:
                    image = ImageOps.exif_transpose(opened_image).convert("RGBA")
            except (OSError, ValueError, Image.DecompressionBombError) as error:
                errors.append(f"{path.name}: {error}")
                continue

            right_edge = max(
                (
                    item["x"] + item["width"]
                    for item in existing_items + new_items
                ),
                default=24
            )
            new_items.append({
                "image": image.copy(),
                "path": path,
                "x": right_edge + (24 if existing_items or new_items else 0),
                "y": 24,
                "width": image.width,
                "height": image.height,
            })

        if not new_items:
            if errors:
                messagebox.showwarning(
                    "No Images Could Be Added",
                    "No selected images could be added:\n\n"
                    + "\n".join(errors)
                )
            return

        if replace:
            self.collage_items = []
            self.collage_selected_index = None
            self.collage_canvas_width = max(1, self.canvas.winfo_width())
            self.collage_canvas_height = max(1, self.canvas.winfo_height())
            self.original_image = None
            self.image_layout_mode = False
            self.image_layout_drag_action = None
            self.image_path = None
            self.folder_images = []
            self.undo_stack.clear()
            self.redo_stack.clear()
            for button in self.toolbar_buttons:
                button.configure(state="normal")
        self.collage_items.extend(new_items)
        self.collage_mode = True
        self._layout_collage_tiles()
        self.display_current_image()

        if errors and new_items:
            messagebox.showwarning(
                "Some Images Could Not Be Opened",
                "These files could not be added:\n\n" + "\n".join(errors)
            )

    def _layout_collage_tiles(self):
        count = len(self.collage_items)
        if not count:
            return

        for index, item in enumerate(self.collage_items):
            left = index * self.collage_canvas_width // count
            right = (index + 1) * self.collage_canvas_width // count
            item["x"] = left
            item["y"] = 0
            item["width"] = right - left
            item["height"] = self.collage_canvas_height

    def _collage_document_size(self):
        return (
            max(1, self.collage_canvas_width),
            max(1, self.collage_canvas_height)
        )

    def _fit_collage_tile(self, item):
        tile_size = (
            max(1, round(item["width"])),
            max(1, round(item["height"]))
        )
        tile = Image.new("RGBA", tile_size, (32, 32, 32, 255))
        image = ImageOps.contain(
            item["image"],
            tile_size,
            method=Image.Resampling.LANCZOS
        )
        tile.alpha_composite(
            image,
            (
                (tile.width - image.width) // 2,
                (tile.height - image.height) // 2
            )
        )
        return tile

    def _render_collage(self):
        self.canvas.delete("all")
        self.collage_photos = []
        if not self.collage_items:
            return

        document_width, document_height = self._collage_document_size()
        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        if self.collage_drag_action is None:
            self.collage_view_scale = min(
                1.0,
                canvas_width / document_width,
                canvas_height / document_height
            )
            self.collage_view_scale = max(0.001, self.collage_view_scale)
            self.collage_view_offset_x = (
                canvas_width - document_width * self.collage_view_scale
            ) / 2
            self.collage_view_offset_y = (
                canvas_height - document_height * self.collage_view_scale
            ) / 2

        for item in self.collage_items:
            tile = self._fit_collage_tile(item)
            preview = tile.resize(
                (
                    max(1, round(tile.width * self.collage_view_scale)),
                    max(1, round(tile.height * self.collage_view_scale))
                ),
                Image.Resampling.LANCZOS
            )
            photo = ImageTk.PhotoImage(preview)
            self.collage_photos.append(photo)
            self.canvas.create_image(
                self.collage_view_offset_x + item["x"] * self.collage_view_scale,
                self.collage_view_offset_y + item["y"] * self.collage_view_scale,
                image=photo,
                anchor=tk.NW
            )

        if self.collage_selected_index is not None:
            item = self.collage_items[self.collage_selected_index]
            x1 = self.collage_view_offset_x + item["x"] * self.collage_view_scale
            y1 = self.collage_view_offset_y + item["y"] * self.collage_view_scale
            x2 = x1 + item["width"] * self.collage_view_scale
            y2 = y1 + item["height"] * self.collage_view_scale
            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                outline="#7ad7ff",
                width=2,
                dash=(4, 4)
            )
            handle_size = 5
            for x, y in (
                ((x1 + x2) / 2, y1), (x2, (y1 + y2) / 2),
                ((x1 + x2) / 2, y2), (x1, (y1 + y2) / 2),
                (x1, y1), (x2, y1), (x2, y2), (x1, y2)
            ):
                self.canvas.create_rectangle(
                    x - handle_size, y - handle_size,
                    x + handle_size, y + handle_size,
                    fill="#7ad7ff",
                    outline="#202020"
                )

        self.status.config(
            text=(
                f"Collage: {len(self.collage_items)} images | "
                "Drag an image to move it; drag its sides or handles to resize"
            )
        )
        self.root.title("Collage - Image Viewer")

    def _collage_point(self, event):
        return (
            (event.x - self.collage_view_offset_x) / self.collage_view_scale,
            (event.y - self.collage_view_offset_y) / self.collage_view_scale
        )

    def _collage_press(self, event):
        x, y = self._collage_point(event)
        self.collage_drag_start = (x, y)
        self.collage_drag_action = None
        selected = self.collage_selected_index

        if selected is not None:
            item = self.collage_items[selected]
            tolerance = 12 / self.collage_view_scale
            x1, y1 = item["x"], item["y"]
            x2, y2 = x1 + item["width"], y1 + item["height"]
            near_left = abs(x - x1) <= tolerance and y1 - tolerance <= y <= y2 + tolerance
            near_right = abs(x - x2) <= tolerance and y1 - tolerance <= y <= y2 + tolerance
            near_top = abs(y - y1) <= tolerance and x1 - tolerance <= x <= x2 + tolerance
            near_bottom = abs(y - y2) <= tolerance and x1 - tolerance <= x <= x2 + tolerance
            if near_left or near_right or near_top or near_bottom:
                self.collage_drag_action = (
                    ("w" if near_left else "e" if near_right else "")
                    + ("n" if near_top else "s" if near_bottom else "")
                )
                self.collage_initial_bounds = (
                    item["x"], item["y"], item["width"], item["height"]
                )
                return

        self.collage_selected_index = None
        for index in range(len(self.collage_items) - 1, -1, -1):
            item = self.collage_items[index]
            if (
                item["x"] <= x <= item["x"] + item["width"]
                and item["y"] <= y <= item["y"] + item["height"]
            ):
                self.collage_selected_index = index
                self.collage_drag_action = "move"
                self.collage_initial_bounds = (
                    item["x"], item["y"], item["width"], item["height"]
                )
                break
        self._render_collage()

    def _collage_drag(self, event):
        if self.collage_drag_action is None or self.collage_selected_index is None:
            return

        x, y = self._collage_point(event)
        start_x, start_y = self.collage_drag_start
        item = self.collage_items[self.collage_selected_index]
        x0, y0, width, height = self.collage_initial_bounds
        min_size = 20

        if self.collage_drag_action == "move":
            item["x"] = min(
                max(0, x0 + x - start_x),
                max(0, self.collage_canvas_width - width)
            )
            item["y"] = min(
                max(0, y0 + y - start_y),
                max(0, self.collage_canvas_height - height)
            )
        else:
            right = x0 + width
            bottom = y0 + height
            if "w" in self.collage_drag_action:
                new_left = max(0, min(x, right - min_size))
                item["x"] = new_left
                item["width"] = right - new_left
            elif "e" in self.collage_drag_action:
                item["width"] = min(
                    max(min_size, x - x0),
                    self.collage_canvas_width - x0
                )
            if "n" in self.collage_drag_action:
                new_top = max(0, min(y, bottom - min_size))
                item["y"] = new_top
                item["height"] = bottom - new_top
            elif "s" in self.collage_drag_action:
                item["height"] = min(
                    max(min_size, y - y0),
                    self.collage_canvas_height - y0
                )

        self._render_collage()

    def _collage_release(self, event):
        self.collage_drag_action = None
        self.collage_initial_bounds = None
        self._render_collage()

    def save_collage(self):
        if not self.collage_mode or not self.collage_items:
            messagebox.showinfo(
                "No Collage to Save",
                "Create a collage and add images before saving."
            )
            return

        filename = filedialog.asksaveasfilename(
            title="Save Collage",
            initialfile="collage.png",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")]
        )
        if not filename:
            return

        path = Path(filename)
        try:
            width, height = self._collage_document_size()
            composition = Image.new(
                "RGBA", (ceil(width), ceil(height)), (0, 0, 0, 0)
            )
            for item in self.collage_items:
                image = self._fit_collage_tile(item)
                composition.alpha_composite(
                    image,
                    (round(item["x"]), round(item["y"]))
                )
            composition.save(path, format="PNG")
        except (OSError, ValueError, MemoryError) as error:
            messagebox.showerror(
                "Unable to Save Collage",
                f"Could not save this collage:\n\n{error}"
            )
            return

        self.status.config(text=f"Saved collage: {path.name}")
