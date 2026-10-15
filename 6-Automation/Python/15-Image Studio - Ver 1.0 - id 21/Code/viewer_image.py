import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from PIL import Image, ImageOps, ImageTk


class ViewerImageMixin:

    def open_image(self):
        filename = filedialog.askopenfilename(
            title="Select an Image",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp *.gif "
                 "*.tif *.tiff *.webp *.ico"),
                ("All files", "*.*")
            ]
        )

        if filename:
            self.load_image(filename)

    def load_image(self, filename):
        try:
            path = Path(filename)
            animation_frames = []
            animation_durations = []
            animation_frame_count = 0

            with Image.open(path) as image:
                if image.format == "GIF" and image.n_frames > 1:
                    image.seek(0)
                    loaded_image = (
                        ImageOps.exif_transpose(image).convert("RGBA").copy()
                    )
                    animation_frames.append(loaded_image)
                    animation_durations.append(
                        self._animation_frame_duration(image)
                    )
                    animation_frame_count = image.n_frames
                else:
                    image = ImageOps.exif_transpose(image)
                    image.seek(0)
                    loaded_image = image.convert("RGBA").copy()

            self._clear_animation()
            self.image_path = path
            self.original_image = loaded_image
            self.animation_frames = animation_frames
            self.animation_durations = animation_durations
            self.animation_index = 0
            self.animation_load_complete = animation_frame_count < 2
            self.image_layout_mode = False
            self.image_layout_drag_action = None
            self.collage_mode = False
            self.collage_items = []
            self.collage_selected_index = None
            self.collage_drag_action = None
            self.collage_photos = []
            self.rotation = 0
            self.zoom = 1.0
            self.fit_mode = True
            self.pan_x = 0
            self.pan_y = 0
            self.crop_mode = False
            self.canvas.configure(cursor="")
            if self.crop_rect_id is not None:
                self.canvas.delete(self.crop_rect_id)
                self.crop_rect_id = None
            self.apply_crop_button.pack_forget()
            self.cancel_crop_button.pack_forget()
            for button in (
                self.toolbar_buttons
                + self.collage_buttons
                + self.image_layout_buttons
            ):
                button.configure(state=tk.NORMAL)
            self.undo_stack.clear()
            self.redo_stack.clear()

            self._load_folder_images()
            self.display_current_image()
            if animation_frame_count > 1:
                self._start_animation_loading(path, animation_frame_count)
            self._record_recent_file(path)

        except Exception as error:
            messagebox.showerror(
                "Unable to Open Image",
                f"Could not open this image:\n\n{error}"
            )

    @staticmethod
    def _animation_frame_duration(image):
        duration = image.info.get("duration", 100)
        return max(20, int(100 if duration is None else duration))

    def _start_animation_loading(self, path, frame_count):
        frame_queue = queue.Queue(maxsize=4)
        cancelled = threading.Event()
        self.animation_frame_queue = frame_queue
        self.animation_load_cancelled = cancelled
        generation = self.animation_generation

        worker = threading.Thread(
            target=self._decode_animation_frames,
            args=(path, frame_count, frame_queue, cancelled),
            daemon=True,
        )
        worker.start()
        self.animation_load_after_id = self.root.after(
            15,
            self._poll_animation_frames,
            generation,
        )

    def _decode_animation_frames(
        self,
        path,
        frame_count,
        frame_queue,
        cancelled,
    ):
        try:
            with Image.open(path) as image:
                for frame_index in range(1, frame_count):
                    if cancelled.is_set():
                        return

                    image.seek(frame_index)
                    frame = (
                        ImageOps.exif_transpose(image).convert("RGBA").copy()
                    )
                    message = (
                        "frame",
                        frame,
                        self._animation_frame_duration(image),
                    )
                    while not cancelled.is_set():
                        try:
                            frame_queue.put(message, timeout=0.1)
                            break
                        except queue.Full:
                            continue
                    else:
                        return
        except Exception as error:
            self._put_animation_load_message(
                frame_queue,
                cancelled,
                ("error", error, None),
            )
            return

        self._put_animation_load_message(
            frame_queue,
            cancelled,
            ("done", None, None),
        )

    @staticmethod
    def _put_animation_load_message(frame_queue, cancelled, message):
        while not cancelled.is_set():
            try:
                frame_queue.put(message, timeout=0.1)
                return
            except queue.Full:
                continue

    def _poll_animation_frames(self, generation):
        self.animation_load_after_id = None
        if generation != self.animation_generation:
            return

        while True:
            try:
                message_type, value, duration = (
                    self.animation_frame_queue.get_nowait()
                )
            except queue.Empty:
                break

            if message_type == "frame":
                self.animation_frames.append(value)
                self.animation_durations.append(duration)
                if len(self.animation_frames) > 1:
                    self._schedule_animation_frame()
            elif message_type == "done":
                self.animation_load_complete = True
                self.animation_load_cancelled = None
            elif message_type == "error":
                self.animation_load_complete = True
                self.animation_load_cancelled = None
                messagebox.showerror(
                    "GIF Playback Incomplete",
                    f"Could not load all GIF frames:\n\n{value}",
                )

        if not self.animation_load_complete:
            self.animation_load_after_id = self.root.after(
                15,
                self._poll_animation_frames,
                generation,
            )

    def _stop_animation(self):
        if self.animation_after_id is not None:
            self.root.after_cancel(self.animation_after_id)
            self.animation_after_id = None
        self.animation_next_frame_at = None

    def _clear_animation(self):
        self._stop_animation()
        self.animation_generation += 1
        if self.animation_load_after_id is not None:
            self.root.after_cancel(self.animation_load_after_id)
            self.animation_load_after_id = None
        if self.animation_load_cancelled is not None:
            self.animation_load_cancelled.set()
            self.animation_load_cancelled = None
        self.animation_frame_queue = None
        self.animation_frames = []
        self.animation_durations = []
        self.animation_index = 0
        self.animation_load_complete = True

    def _schedule_animation_frame(self):
        if (
            len(self.animation_frames) > 1
            and not self.crop_mode
            and self.animation_after_id is None
        ):
            if self.animation_next_frame_at is None:
                self.animation_next_frame_at = (
                    time.monotonic()
                    + self.animation_durations[self.animation_index] / 1000
                )
            delay = max(
                1,
                round(
                    (self.animation_next_frame_at - time.monotonic()) * 1000
                )
            )
            self.animation_after_id = self.root.after(
                delay, self._show_next_animation_frame
            )

    def _show_next_animation_frame(self):
        self.animation_after_id = None
        if len(self.animation_frames) < 2 or self.crop_mode:
            return

        if (
            not self.animation_load_complete
            and self.animation_index + 1 >= len(self.animation_frames)
        ):
            self.animation_next_frame_at = None
            return

        now = time.monotonic()
        self.animation_index = (
            self.animation_index + 1
        ) % len(self.animation_frames)
        self.animation_next_frame_at += (
            self.animation_durations[self.animation_index] / 1000
        )
        while self.animation_next_frame_at <= now:
            self.animation_index = (
                self.animation_index + 1
            ) % len(self.animation_frames)
            self.animation_next_frame_at += (
                self.animation_durations[self.animation_index] / 1000
            )
        self.original_image = self.animation_frames[self.animation_index]
        self.display_current_image()
        self._schedule_animation_frame()

    def _load_folder_images(self):
        folder = self.image_path.parent

        self.folder_images = sorted(
            (
                file for file in folder.iterdir()
                if file.is_file()
                and file.suffix.lower() in self.SUPPORTED_FORMATS
            ),
            key=lambda file: file.name.lower()
        )

        try:
            self.image_index = self.folder_images.index(self.image_path)
        except ValueError:
            self.image_index = 0

    def display_current_image(self):
        if self.collage_mode:
            self._render_collage()
            return
        if self.image_layout_mode:
            self._render_image_layout()
            return
        if self.original_image is None:
            return

        self.canvas.delete("all")

        # Rotation affects viewing only, not the source file.
        image = self.original_image.rotate(
            self.rotation,
            expand=True,
            resample=Image.Resampling.BICUBIC
        )

        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())

        image_width, image_height = image.size

        if self.fit_mode:
            scale = min(
                canvas_width / image_width,
                canvas_height / image_height
            )
            scale = min(scale, 1.0)
        else:
            scale = self.zoom

        new_width = max(1, round(image_width * scale))
        new_height = max(1, round(image_height * scale))

        image = image.resize(
            (new_width, new_height),
            Image.Resampling.LANCZOS
        )

        self.display_image = image
        self.photo = ImageTk.PhotoImage(image)

        # Center the image in the available area and allow panning when zoomed in.
        x = canvas_width // 2 + self.pan_x
        y = canvas_height // 2 + self.pan_y

        self.canvas.create_image(
            x, y,
            image=self.photo,
            anchor=tk.CENTER
        )

        self._update_status(scale)

    def _update_status(self, displayed_scale=None):
        if self.original_image is None:
            self.status.config(text="No image open")
            return

        width, height = self.original_image.size

        if displayed_scale is None:
            displayed_scale = self.zoom

        if self.image_path:
            name = self.image_path.name
        else:
            name = ""

        if self.fit_mode:
            zoom_text = "Fit to window"
        else:
            zoom_text = f"{self.zoom * 100:.0f}%"

        count = len(self.folder_images)

        self.status.config(
            text=(
                f"{name}  |  {width} × {height} px  |  "
                f"{zoom_text}  |  "
                f"Image {self.image_index + 1}/{count}"
                if count else
                f"{name}  |  {width} × {height} px  |  {zoom_text}"
            )
        )

        self.root.title(f"{name} - Image Viewer")

    def _start_drag(self, event):
        if self.original_image is None or self.fit_mode and self.zoom <= 1.0:
            return

        self.dragging = True
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        self.pan_start_x = self.pan_x
        self.pan_start_y = self.pan_y

    def _drag_image(self, event):
        if not self.dragging or self.original_image is None:
            return

        self.pan_x = self.pan_start_x + (event.x - self.drag_start_x)
        self.pan_y = self.pan_start_y + (event.y - self.drag_start_y)
        self.display_current_image()

    def _stop_drag(self, event):
        self.dragging = False

    def change_zoom(self, factor):
        if self.original_image is None:
            return

        if self.fit_mode:
            self._record_history()
            self.zoom = min(
                self.canvas.winfo_width() / self.original_image.width,
                self.canvas.winfo_height() / self.original_image.height
            )
            self.fit_mode = False

        self._record_history()
        self.zoom = max(0.05, min(10.0, self.zoom * factor))
        self.pan_x = 0
        self.pan_y = 0
        self.display_current_image()

    def _mouse_zoom(self, event):
        if event.delta > 0:
            self.change_zoom(1.1)
        elif event.delta < 0:
            self.change_zoom(1 / 1.1)

    def fit_image(self):
        if self.original_image is not None:
            self._record_history()
            self.fit_mode = True
            self.pan_x = 0
            self.pan_y = 0
            self.display_current_image()

    def actual_size(self):
        if self.original_image is not None:
            self._record_history()
            self.fit_mode = False
            self.zoom = 1.0
            self.pan_x = 0
            self.pan_y = 0
            self.display_current_image()

    def rotate_image(self, angle):
        if self.original_image is not None:
            self._record_history()
            self.rotation = (self.rotation + angle) % 360
            self.display_current_image()

    def previous_image(self):
        self.navigate_image(-1)

    def next_image(self):
        self.navigate_image(1)

    def navigate_image(self, direction):
        if not self.folder_images:
            return

        new_index = self.image_index + direction

        # Stop at the first and last images.
        if not 0 <= new_index < len(self.folder_images):
            return

        self.load_image(str(self.folder_images[new_index]))
