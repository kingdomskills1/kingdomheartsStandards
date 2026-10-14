import sys
import tkinter as tk
from pathlib import Path

from viewer_collage import ViewerCollageMixin
from viewer_crop import ViewerCropMixin
from viewer_history import ViewerHistoryMixin
from viewer_image import ViewerImageMixin
from viewer_layout import ViewerLayoutMixin
from viewer_ui import ViewerUIMixin


class ImageViewer(
    ViewerUIMixin,
    ViewerHistoryMixin,
    ViewerCollageMixin,
    ViewerCropMixin,
    ViewerLayoutMixin,
    ViewerImageMixin,
):
    SUPPORTED_FORMATS = {
        ".jpg", ".jpeg", ".png", ".bmp", ".gif",
        ".tif", ".tiff", ".webp", ".ico"
    }

    def __init__(self, root):
        self.root = root
        self.root.title("Image Viewer")
        self.root.iconbitmap(
            str(Path(__file__).with_name("Image Studio Icon.ico"))
        )
        self.root.geometry("1100x750")
        self.root.minsize(500, 350)
        self.root.configure(bg="#202020")

        self.recent_files = self._load_recent_files()
        self.image_path = None
        self.folder_images = []
        self.image_index = 0
        self.original_image = None
        self.display_image = None
        self.photo = None
        self.animation_frames = []
        self.animation_durations = []
        self.animation_index = 0
        self.animation_after_id = None
        self.animation_next_frame_at = None
        self.animation_generation = 0
        self.animation_frame_queue = None
        self.animation_load_after_id = None
        self.animation_load_cancelled = None
        self.animation_load_complete = True
        self.zoom = 1.0
        self.rotation = 0
        self.fit_mode = True
        self.fullscreen = False
        self.pan_x = 0
        self.pan_y = 0
        self.image_layout_mode = False
        self.image_layout_width = 0
        self.image_layout_height = 0
        self.image_layout_x = 0
        self.image_layout_y = 0
        self.image_layout_canvas_width = 0
        self.image_layout_canvas_height = 0
        self.image_layout_view_scale = 1.0
        self.image_layout_view_offset_x = 0
        self.image_layout_view_offset_y = 0
        self.image_layout_drag_action = None
        self.image_layout_drag_start = (0.0, 0.0)
        self.image_layout_initial_bounds = None
        self.dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.crop_mode = False
        self.crop_rect_id = None
        self.crop_start_x = 0
        self.crop_start_y = 0
        self.crop_drag_action = None
        self.crop_initial_coords = None
        self.crop_handle_ids = []
        self.collage_mode = False
        self.collage_items = []
        self.collage_selected_index = None
        self.collage_photos = []
        self.collage_canvas_width = 0
        self.collage_canvas_height = 0
        self.collage_view_scale = 1.0
        self.collage_view_offset_x = 0
        self.collage_view_offset_y = 0
        self.collage_drag_action = None
        self.collage_drag_start = (0, 0)
        self.collage_initial_bounds = None
        self.undo_stack = []
        self.redo_stack = []
        self.history_limit = 25

        self._build_interface()
        self._bind_shortcuts()

        self.root.after(100, self._initial_message)


if __name__ == "__main__":
    root = tk.Tk()
    app = ImageViewer(root)
    if len(sys.argv) > 1:
        root.after(0, app.load_image, str(Path(sys.argv[1])))
    root.mainloop()
