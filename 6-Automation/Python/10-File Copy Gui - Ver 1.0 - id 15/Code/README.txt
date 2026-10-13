Word Copy GUI

This project is a small Windows desktop application for copying Microsoft Word documents while preserving formatting.

Files:
- file_copy_gui.py: main Tkinter application

Requirements:
- Python 3
- pywin32 (pythoncom / win32com)
- Microsoft Word installed on the machine

Install dependency:
- pip install pywin32

How to run:
1. Open a terminal in this folder.
2. Run: python file_copy_gui.py
3. Select a source Word file or folder.
4. Choose the destination folder.
5. Optionally enable "Include subfolders".
6. Click "Start Copy".

Notes:
- The app copies .doc and .docx files.
- It preserves the original document formatting by copying the formatted text content into a new Word document.
- If a file with the same name already exists in the destination, a numbered copy is created automatically.

This tool is intended for Windows environments because it uses the Word COM automation interface.
