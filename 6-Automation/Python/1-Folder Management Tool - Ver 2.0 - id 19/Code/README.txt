Folder Management Tool - Version 2.0
===================================

Overview
--------
This project is a Windows-focused Python utility for managing folders, files, and media in a single desktop application. Version 2.0 expands the original tool into a tab-based interface with multiple productivity features for folder organization, tree printing, safe deletion, and media conversion.

Features
--------
- Browse and select a folder from the local file system
- Scan files and folders recursively with configurable filtering
- Limit results by depth and match criteria
- Include or exclude items by extension, file name, or full name
- Choose output formatting such as full path, filename, filename + extension, extension only, or folder-level path
- Copy filtered results to the clipboard
- Print a folder/file tree structure with optional ignored entries
- Remove and wipe folders using a safe recycle-bin workflow
- Convert images, videos, audio, and documents between common formats

Application tabs
----------------
1. Main Folder Management Tab
   - Select a target folder
   - Filter results using include/exclude logic
   - View generated file and folder lists
   - Copy or print selected output

2. Print Folder & File Tree
   - Generate a visual directory tree for a selected folder
   - Ignore files, folders, or extensions before printing
   - Copy the tree to the clipboard or display it in the app

3. Delete & Wipe
   - Select a folder for cleanup
   - Confirm the action before proceeding
   - Delete files and subfolders while sending them through the Windows recycle-bin workflow

4. Media Converter
   - Convert between supported image, video, audio, and document formats
   - Choose input files or folders
   - Select an output folder and conversion target
   - Monitor conversion progress in the UI

Project files
-------------
- folder_management_tool.py - Main application entry point
- tabs/
  - delete_tab.py - Safe delete and wipe workflow
  - print_tree_tab.py - Tree-printing and ignore rules
  - converter_tab.py - Media conversion utilities

Requirements
------------
- Python 3.x
- Windows environment
- A desktop GUI environment

Install dependencies:
    pip install send2trash Pillow proglog PyMuPDF python-docx reportlab pdf2docx

For video conversion, install FFmpeg and make sure it is available on your PATH:
    ffmpeg
    ffprobe

Run the tool:
    python folder_management_tool.py

Notes
-----
- The delete/wipe feature removes content from the selected folder and handles it through the Windows recycle-bin workflow for recovery safety.
- Use the utility carefully when working with important or irreplaceable directories.
- Media conversion depends on the availability of external tools and libraries.
- This tool is intended for practical local folder management and cleanup tasks in Windows-based workflows.

Project purpose
---------------
This tool was created to speed up repeated directory management tasks, especially when working with large folder structures that need filtering, listing, cleanup, or conversion.
