Image Viewer Project Documentation
=================================

Overview
--------
This project is a desktop image viewer built with Python and Tkinter. It loads image files, displays them in a canvas, supports zooming, rotation, fullscreen mode, cropping, image layout adjustments, and collage creation.

Entry Point
-----------
The application starts in main.py. Running the script creates a Tk root window, instantiates the ImageViewer class, and enters the Tkinter event loop.

Main Class
----------
ImageViewer is defined in main.py and combines the behavior from several mixin modules:
- ViewerUIMixin: builds the window, toolbar, canvas, and keyboard shortcuts
- ViewerHistoryMixin: manages undo and redo state snapshots
- ViewerCollageMixin: creates and edits image collages
- ViewerCropMixin: handles crop selection and image crop operations
- ViewerLayoutMixin: supports fitting images to screen and layout editing
- ViewerImageMixin: opens, loads, and displays individual images

Supported Image Formats
----------------------
The viewer supports common raster image types, including:
.jpg, .jpeg, .png, .bmp, .gif, .tif, .tiff, .webp, .ico

Core Features
-------------
- Open one image from disk
- Browse through images in the same folder
- Zoom in and out
- Fit image to canvas or actual size
- Rotate left or right
- Pan around large images
- Fullscreen toggle
- Crop an image selection
- Undo/redo changes
- Create a collage from multiple images
- Save edited or collage results

User Interface Layout
---------------------
The main window has:
- A top toolbar with image and editing actions
- A central canvas for displaying images
- A status bar at the bottom for user feedback

Keyboard and Mouse Controls
---------------------------
- Ctrl+O: open image
- Left Arrow: previous image
- Right Arrow: next image
- Mouse wheel: zoom in/out
- Left click and drag: pan or manipulate current tool
- Double-click canvas: toggle fullscreen

Modules
-------
main.py
  Holds the ImageViewer class and creates the application window.

viewer_ui.py
  Defines the window layout, toolbar buttons, canvas bindings, and shortcut handlers.

viewer_image.py
  Opens files, loads images into memory, loads neighboring folder images, and renders the current image.

viewer_crop.py
  Handles crop selection, resizing crop bounds, and applying crop changes.

viewer_history.py
  Tracks snapshots of viewer state for undo/redo operations.

viewer_layout.py
  Provides support for fitting the image to screen size and moving/resizing it within a layout surface.

viewer_collage.py
  Creates multi-image collages, lays out tiles, and saves combined results.

Notes
-----
- The viewer uses Pillow (PIL) for image decoding and transformation.
- State is stored on the ImageViewer instance and reused by the mixins.
- Many operations work through the shared canvas and a set of coordinated flags such as crop_mode, collage_mode, and image_layout_mode.

Typical Usage
-------------
1. Run main.py.
2. Click Open to select an image.
3. Use toolbar actions to zoom, rotate, crop, or fullscreen.
4. Browse the folder using Previous and Next.
5. Save any modified image or collage when done.

Dependencies
------------
Required packages include:
- tkinter
- Pillow (PIL)

This project is designed for local desktop use and is meant to provide a simple image-editing and viewing workflow in a single Python application.
