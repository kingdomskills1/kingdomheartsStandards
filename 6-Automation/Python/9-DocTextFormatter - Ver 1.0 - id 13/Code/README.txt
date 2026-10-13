DocTextFormatter

A Python desktop utility for formatting text inside Word (.docx) documents.
It is built with Tkinter and python-docx, and allows you to apply font styling,
text filtering, highlighting, and document-wide formatting options through a GUI.

Project purpose:
- Open a .docx file or folder of .docx files
- Apply consistent font family, size, bold/italic/underline settings
- Set text color and highlight color
- Filter paragraphs by included/excluded text or regular expressions
- Restrict formatting to headings, tables, images, text, or all content
- Save the updated document back to the same file

Requirements:
- Python 3.x
- python-docx
- Tkinter (usually bundled with Python on desktop installs)

Install dependencies:
  pip install python-docx

Run the application:
  python doc_text_formatter.py

Notes:
- This tool is intended for editing document formatting in bulk.
- Make a backup of important .docx files before applying formatting changes.
- Regular-expression filtering is optional and case-insensitive by default.

Files in this folder:
- doc_text_formatter.py

This project is useful for standardizing document appearance across large Word files
without manually editing every paragraph in Microsoft Word.
