import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from PIL import Image, ImageOps


class ViewerCropMixin:

    def begin_crop(self):
        if self.original_image is None:
            return

        self._stop_animation()
        if self.image_layout_mode:
            self.image_layout_mode = False
            self.image_layout_drag_action = None
            self._set_image_layout_controls()
        self.crop_mode = True
        self.crop_drag_action = None
        for button in (
            self.toolbar_buttons + self.collage_buttons + self.image_layout_buttons
        ):
            button.configure(state=tk.DISABLED)
        self.canvas.configure(cursor="crosshair")
        self.apply_crop_button.pack_forget()
        self.cancel_crop_button.pack_forget()
        if self.crop_rect_id is not None:
            self.canvas.delete(self.crop_rect_id)
            self.crop_rect_id = None
        self._clear_crop_handles()
        self.status.config(
            text="Drag to select; move the sides or corner handles to adjust"
        )

    def _handle_canvas_press(self, event):
        if self.collage_mode:
            self._collage_press(event)
            return
        if self.image_layout_mode:
            self._image_layout_press(event)
            return
        if self.crop_mode:
            self._start_crop_selection(event)
            return

        self._start_drag(event)

    def _handle_canvas_drag(self, event):
        if self.collage_mode:
            self._collage_drag(event)
            return
        if self.image_layout_mode:
            self._image_layout_drag(event)
            return
        if self.crop_mode:
            self._update_crop_selection(event)
            return

        self._drag_image(event)

    def _handle_canvas_release(self, event):
        if self.collage_mode:
            self._collage_release(event)
            return
        if self.image_layout_mode:
            self._image_layout_release(event)
            return
        if self.crop_mode:
            self._finish_crop_selection(event)
            return

        self._stop_drag(event)

    def _crop_image_bounds(self):
        if self.display_image is None:
            return 0, 0, 0, 0

        left = (
            self.canvas.winfo_width() // 2
            + self.pan_x
            - self.display_image.width / 2
        )
        top = (
            self.canvas.winfo_height() // 2
            + self.pan_y
            - self.display_image.height / 2
        )
        return (
            left,
            top,
            left + self.display_image.width,
            top + self.display_image.height
        )

    def _crop_point_in_image(self, event):
        left, top, right, bottom = self._crop_image_bounds()
        return (
            min(max(event.x, left), right),
            min(max(event.y, top), bottom)
        )

    def _start_crop_selection(self, event):
        if self.original_image is None or self.display_image is None:
            return

        x, y = self._crop_point_in_image(event)
        self.crop_start_x = x
        self.crop_start_y = y

        if self.crop_rect_id is None:
            self.crop_drag_action = "new"
            self.crop_initial_coords = (x, y, x, y)
            self.crop_rect_id = self.canvas.create_rectangle(
                x, y, x, y,
                outline="#7ad7ff",
                width=2,
                dash=(4, 4)
            )
            return

        x1, y1, x2, y2 = self.canvas.coords(self.crop_rect_id)
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        edge = 14
        near_left = (
            abs(x - x1) <= edge and y1 - edge <= y <= y2 + edge
        )
        near_right = (
            abs(x - x2) <= edge and y1 - edge <= y <= y2 + edge
        )
        near_top = (
            abs(y - y1) <= edge and x1 - edge <= x <= x2 + edge
        )
        near_bottom = (
            abs(y - y2) <= edge and x1 - edge <= x <= x2 + edge
        )
        inside = x1 <= x <= x2 and y1 <= y <= y2

        if near_left or near_right or near_top or near_bottom:
            self.crop_drag_action = (
                ("w" if near_left else "e" if near_right else "")
                + ("n" if near_top else "s" if near_bottom else "")
            )
        elif inside:
            self.crop_drag_action = "move"
        else:
            self.crop_drag_action = "new"

        if self.crop_drag_action == "new":
            self.crop_initial_coords = (x, y, x, y)
        else:
            self.crop_initial_coords = (x1, y1, x2, y2)

    def _update_crop_selection(self, event):
        if self.crop_rect_id is None or self.crop_drag_action is None:
            return

        x, y = self._crop_point_in_image(event)
        x1, y1, x2, y2 = self.crop_initial_coords

        if self.crop_drag_action == "new":
            coords = (self.crop_start_x, self.crop_start_y, x, y)
        elif self.crop_drag_action == "move":
            dx = x - self.crop_start_x
            dy = y - self.crop_start_y
            left, top, right, bottom = self._crop_image_bounds()
            dx = min(max(dx, left - x1), right - x2)
            dy = min(max(dy, top - y1), bottom - y2)
            coords = (x1 + dx, y1 + dy, x2 + dx, y2 + dy)
        else:
            left, top, right, bottom = self._crop_image_bounds()
            if "w" in self.crop_drag_action:
                x1 = min(x, x2 - 4)
            if "e" in self.crop_drag_action:
                x2 = max(x, x1 + 4)
            if "n" in self.crop_drag_action:
                y1 = min(y, y2 - 4)
            if "s" in self.crop_drag_action:
                y2 = max(y, y1 + 4)
            coords = (
                max(left, x1),
                max(top, y1),
                min(right, x2),
                min(bottom, y2)
            )

        self.canvas.coords(self.crop_rect_id, *coords)
        self._draw_crop_handles()

    def _clear_crop_handles(self):
        for handle_id in self.crop_handle_ids:
            self.canvas.delete(handle_id)
        self.crop_handle_ids.clear()

    def _draw_crop_handles(self):
        if self.crop_rect_id is None:
            return

        self._clear_crop_handles()
        x1, y1, x2, y2 = self.canvas.coords(self.crop_rect_id)
        handle_size = 5
        for x, y in (
            ((x1 + x2) / 2, y1),
            (x2, (y1 + y2) / 2),
            ((x1 + x2) / 2, y2),
            (x1, (y1 + y2) / 2),
            (x1, y1),
            (x2, y1),
            (x2, y2),
            (x1, y2)
        ):
            self.crop_handle_ids.append(self.canvas.create_rectangle(
                x - handle_size,
                y - handle_size,
                x + handle_size,
                y + handle_size,
                fill="#7ad7ff",
                outline="#202020",
                width=1
            ))

    def _finish_crop_selection(self, event):
        self.crop_drag_action = None
        if self.crop_rect_id is None or self.original_image is None:
            return

        x1, y1, x2, y2 = self.canvas.coords(self.crop_rect_id)
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))

        if x2 - x1 < 4 or y2 - y1 < 4:
            self.apply_crop_button.pack_forget()
            self.cancel_crop_button.pack_forget()
            self.status.config(text="Drag a larger area to select the crop")
            return

        self.apply_crop_button.pack(side=tk.LEFT, padx=2)
        self.cancel_crop_button.pack(side=tk.LEFT, padx=2)
        self._draw_crop_handles()
        self.canvas.configure(cursor="fleur")
        self.status.config(
            text=(
                "Drag a side or handle to resize, inside to move; "
                "choose Apply Crop or Cancel Crop when satisfied"
            )
        )

    def cancel_crop(self):
        self.crop_mode = False
        self.crop_drag_action = None
        self.crop_initial_coords = None
        if self.crop_rect_id is not None:
            self.canvas.delete(self.crop_rect_id)
            self.crop_rect_id = None
        self._clear_crop_handles()
        self.apply_crop_button.pack_forget()
        self.cancel_crop_button.pack_forget()
        for button in (
            self.toolbar_buttons + self.collage_buttons + self.image_layout_buttons
        ):
            button.configure(state=tk.NORMAL)
        self.canvas.configure(cursor="")
        self._update_status()
        self._schedule_animation_frame()

    def apply_crop(self):
        if (
            not self.crop_mode
            or self.crop_rect_id is None
            or self.original_image is None
            or self.display_image is None
        ):
            return

        x1, y1, x2, y2 = self.canvas.coords(self.crop_rect_id)
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        left, top, _, _ = self._crop_image_bounds()
        crop_left = max(0, x1 - left)
        crop_top = max(0, y1 - top)
        crop_right = min(self.display_image.width, x2 - left)
        crop_bottom = min(self.display_image.height, y2 - top)
        if crop_right - crop_left < 4 or crop_bottom - crop_top < 4:
            self.status.config(text="Crop area is too small")
            return

        self._record_history()
        rotated_image = self.original_image.rotate(
            self.rotation,
            expand=True,
            resample=Image.Resampling.BICUBIC
        )
        scale_x = self.display_image.width / rotated_image.width
        scale_y = self.display_image.height / rotated_image.height
        cropped = rotated_image.crop((
            int(crop_left / scale_x),
            int(crop_top / scale_y),
            int(crop_right / scale_x),
            int(crop_bottom / scale_y)
        ))

        self.crop_mode = False
        self._clear_animation()
        self.crop_drag_action = None
        self.crop_initial_coords = None
        self.canvas.delete(self.crop_rect_id)
        self.crop_rect_id = None
        self._clear_crop_handles()
        self.apply_crop_button.pack_forget()
        self.cancel_crop_button.pack_forget()
        for button in (
            self.toolbar_buttons + self.collage_buttons + self.image_layout_buttons
        ):
            button.configure(state=tk.NORMAL)
        self.canvas.configure(cursor="")
        self.original_image = cropped.convert("RGBA")
        self.rotation = 0
        self.zoom = 1.0
        self.fit_mode = True
        self.pan_x = 0
        self.pan_y = 0
        self.display_current_image()
        self.save_cropped_image()

    def save_cropped_image(self):
        if self.original_image is None:
            return

        initial_name = (
            f"{self.image_path.stem}_cropped.png"
            if self.image_path else "cropped.png"
        )
        filename = filedialog.asksaveasfilename(
            title="Save Cropped Image",
            initialfile=initial_name,
            defaultextension=".png",
            filetypes=[
                ("PNG image", "*.png"),
                ("JPEG image", "*.jpg *.jpeg"),
                ("WebP image", "*.webp"),
                ("TIFF image", "*.tif *.tiff"),
                ("BMP image", "*.bmp"),
                ("All files", "*.*")
            ]
        )
        if not filename:
            self.status.config(text="Crop applied; saving cancelled")
            return

        path = Path(filename)
        try:
            image = self.original_image
            if path.suffix.lower() in {".jpg", ".jpeg", ".bmp"}:
                image = image.convert("RGB")
            image.save(path)
        except (OSError, ValueError) as error:
            messagebox.showerror(
                "Unable to Save Cropped Image",
                f"Could not save this image:\n\n{error}"
            )
            return

        self.status.config(text=f"Saved cropped image: {path.name}")
