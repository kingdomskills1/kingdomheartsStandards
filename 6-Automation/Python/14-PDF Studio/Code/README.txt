PDF Studio

A lightweight PDF viewer and editor built with Python and PySide6.

Overview
- Open one or multiple PDF files in separate tabs
- Reopen recently used PDFs from a quick-access menu
- View PDF pages and navigate between them
- Manage nested PDF bookmarks in a show/hide sidebar
- Create blank PDFs and update pages by adding, deleting, reordering, or rotating
- Add pages and place text, images, shapes, arrows, and interactive form fields visually
- Add multiple selected images as full-page PDF image pages
- Export the current PDF page
- Split a PDF into parts
- Merge multiple PDFs
- Compress an existing PDF

Project layout
- main.py              Main application window and menu actions
- pdf_viewer.py        PDF viewing logic and page navigation
- export_dialog.py     Export dialog for exporting current page
- split_dialog.py      Dialog for splitting PDFs
- merge_dialog.py      Dialog for combining multiple PDFs
- compress_dialog.py   Dialog for reducing PDF file size
- page_manager_dialog.py Page management dialog for existing PDFs
- pdf_editor_dialog.py Visual editor for adding page content and form fields

Requirements
- Python 3.x
- PySide6
- PyMuPDF or related PDF processing library used by the project

Run the application
1. Open a terminal in this folder.
2. Install dependencies if needed:
   pip install PySide6 PyMuPDF
3. Start the app:
   python main.py

Create PDF
- Use Create PDF to make a new blank A4 PDF.
- The visual editor opens after selecting a file name. Add pages and content
  directly, or use Manage Pages to see a large, scrollable thumbnail grid,
  drag pages to change their order, delete one or multiple selected pages,
  create a blank page, or add one or more image pages. Image-page entries show
  the source filename.
  Add text, images,
  rectangles, ellipses, arrows, text fields, or checkboxes. Drag components to move
  them and use the lower-right handle to resize. Double-click any component to
  open its properties dialog, where you can change its position, size, text,
  colors, border visibility/color/width, appearance, image, or form-field
  settings. Form fields support border color and width. Use Remove Selected to
  delete a component. Image pages show the source image filename while viewing
  the page. Flip pages with the mouse wheel or left/right arrow keys. Use Delete
  Page to remove the current page; the last remaining page cannot be deleted.
- Use Edit Content with an open PDF to add components or pages to a separate
  output PDF.
- Use the Bookmarks sidebar to jump to a bookmark, add or edit bookmarks,
  delete bookmarks, or drag them to reorder or nest them. Toggle the sidebar
  from View > Bookmarks. Bookmark changes are saved automatically to the
  currently open PDF. New and edited bookmarks retain the current zoom and
  scroll position as well as their page.

Notes
- This project is intended for local PDF management and basic editing tasks.
- For best results, use a modern Python environment with the required dependencies installed.
